"""Azure Functions entry point (Python v2 programming model).

Routes:
  POST /api/gitlab-webhook  - GitLab Issue Hook receiver; creates branches on assignment
  GET  /api/health          - liveness check (no secrets touched)
  POST /api/health          - deep check of Key Vault + GitLab access (needs X-Gitlab-Token)
"""

import json
import logging

import azure.functions as func

from shared.config import Settings
from shared.gitlab_client import GitLabClient
from shared.handler import WebhookHandler, build_secret_loaders
from shared.secret_store import SecretStore

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

_handler: WebhookHandler | None = None


def _get_handler() -> WebhookHandler:
    """Build the handler once per worker so secrets are cached between calls."""
    global _handler
    if _handler is None:
        settings = Settings.load()
        store = SecretStore(settings.keyvault_url, settings.azure_client_id) if settings.keyvault_url else None
        webhook_secrets, gitlab_token = build_secret_loaders(settings, store)
        _handler = WebhookHandler(
            settings,
            webhook_secrets,
            gitlab_factory=lambda: GitLabClient(settings.gitlab_url, gitlab_token.get()),
        )
    return _handler


def _json_response(status: int, body: dict) -> func.HttpResponse:
    return func.HttpResponse(json.dumps(body), status_code=status, mimetype="application/json")


@app.route(route="gitlab-webhook", methods=["POST"])
def gitlab_webhook(req: func.HttpRequest) -> func.HttpResponse:
    try:
        status, body = _get_handler().handle(req.headers.get("X-Gitlab-Token"), req.get_body())
    except Exception:
        logging.exception("Unhandled error while processing GitLab webhook")
        status, body = 500, {"error": "internal error"}
    return _json_response(status, body)


@app.route(route="health", methods=["GET", "POST"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "GET":
        return _json_response(200, {"status": "ok"})
    try:
        status, body = _get_handler().deep_health(req.headers.get("X-Gitlab-Token"))
    except Exception as exc:
        logging.exception("Deep health check failed")
        status, body = 503, {"status": "error", "error": type(exc).__name__}
    return _json_response(status, body)
