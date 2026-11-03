import json
from datetime import datetime, timedelta, timezone

from conftest import FakeStore, issue_payload
from shared.handler import WebhookHandler, build_secret_loaders
from shared.secret_store import CachedValue, previous_secret_is_valid


def make_handler(settings, fake_gitlab, store):
    secrets, _ = build_secret_loaders(settings, store)
    return WebhookHandler(settings, secrets, lambda: fake_gitlab)


def body(payload):
    return json.dumps(payload).encode()


def test_rejects_missing_and_wrong_token(settings, fake_gitlab):
    handler = make_handler(settings, fake_gitlab, FakeStore({"gitlab-webhook-secret": ("s3cret", {})}))
    assert handler.handle(None, b"{}")[0] == 401
    assert handler.handle("wrong", b"{}")[0] == 401
    assert fake_gitlab.created == []


def test_processes_assignment(settings, fake_gitlab):
    handler = make_handler(settings, fake_gitlab, FakeStore({"gitlab-webhook-secret": ("s3cret", {})}))
    status, result = handler.handle("s3cret", body(issue_payload("open", assignees=["alice"])))
    assert status == 200 and result["status"] == "processed"
    assert len(result["results"]) == 2


def test_ignores_non_assignment_and_bad_json(settings, fake_gitlab):
    handler = make_handler(settings, fake_gitlab, FakeStore({"gitlab-webhook-secret": ("s3cret", {})}))
    assert handler.handle("s3cret", body({"object_kind": "note"}))[1]["status"] == "ignored"
    assert handler.handle("s3cret", b"{not json")[0] == 400


def test_ignores_excluded_and_unrouted_repos(settings, fake_gitlab):
    handler = make_handler(settings, fake_gitlab, FakeStore({"gitlab-webhook-secret": ("s3cret", {})}))
    _, result = handler.handle("s3cret", body(issue_payload("open", assignees=["a"], project="grp/sandbox/x")))
    assert result["reason"] == "repo excluded"
    settings.routes = [{"source": "other/*", "targets": ["other/x"]}]
    _, result = handler.handle("s3cret", body(issue_payload("open", assignees=["a"])))
    assert result["reason"] == "no route for this repo"
    assert fake_gitlab.created == []


def test_picks_up_rotated_secret_without_restart(settings, fake_gitlab):
    store = FakeStore({"gitlab-webhook-secret": ("old", {})})
    clock = [0.0]
    secrets = CachedValue(build_secret_loaders(settings, store)[0]._loader, ttl=300, min_refresh_interval=30,
                          clock=lambda: clock[0])
    handler = WebhookHandler(settings, secrets, lambda: fake_gitlab)
    assert handler.is_authorized("old")
    store.set("gitlab-webhook-secret", "new")
    clock[0] = 31  # past the refresh rate limit, before the TTL
    assert handler.is_authorized("new")


def test_previous_secret_accepted_only_during_grace(settings, fake_gitlab):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store = FakeStore({"gitlab-webhook-secret": ("new", {}),
                       "gitlab-webhook-secret-previous": ("old", {"expires_at": future})})
    assert make_handler(settings, fake_gitlab, store).is_authorized("old")
    store.set("gitlab-webhook-secret-previous", "old", {"expires_at": past})
    assert not make_handler(settings, fake_gitlab, store).is_authorized("old")


def test_previous_secret_tag_parsing():
    assert not previous_secret_is_valid({})
    assert not previous_secret_is_valid({"expires_at": "garbage"})
    assert previous_secret_is_valid({"expires_at": "2999-01-01T00:00:00"})


def test_local_env_secret_bypasses_key_vault(settings, fake_gitlab):
    settings.webhook_secret = "local"
    assert make_handler(settings, fake_gitlab, None).is_authorized("local")


def test_deep_health(settings, fake_gitlab):
    handler = make_handler(settings, fake_gitlab, FakeStore({"gitlab-webhook-secret": ("s3cret", {})}))
    assert handler.deep_health("nope")[0] == 401
    status, result = handler.deep_health("s3cret")
    assert status == 200 and "automation-bot" in result["checks"]["gitlab"]


def test_cached_value_rate_limits_refresh():
    calls = []
    clock = [0.0]
    cache = CachedValue(lambda: calls.append(1) or len(calls), ttl=300, min_refresh_interval=30,
                        clock=lambda: clock[0])
    assert cache.get() == 1
    assert cache.get(refresh=True) == 1  # too soon
    clock[0] = 31
    assert cache.get(refresh=True) == 2
    clock[0] = 400
    assert cache.get() == 3
