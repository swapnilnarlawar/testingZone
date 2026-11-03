import json

import pytest

from shared.config import DEFAULT_CONFIG_PATH, Settings


def test_shipped_config_loads():
    settings = Settings.load(DEFAULT_CONFIG_PATH, env={})
    assert settings.source_repos and settings.target_repos
    assert settings.release_branch == "release"


def test_env_overrides(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"target_repos": ["a/b"], "comment_on_issue": True}))
    settings = Settings.load(path, env={"TARGET_REPOS": "x/y, z/w", "COMMENT_ON_ISSUE": "false",
                                        "PREVIOUS_SECRET_GRACE_HOURS": "6", "KEYVAULT_URL": "https://kv"})
    assert settings.target_repos == ["x/y", "z/w"]
    assert settings.comment_on_issue is False
    assert settings.previous_secret_grace_hours == 6
    assert settings.keyvault_url == "https://kv"


def test_unknown_key_rejected(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"target_repo": ["typo"]}))
    with pytest.raises(ValueError, match="target_repo"):
        Settings.load(path, env={})


def test_require():
    settings = Settings.load("/nonexistent.json", env={})
    with pytest.raises(ValueError, match="KEYVAULT_URL"):
        settings.require("keyvault_url")
