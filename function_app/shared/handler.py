"""Framework-independent webhook handling (kept separate so it is unit-testable)."""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import asdict
from typing import Callable

from .config import Settings
from .events import parse_assignment_event
from .processor import process_assignment
from .secret_store import CachedValue, SecretStore, previous_secret_is_valid

logger = logging.getLogger(__name__)


def build_secret_loaders(settings: Settings, store: SecretStore | None):
    """Return (webhook_secrets, gitlab_token) cached loaders.

    ``webhook_secrets`` yields the list of currently accepted secrets: the
    current one plus, during the grace period after a rotation, the previous one.
    """

    def load_webhook_secrets() -> list[str]:
        if settings.webhook_secret:
            return [settings.webhook_secret]
        if store is None:
            raise RuntimeError("KEYVAULT_URL is not configured")
        accepted = []
        current = store.get(settings.webhook_secret_name)
        if current:
            accepted.append(current)
        previous = store.get_with_tags(settings.previous_webhook_secret_name)
        if previous and previous_secret_is_valid(previous[1]):
            accepted.append(previous[0])
        return accepted

    def load_gitlab_token() -> str:
        if settings.gitlab_token:
            return settings.gitlab_token
        if store is None:
            raise RuntimeError("KEYVAULT_URL is not configured")
        token = store.get(settings.gitlab_token_secret_name)
        if not token:
            raise RuntimeError(f"Secret '{settings.gitlab_token_secret_name}' not found in Key Vault")
        return token

    return CachedValue(load_webhook_secrets), CachedValue(load_gitlab_token)


class WebhookHandler:
    def __init__(self, settings: Settings, webhook_secrets: CachedValue, gitlab_factory: Callable):
        self.settings = settings
        self.webhook_secrets = webhook_secrets
        self.gitlab_factory = gitlab_factory

    @staticmethod
    def _matches(provided: str, accepted: list[str]) -> bool:
        provided_b = provided.encode()
        # Compare against every accepted secret so timing does not reveal which matched.
        results = [hmac.compare_digest(provided_b, s.encode()) for s in accepted or []]
        return any(results)

    def is_authorized(self, token_header: str | None) -> bool:
        """GitLab sends the webhook secret verbatim in the ``X-Gitlab-Token`` header."""
        if not token_header:
            return False
        if self._matches(token_header, self.webhook_secrets.get()):
            return True
        # The secret may have been rotated since we cached it: reload once and retry.
        return self._matches(token_header, self.webhook_secrets.get(refresh=True))

    def handle(self, token_header: str | None, body: bytes) -> tuple[int, dict]:
        if not self.is_authorized(token_header):
            logger.warning("Rejected webhook call with missing or invalid X-Gitlab-Token")
            return 401, {"error": "unauthorized"}

        try:
            payload = json.loads(body or b"{}")
        except ValueError:
            return 400, {"error": "body is not valid JSON"}

        event = parse_assignment_event(payload)
        if event is None:
            return 200, {"status": "ignored", "reason": "not an assignment"}
        issue = f"{event.project_path}#{event.issue_iid}"
        if self.settings.is_excluded(event.project_path):
            return 200, {"status": "ignored", "reason": "repo excluded", "issue": issue}
        if not self.settings.targets_for(event.project_path):
            logger.warning("No route matches %s; add one to automation.json", event.project_path)
            return 200, {"status": "ignored", "reason": "no route for this repo", "issue": issue}

        logger.info("Issue %s assigned to %s", issue, ", ".join(a.username for a in event.added))
        results = process_assignment(event, self.gitlab_factory(), self.settings)
        # Always 200 once authenticated: GitLab disables hooks that keep failing,
        # and per-branch failures are reported in the body, the logs and on the issue.
        return 200, {
            "status": "processed",
            "issue": issue,
            "results": [asdict(r) for r in results],
        }

    def deep_health(self, token_header: str | None) -> tuple[int, dict]:
        """Check Key Vault and GitLab access. Requires a valid webhook token."""
        if not self.is_authorized(token_header):
            return 401, {"error": "unauthorized"}
        checks = {"keyvault": "ok"}
        try:
            user = self.gitlab_factory().current_user()
            checks["gitlab"] = f"ok (as @{user.get('username')})"
        except Exception as exc:
            checks["gitlab"] = f"error: {exc}"
        healthy = all(v.startswith("ok") for v in checks.values())
        return (200 if healthy else 503), {"status": "ok" if healthy else "degraded", "checks": checks}
