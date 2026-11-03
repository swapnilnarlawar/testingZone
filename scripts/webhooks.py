#!/usr/bin/env python3
"""Operations CLI for the GitLab branch automation.

Commands
  store-token  Save the GitLab API token in Key Vault (prompted, never echoed)
  setup        Create the webhook secret if missing and add the webhook to every
               watched repo (all projects in source_groups + source_repos)
  verify       Check webhooks, target repos and the Azure Function end to end
  rotate       Generate a new webhook secret and push it to every webhook
  cleanup      Remove stale or duplicate webhooks (dry run unless --apply)

Run ``python scripts/webhooks.py <command> --help`` for options. Configuration is
read from function_app/config/automation.json plus environment variables
(KEYVAULT_URL, WEBHOOK_URL, AZURE_CLIENT_ID); see docs/CONFIGURATION.md.
Secret values are never printed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "function_app"))

from shared.config import Settings  # noqa: E402
from shared.gitlab_client import GitLabClient, GitLabError  # noqa: E402
from shared.secret_store import SecretStore  # noqa: E402


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from .env into the environment (existing variables win)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# --------------------------------------------------------------------------- output
class Report:
    """Collects result rows, prints them, and writes a GitHub Actions job summary."""

    def __init__(self, title: str):
        self.title = title
        self.rows: list[tuple[str, str, str]] = []
        self.failed = False

    def add(self, target: str, status: str, detail: str = "", failure: bool = False) -> None:
        self.rows.append((target, status, detail))
        self.failed = self.failed or failure
        mark = "FAIL" if failure else "ok  "
        print(f"  [{mark}] {target}: {status}{' - ' + detail if detail else ''}")

    def finish(self) -> int:
        verdict = "FAILED" if self.failed else "OK"
        print(f"\n{self.title}: {verdict}")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as fh:
                fh.write(f"## {self.title}: {':x: ' if self.failed else ':white_check_mark: '}{verdict}\n\n")
                fh.write("| Target | Status | Detail |\n|---|---|---|\n")
                for target, status, detail in self.rows:
                    fh.write(f"| {target} | {status} | {detail.replace('|', '/')} |\n")
                fh.write("\n")
        return 1 if self.failed else 0


# --------------------------------------------------------------------------- helpers
def get_store(settings: Settings) -> SecretStore:
    settings.require("keyvault_url")
    return SecretStore(settings.keyvault_url, settings.azure_client_id)


def get_gitlab(settings: Settings, store: SecretStore | None) -> GitLabClient:
    token = settings.gitlab_token or (store.get(settings.gitlab_token_secret_name) if store else None)
    if not token:
        raise SystemExit(
            f"GitLab token not found. Run 'python scripts/webhooks.py store-token' "
            f"(Key Vault secret '{settings.gitlab_token_secret_name}')."
        )
    return GitLabClient(settings.gitlab_url, token, timeout=20)


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def matching_hooks(gitlab: GitLabClient, repo: str, urls: set[str]) -> list[dict]:
    return sorted((h for h in gitlab.list_hooks(repo) if h.get("url") in urls), key=lambda h: h["id"])


def group_projects(gitlab: GitLabClient, groups: list[str], report: Report) -> dict[str, str]:
    """All non-archived projects in ``groups`` (subgroups included), keyed by lower-case path."""
    found: dict[str, str] = {}
    for group in groups:
        try:
            for project in gitlab.list_group_projects(group):
                path = project["path_with_namespace"]
                found.setdefault(path.lower(), path)
        except GitLabError as exc:
            report.add(f"group {group}", "error", exc.message, failure=True)
    return found


def watched_repos(gitlab: GitLabClient, settings: Settings, report: Report) -> list[str]:
    """Repos that should have the webhook: every project in source_groups plus
    source_repos, minus exclude_repos. New projects in a group are picked up
    automatically the next time this runs."""
    repos = group_projects(gitlab, settings.source_groups, report)
    for repo in settings.source_repos:
        repos.setdefault(repo.lower(), repo)
    return sorted(path for path in repos.values() if not settings.is_excluded(path))


def hook_problems(hook: dict) -> list[str]:
    problems = []
    if not hook.get("issues_events"):
        problems.append("issue events off")
    if hook.get("alert_status") in {"disabled", "temporarily_disabled"}:
        problems.append(f"hook {hook['alert_status']}")
    return problems


def sync_hooks(gitlab: GitLabClient, settings: Settings, repos: list[str], secret: str, report: Report,
               force_update: bool = False, dry_run: bool = False) -> None:
    """Make sure every watched repo has a webhook to WEBHOOK_URL.

    Missing hooks are created; existing hooks are updated when misconfigured
    or disabled, or always when ``force_update`` is set (secret rotation).
    """
    for repo in repos:
        try:
            hooks = matching_hooks(gitlab, repo, {settings.webhook_url})
            extra = f"{len(hooks) - 1} duplicate(s), run cleanup" if len(hooks) > 1 else ""
            if not hooks:
                if dry_run:
                    report.add(repo, "would create hook")
                else:
                    hook = gitlab.create_hook(repo, settings.webhook_url, secret)
                    report.add(repo, f"created hook {hook['id']}")
                continue
            problems = hook_problems(hooks[0])
            if not (force_update or problems):
                report.add(repo, "hook ok", extra)
            elif dry_run:
                report.add(repo, "would update hook", ", ".join(problems))
            else:
                gitlab.update_hook(repo, hooks[0]["id"], settings.webhook_url, secret)
                report.add(repo, f"updated hook {hooks[0]['id']}", ", ".join(problems + ([extra] if extra else [])))
        except GitLabError as exc:
            report.add(repo, "error", exc.message, failure=True)


def require_sources(settings: Settings) -> None:
    if not (settings.source_groups or settings.source_repos):
        raise ValueError("Set source_groups and/or source_repos in automation.json")


# --------------------------------------------------------------------------- commands
def cmd_store_token(settings: Settings, args) -> int:
    store = get_store(settings)
    token = os.environ.get("GITLAB_TOKEN") if args.from_env else getpass.getpass("GitLab API token (input hidden): ")
    token = (token or "").strip()
    if not token:
        print("No token provided.")
        return 1
    try:
        user = GitLabClient(settings.gitlab_url, token).current_user()
    except GitLabError as exc:
        print(f"Token rejected by {settings.gitlab_url}: {exc.message}")
        return 1
    store.set(settings.gitlab_token_secret_name, token, tags={"stored_at": now_utc().isoformat(),
                                                              "gitlab_user": user.get("username", "")})
    print(f"Stored token for @{user.get('username')} in Key Vault secret '{settings.gitlab_token_secret_name}'.")
    return 0


def cmd_setup(settings: Settings, args) -> int:
    settings.require("webhook_url")
    require_sources(settings)
    store = get_store(settings)
    gitlab = get_gitlab(settings, store)
    report = Report("Webhook sync" + (" (dry run)" if args.dry_run else ""))

    secret = store.get(settings.webhook_secret_name)
    if secret is None:
        if args.dry_run:
            report.add("Key Vault", "would generate webhook secret")
            secret = "dry-run"
        else:
            secret = new_secret()
            store.set(settings.webhook_secret_name, secret, tags={"created_at": now_utc().isoformat()})
            report.add("Key Vault", f"generated secret '{settings.webhook_secret_name}'")
    else:
        report.add("Key Vault", f"using existing secret '{settings.webhook_secret_name}'")

    repos = watched_repos(gitlab, settings, report)
    report.add("watched repos", str(len(repos)))
    sync_hooks(gitlab, settings, repos, secret, report, force_update=args.force_update, dry_run=args.dry_run)
    return report.finish()


def cmd_rotate(settings: Settings, args) -> int:
    settings.require("webhook_url")
    require_sources(settings)
    store = get_store(settings)
    gitlab = get_gitlab(settings, store)
    report = Report("Webhook secret rotation")

    grace = args.grace_hours if args.grace_hours is not None else settings.previous_secret_grace_hours
    stamp = now_utc()
    current = store.get(settings.webhook_secret_name)
    if current:
        # Keep the old secret valid for a while so calls already in flight are not rejected.
        store.set(settings.previous_webhook_secret_name, current, tags={
            "rotated_at": stamp.isoformat(), "expires_at": (stamp + timedelta(hours=grace)).isoformat()})
        report.add("Key Vault", f"previous secret kept valid for {grace}h")

    secret = new_secret()
    store.set(settings.webhook_secret_name, secret, tags={"rotated_at": stamp.isoformat()})
    report.add("Key Vault", f"new secret stored in '{settings.webhook_secret_name}'")

    sync_hooks(gitlab, settings, watched_repos(gitlab, settings, report), secret, report, force_update=True)
    if report.failed:
        print("Some webhooks were not updated. Fix the errors and re-run 'rotate' or 'setup --force-update' "
              f"before the {grace}h grace period ends.")
    return report.finish()


def cmd_verify(settings: Settings, args) -> int:
    settings.require("webhook_url", "routes")
    require_sources(settings)
    store = get_store(settings)
    gitlab = get_gitlab(settings, store)
    report = Report("Webhook verification")

    try:
        user = gitlab.current_user()
        report.add("GitLab token", f"valid (@{user.get('username')})")
    except GitLabError as exc:
        report.add("GitLab token", "invalid", exc.message, failure=True)
        return report.finish()

    repos = watched_repos(gitlab, settings, report)
    targets: dict[str, None] = {}
    for repo in repos:
        routed = settings.targets_for(repo)
        for target in routed:
            targets.setdefault(target, None)
        try:
            hooks = matching_hooks(gitlab, repo, {settings.webhook_url})
        except GitLabError as exc:
            report.add(f"source {repo}", "error", exc.message, failure=True)
            continue
        if not hooks:
            report.add(f"source {repo}", "webhook missing", "new repo? run setup (the daily sync adds it)",
                       failure=True)
            continue
        problems = hook_problems(hooks[0]) + ([f"{len(hooks)} duplicate hooks"] if len(hooks) > 1 else [])
        if not routed:
            problems.append("no route matches, issues here create no branches")
        report.add(f"source {repo}", "webhook problem" if problems else "webhook ok", ", ".join(problems),
                   failure=bool(problems))

    for repo in targets:
        release, _ = settings.target_settings(repo)
        try:
            ref = gitlab.resolve_ref(repo, release)
            report.add(f"target {repo}", f"release branch ok ({ref})")
        except GitLabError as exc:
            report.add(f"target {repo}", "release branch problem", exc.message, failure=True)

    if not args.skip_endpoint:
        verify_endpoint(settings, store, report)
    return report.finish()


def verify_endpoint(settings: Settings, store: SecretStore, report: Report) -> None:
    hook_url = settings.webhook_url
    health_url = hook_url.rsplit("/", 1)[0] + "/health"
    secret = store.get(settings.webhook_secret_name)

    checks = [
        ("function liveness", "GET", health_url, {}, 200),
        ("function rejects bad token", "POST", hook_url, {"X-Gitlab-Token": "invalid-" + new_secret()}, 401),
    ]
    if secret:
        checks.append(("function deep health", "POST", health_url, {"X-Gitlab-Token": secret}, 200))
    else:
        report.add("function deep health", "skipped", "webhook secret missing in Key Vault", failure=True)

    for name, method, url, headers, expected in checks:
        try:
            resp = requests.request(method, url, headers=headers, json={} if method == "POST" else None, timeout=30)
            detail = resp.text[:200] if resp.status_code != expected or name == "function deep health" else ""
            report.add(name, f"HTTP {resp.status_code}", detail, failure=resp.status_code != expected)
        except requests.RequestException as exc:
            report.add(name, "unreachable", str(exc), failure=True)


def cmd_cleanup(settings: Settings, args) -> int:
    settings.require("webhook_url")
    store = get_store(settings)
    gitlab = get_gitlab(settings, store)
    report = Report("Webhook cleanup" + ("" if args.apply else " (dry run)"))

    urls = {settings.webhook_url, *args.legacy_url}
    keep = set() if args.remove_all else {r.lower() for r in watched_repos(gitlab, settings, report)}
    # Scan the configured groups (excluded repos included), extra groups and repos.
    repos = group_projects(gitlab, [*settings.source_groups, *args.group], report)
    for repo in [*settings.source_repos, *args.repo]:
        repos.setdefault(repo.lower(), repo)

    for key, repo in sorted(repos.items()):
        try:
            hooks = matching_hooks(gitlab, repo, urls)
        except GitLabError as exc:
            report.add(repo, "error", exc.message, failure=True)
            continue
        if key in keep:
            # Keep the oldest hook pointing at the current URL, remove legacy URLs and duplicates.
            current = [h for h in hooks if h["url"] == settings.webhook_url]
            stale = [h for h in hooks if h not in current[:1]]
        else:
            stale = hooks
        for hook in stale:
            if key not in keep:
                reason = "teardown" if args.remove_all else (
                    "repo excluded" if settings.is_excluded(repo) else "repo no longer watched")
            else:
                reason = "duplicate" if hook["url"] == settings.webhook_url else "legacy URL"
            if args.apply:
                try:
                    gitlab.delete_hook(repo, hook["id"])
                    report.add(repo, f"deleted hook {hook['id']}", reason)
                except GitLabError as exc:
                    report.add(repo, f"delete hook {hook['id']} failed", exc.message, failure=True)
            else:
                report.add(repo, f"would delete hook {hook['id']}", reason)
    if not any(r[1].startswith(("would", "deleted", "delete")) for r in report.rows):
        report.add("all repos", "nothing to clean up")
    return report.finish()


# --------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to automation.json (default: function_app/config/automation.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("store-token", help="save the GitLab API token in Key Vault")
    p.add_argument("--from-env", action="store_true", help="read the token from GITLAB_TOKEN instead of prompting")

    p = sub.add_parser("setup", help="add the webhook to every watched repo (safe to re-run)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-update", action="store_true", help="re-write every hook with the current secret")

    sub.add_parser("verify", help="check webhooks, release branches and the function").add_argument(
        "--skip-endpoint", action="store_true", help="do not call the Azure Function")

    p = sub.add_parser("rotate", help="rotate the webhook secret")
    p.add_argument("--grace-hours", type=int, help="hours the previous secret stays valid")

    p = sub.add_parser("cleanup", help="remove stale or duplicate webhooks")
    p.add_argument("--apply", action="store_true", help="actually delete (default is a dry run)")
    p.add_argument("--group", action="append", default=[], help="also scan every project in this extra group")
    p.add_argument("--repo", action="append", default=[], help="also scan this project path")
    p.add_argument("--legacy-url", action="append", default=[], help="old webhook URL to remove everywhere")
    p.add_argument("--remove-all", action="store_true", help="remove the webhooks from source repos too (teardown)")
    return parser


COMMANDS = {"store-token": cmd_store_token, "setup": cmd_setup, "verify": cmd_verify,
            "rotate": cmd_rotate, "cleanup": cmd_cleanup}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(REPO_ROOT / ".env")
    try:
        settings = Settings.load(args.config)
        return COMMANDS[args.command](settings, args)
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
