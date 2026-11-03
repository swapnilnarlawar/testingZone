import pytest

import webhooks
from conftest import FakeGitLab, FakeStore

URL = "https://func.example.net/api/gitlab-webhook"


@pytest.fixture
def env(monkeypatch, config_file):
    monkeypatch.setenv("KEYVAULT_URL", "https://kv.vault.azure.net/")
    monkeypatch.setenv("WEBHOOK_URL", URL)
    monkeypatch.setenv("AUTOMATION_CONFIG", str(config_file))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    store = FakeStore({"gitlab-api-token": ("glpat", {})})
    gitlab = FakeGitLab(branches={"grp/app": {"release": "x"}, "grp/web": {"release": "x"},
                                  "grp/lib": {"release": "x"}},
                        hooks={"grp/app": [{"id": 1, "url": URL, "token": "old", "issues_events": True}],
                               "grp/sandbox/x": [{"id": 5, "url": URL, "token": "old", "issues_events": True}]})
    gitlab.groups = {"grp": ["grp/app", "grp/web", "grp/sandbox/x"]}
    monkeypatch.setattr(webhooks, "get_store", lambda settings: store)
    monkeypatch.setattr(webhooks, "get_gitlab", lambda settings, s: gitlab)
    return store, gitlab


def test_setup_watches_whole_group_except_excluded(env):
    store, gitlab = env
    assert webhooks.main(["setup"]) == 0
    secret = store.get("gitlab-webhook-secret")
    assert secret and len(secret) >= 40
    assert gitlab.hooks["grp/web"][0]["token"] == secret        # new repo picked up
    assert gitlab.hooks["grp/app"][0]["token"] == "old"         # healthy hook left alone
    assert gitlab.hooks["grp/sandbox/x"][0]["token"] == "old"   # excluded repo untouched


def test_setup_picks_up_repos_added_to_group_later(env):
    _, gitlab = env
    webhooks.main(["setup"])
    gitlab.groups["grp"].append("grp/brand-new")
    gitlab.branches["grp/brand-new"] = {"release": "x"}
    assert webhooks.main(["setup"]) == 0
    assert len(gitlab.hooks["grp/brand-new"]) == 1
    assert len(gitlab.hooks["grp/web"]) == 1                    # idempotent


def test_setup_repairs_disabled_hook_and_force_update(env):
    store, gitlab = env
    store.set("gitlab-webhook-secret", "current")
    gitlab.hooks["grp/app"][0]["alert_status"] = "disabled"
    webhooks.main(["setup"])
    assert gitlab.hooks["grp/app"][0]["token"] == "current"
    gitlab.hooks["grp/web"][0]["token"] = "stale"
    webhooks.main(["setup", "--force-update"])
    assert gitlab.hooks["grp/web"][0]["token"] == "current"


def test_setup_dry_run_changes_nothing(env):
    store, gitlab = env
    assert webhooks.main(["setup", "--dry-run"]) == 0
    assert store.get("gitlab-webhook-secret") is None
    assert "grp/web" not in gitlab.hooks


def test_rotate_updates_every_watched_hook_and_keeps_previous(env):
    store, gitlab = env
    store.set("gitlab-webhook-secret", "old")
    webhooks.main(["setup"])
    assert webhooks.main(["rotate", "--grace-hours", "2"]) == 0
    new = store.get("gitlab-webhook-secret")
    value, tags = store.get_with_tags("gitlab-webhook-secret-previous")
    assert new != "old" and value == "old" and "expires_at" in tags
    assert gitlab.hooks["grp/app"][0]["token"] == new and gitlab.hooks["grp/web"][0]["token"] == new


def test_cleanup_removes_hooks_from_excluded_repos_and_duplicates(env):
    _, gitlab = env
    gitlab.hooks["grp/app"].append({"id": 2, "url": URL, "token": "dup"})
    assert webhooks.main(["cleanup"]) == 0
    assert len(gitlab.hooks["grp/sandbox/x"]) == 1             # dry run
    assert webhooks.main(["cleanup", "--apply"]) == 0
    assert gitlab.hooks["grp/sandbox/x"] == []
    assert [h["id"] for h in gitlab.hooks["grp/app"]] == [1]


def test_verify_flags_new_repo_without_hook_then_passes(env, capsys):
    store, gitlab = env
    store.set("gitlab-webhook-secret", "s")
    assert webhooks.main(["verify", "--skip-endpoint"]) == 1
    assert "webhook missing" in capsys.readouterr().out
    webhooks.main(["setup"])
    assert webhooks.main(["verify", "--skip-endpoint"]) == 0


def test_verify_checks_release_branch_in_routed_targets(env, capsys):
    store, gitlab = env
    webhooks.main(["setup"])
    del gitlab.branches["grp/lib"]["release"]
    assert webhooks.main(["verify", "--skip-endpoint"]) == 1
    assert "target grp/lib: release branch problem" in capsys.readouterr().out


def test_summary_written_for_github_actions(env, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    webhooks.main(["setup", "--dry-run"])
    assert "Webhook sync" in summary.read_text()


def test_config_error_exit_code(env, monkeypatch):
    monkeypatch.delenv("WEBHOOK_URL")
    assert webhooks.main(["setup"]) == 2
