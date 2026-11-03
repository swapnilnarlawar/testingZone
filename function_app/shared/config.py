"""Configuration loading.

Behaviour (which repos are watched, where branches go, branch naming) lives in
``function_app/config/automation.json`` so it is versioned and reviewed in Git,
and the same file is read by the Azure Function and by the ops scripts.

Environment-specific values (Key Vault URL, identity client id, webhook URL)
come from environment variables / Function App settings. Simple keys in the
JSON file can also be overridden by an environment variable with the same name
in upper case (lists are comma separated, booleans accept true/false/1/0).
"""

from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "automation.json"

_DEFAULTS = {
    "gitlab_url": "https://gitlab.com",
    "source_groups": [],
    "source_repos": [],
    "exclude_repos": [],
    "routes": [],
    "release_branch": "release",
    "branch_name_template": "feature/{project}-{iid}",
    "target_overrides": {},
    "comment_on_issue": True,
    "gitlab_token_secret_name": "gitlab-api-token",
    "webhook_secret_name": "gitlab-webhook-secret",
    "previous_secret_grace_hours": 24,
}

_LIST_KEYS = {"source_groups", "source_repos", "exclude_repos"}
_BOOL_KEYS = {"comment_on_issue"}
_INT_KEYS = {"previous_secret_grace_hours"}
_STRUCT_KEYS = {"routes", "target_overrides"}  # JSON file only, no env override
_OVERRIDE_KEYS = {"release_branch", "branch_name_template"}


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def path_matches(path: str, patterns: list[str]) -> bool:
    """Case-insensitive match of a project path against exact paths or globs.

    ``group/*`` matches every project below ``group`` (including subgroups).
    """
    lowered = path.lower()
    return any(fnmatch.fnmatchcase(lowered, p.lower()) for p in patterns)


@dataclass
class Settings:
    gitlab_url: str
    source_groups: list[str]
    source_repos: list[str]
    exclude_repos: list[str]
    routes: list[dict]
    release_branch: str
    branch_name_template: str
    target_overrides: dict
    comment_on_issue: bool
    gitlab_token_secret_name: str
    webhook_secret_name: str
    previous_secret_grace_hours: int
    # Environment-specific values
    keyvault_url: str | None = None
    azure_client_id: str | None = None
    webhook_url: str | None = None
    # Local development only: bypass Key Vault when these are set.
    gitlab_token: str | None = field(default=None, repr=False)
    webhook_secret: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._validate()

    # ------------------------------------------------------------------ derived values
    @property
    def previous_webhook_secret_name(self) -> str:
        return f"{self.webhook_secret_name}-previous"

    def is_excluded(self, project_path: str) -> bool:
        return path_matches(project_path, self.exclude_repos)

    def targets_for(self, source_path: str) -> list[str]:
        """Target repos for an issue in ``source_path``: the first matching route wins."""
        for route in self.routes:
            if path_matches(source_path, [route["source"]]):
                return [source_path if t == "{source}" else t for t in route["targets"]]
        return []

    def all_targets(self) -> list[str]:
        seen: dict[str, None] = {}
        for route in self.routes:
            for target in route["targets"]:
                if target != "{source}":
                    seen.setdefault(target, None)
        return list(seen)

    def target_settings(self, repo: str) -> tuple[str, str]:
        """(release_branch, branch_name_template) for a target repo, honouring overrides."""
        release, template = self.release_branch, self.branch_name_template
        for pattern, override in self.target_overrides.items():
            if path_matches(repo, [pattern]):
                release = override.get("release_branch", release)
                template = override.get("branch_name_template", template)
                break
        return release, template

    # ------------------------------------------------------------------ validation
    def _validate(self) -> None:
        from .branching import validate_template

        if not isinstance(self.routes, list):
            raise ValueError("routes must be a list")
        for i, route in enumerate(self.routes):
            if not isinstance(route, dict) or not route.get("source") or not route.get("targets"):
                raise ValueError(f"routes[{i}] needs a 'source' pattern and a non-empty 'targets' list")
            if set(route) - {"source", "targets", "$comment"}:
                raise ValueError(f"routes[{i}] has unknown keys: {', '.join(sorted(set(route) - {'source', 'targets'}))}")
        if not isinstance(self.target_overrides, dict):
            raise ValueError("target_overrides must be an object of {repo pattern: {...}}")
        validate_template(self.branch_name_template)
        for pattern, override in self.target_overrides.items():
            if pattern == "$comment":
                continue
            unknown = set(override) - _OVERRIDE_KEYS - {"$comment"}
            if unknown:
                raise ValueError(f"target_overrides['{pattern}'] has unknown keys: {', '.join(sorted(unknown))}")
            if "branch_name_template" in override:
                validate_template(override["branch_name_template"])
        self.target_overrides = {k: v for k, v in self.target_overrides.items() if k != "$comment"}

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: str | os.PathLike | None = None, env: dict | None = None) -> "Settings":
        env = os.environ if env is None else env
        config_path = Path(path or env.get("AUTOMATION_CONFIG") or DEFAULT_CONFIG_PATH)

        values = dict(_DEFAULTS)
        if config_path.exists():
            with open(config_path, encoding="utf-8") as fh:
                data = json.load(fh)
            unknown = set(data) - set(_DEFAULTS) - {"$comment"}
            if unknown:
                raise ValueError(f"Unknown keys in {config_path}: {', '.join(sorted(unknown))}")
            values.update({k: v for k, v in data.items() if k != "$comment"})

        for key in _DEFAULTS:
            raw = env.get(key.upper())
            if raw is None or raw == "" or key in _STRUCT_KEYS:
                continue
            if key in _LIST_KEYS:
                values[key] = _parse_list(raw)
            elif key in _BOOL_KEYS:
                values[key] = _parse_bool(raw)
            elif key in _INT_KEYS:
                values[key] = int(raw)
            else:
                values[key] = raw

        return cls(
            **values,
            keyvault_url=env.get("KEYVAULT_URL") or None,
            azure_client_id=env.get("AZURE_CLIENT_ID") or None,
            webhook_url=env.get("WEBHOOK_URL") or None,
            gitlab_token=env.get("GITLAB_TOKEN") or None,
            webhook_secret=env.get("WEBHOOK_SECRET") or None,
        )

    def require(self, *names: str) -> None:
        """Raise a readable error if any of the named settings are empty."""
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise ValueError(
                "Missing required configuration: "
                + ", ".join(n.upper() if n in {"keyvault_url", "webhook_url", "azure_client_id"} else n for n in missing)
            )
