import pytest

import webhooks
from conftest import FakeGitLab, FakeStore

URL = "https://func.example.net/api/gitlab-webhook"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYVAULT_URL", "https://kv.vault.azure.net/")
    monkeypatch.setenv("WEBHOOK_URL", URL)
    monkeypatch.setenv("SOURCE_REPOS", "grp/app,grp/web")
    monkeypatch.setenv("TARGET_REPOS", "grp/app")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    store = FakeStore({"gitlab-api-token": ("glpat", {})})
    gitlab = FakeGitLab(branches={"grp/app": {"release": "x"}},
                        hooks={"grp/app": [{"id": 1, "url": URL, "token": "old", "issues_events": True}],
                               "grp/old": [{"id": 5, "url": URL, "token": "old"}]})
    monkeypatch.setattr(webhooks, "get_store", lambda settings: store)
    monkeypatch.setattr(webhooks, "get_gitlab", lambda settings, s: gitlab)
    return store, gitlab


def test_setup_generates_secret_and_syncs_hooks(env):
    store, gitlab = env
    assert webhooks.main(["setup"]) == 0
    secret = store.get("gitlab-webhook-secret")
    assert secret and len(secret) >= 40
    assert gitlab.hooks["grp/app"][0]["token"] == secret        # updated
    assert gitlab.hooks["grp/web"][0]["token"] == secret        # created
    assert webhooks.main(["setup"]) == 0                         # idempotent
    assert len(gitlab.hooks["grp/web"]) == 1


def test_setup_dry_run_changes_nothing(env):
    store, gitlab = env
    assert webhooks.main(["setup", "--dry-run"]) == 0
    assert store.get("gitlab-webhook-secret") is None
    assert "grp/web" not in gitlab.hooks


def test_rotate_keeps_previous_with_expiry(env):
    store, gitlab = env
    store.set("gitlab-webhook-secret", "old")
    assert webhooks.main(["rotate", "--grace-hours", "2"]) == 0
    new = store.get("gitlab-webhook-secret")
    assert new != "old"
    value, tags = store.get_with_tags("gitlab-webhook-secret-previous")
    assert value == "old" and "expires_at" in tags
    assert all(h["token"] == new for repo in ("grp/app", "grp/web") for h in gitlab.hooks[repo])


def test_cleanup_dry_run_then_apply(env):
    _, gitlab = env
    gitlab.hooks["grp/app"].append({"id": 2, "url": URL, "token": "dup"})
    assert webhooks.main(["cleanup", "--group", "grp"]) == 0
    assert len(gitlab.hooks["grp/old"]) == 1 and len(gitlab.hooks["grp/app"]) == 2
    assert webhooks.main(["cleanup", "--group", "grp", "--apply"]) == 0
    assert gitlab.hooks["grp/old"] == []
    assert [h["id"] for h in gitlab.hooks["grp/app"]] == [1]


def test_verify_reports_missing_hook(env, capsys):
    store, gitlab = env
    store.set("gitlab-webhook-secret", "s")
    assert webhooks.main(["verify", "--skip-endpoint"]) == 1   # grp/web has no hook
    assert "webhook missing" in capsys.readouterr().out
    webhooks.main(["setup"])
    assert webhooks.main(["verify", "--skip-endpoint"]) == 0


def test_summary_written_for_github_actions(env, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    webhooks.main(["setup", "--dry-run"])
    assert "Webhook setup" in summary.read_text()


def test_config_error_exit_code(env, monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL")
    monkeypatch.setenv("AUTOMATION_CONFIG", "/nonexistent.json")
    assert webhooks.main(["setup"]) == 2
