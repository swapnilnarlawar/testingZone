"""Configuration loading.

Behaviour (which repos, which release branch, branch naming) lives in
``function_app/config/automation.json`` so it is versioned and reviewed in Git,
and the same file is read by the Azure Function and by the ops scripts.

Environment-specific values (Key Vault URL, identity client id, webhook URL)
come from environment variables / Function App settings. Any key in the JSON
file can also be overridden by an environment variable with the same name in
upper case (lists are comma separated, booleans accept true/false/1/0).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "automation.json"

_DEFAULTS = {
    "gitlab_url": "https://gitlab.com",
    "source_repos": [],
    "target_repos": [],
    "release_branch": "release",
    "branch_name_template": "{username}/{project}-{iid}",
    "comment_on_issue": True,
    "excluded_assignees": [],
    "gitlab_token_secret_name": "gitlab-api-token",
    "webhook_secret_name": "gitlab-webhook-secret",
    "previous_secret_grace_hours": 24,
}

_LIST_KEYS = {"source_repos", "target_repos", "excluded_assignees"}
_BOOL_KEYS = {"comment_on_issue"}
_INT_KEYS = {"previous_secret_grace_hours"}


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    gitlab_url: str
    source_repos: list[str]
    target_repos: list[str]
    release_branch: str
    branch_name_template: str
    comment_on_issue: bool
    excluded_assignees: list[str]
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

    @property
    def previous_webhook_secret_name(self) -> str:
        return f"{self.webhook_secret_name}-previous"

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
            if raw is None or raw == "":
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
