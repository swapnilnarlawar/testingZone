import json

import pytest

from shared.config import DEFAULT_CONFIG_PATH, Settings


def write(tmp_path, data):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data))
    return path


def test_shipped_config_loads():
    settings = Settings.load(DEFAULT_CONFIG_PATH, env={})
    assert settings.source_groups and settings.routes


def test_routes_first_match_wins_and_source_placeholder(settings):
    assert settings.targets_for("grp/pay/ledger") == ["grp/pay/ledger", "grp/pay-api"]
    assert settings.targets_for("grp/web") == ["grp/web", "grp/lib"]
    assert settings.all_targets() == ["grp/pay-api", "grp/lib"]


def test_no_route_means_no_targets(tmp_path):
    settings = Settings.load(write(tmp_path, {"routes": [{"source": "a/*", "targets": ["a/x"]}]}), env={})
    assert settings.targets_for("b/y") == []


def test_target_overrides(settings):
    assert settings.target_settings("grp/pay-api") == ("release/*", "pay/{iid}")
    assert settings.target_settings("grp/lib") == ("release", "feature/{project}-{iid}")


def test_exclusions_are_case_insensitive_globs(settings):
    assert settings.is_excluded("GRP/Sandbox/thing")
    assert not settings.is_excluded("grp/app")


def test_env_overrides(tmp_path):
    settings = Settings.load(write(tmp_path, {"source_groups": ["a"]}), env={
        "SOURCE_GROUPS": "x, y", "COMMENT_ON_ISSUE": "false", "PREVIOUS_SECRET_GRACE_HOURS": "6",
        "KEYVAULT_URL": "https://kv", "ROUTES": "ignored"})
    assert settings.source_groups == ["x", "y"]
    assert settings.comment_on_issue is False and settings.previous_secret_grace_hours == 6
    assert settings.keyvault_url == "https://kv" and settings.routes == []


@pytest.mark.parametrize("data,message", [
    ({"target_repos": ["old key"]}, "target_repos"),
    ({"routes": [{"source": "*"}]}, "routes\\[0\\]"),
    ({"routes": [{"source": "*", "targets": ["a"], "extra": 1}]}, "unknown keys"),
    ({"branch_name_template": "{username}/{iid}"}, "per issue"),
    ({"target_overrides": {"a/b": {"branch_name_template": "x"}}}, "must contain"),
    ({"target_overrides": {"a/b": {"colour": "red"}}}, "unknown keys"),
])
def test_invalid_config_rejected(tmp_path, data, message):
    with pytest.raises(ValueError, match=message):
        Settings.load(write(tmp_path, data), env={})


def test_require():
    settings = Settings.load("/nonexistent.json", env={})
    with pytest.raises(ValueError, match="KEYVAULT_URL"):
        settings.require("keyvault_url")
