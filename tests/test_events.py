from conftest import issue_payload
from shared.events import parse_assignment_event


def names(event):
    return [a.username for a in event.new_assignees]


def test_open_with_assignees():
    event = parse_assignment_event(issue_payload("open", assignees=["alice", "bob"]))
    assert names(event) == ["alice", "bob"]
    assert event.issue_iid == 42 and event.project_path == "grp/app" and event.project_id == 7


def test_open_without_assignees_ignored():
    assert parse_assignment_event(issue_payload("open", assignees=[])) is None


def test_update_returns_only_newly_added():
    event = parse_assignment_event(issue_payload("update", previous=["alice"], current=["alice", "bob"]))
    assert names(event) == ["bob"]


def test_unassign_ignored():
    assert parse_assignment_event(issue_payload("update", previous=["alice", "bob"], current=["alice"])) is None


def test_update_without_assignee_change_ignored():
    payload = issue_payload("update", previous=["alice"], current=["alice", "bob"])
    payload["changes"] = {"title": {"previous": "a", "current": "b"}}
    assert parse_assignment_event(payload) is None


def test_other_actions_and_kinds_ignored():
    assert parse_assignment_event(issue_payload("close", assignees=["alice"])) is None
    assert parse_assignment_event({"object_kind": "push"}) is None
    assert parse_assignment_event("not a dict") is None


def test_excluded_assignees():
    payload = issue_payload("open", assignees=["alice", "Renovate-Bot"])
    assert names(parse_assignment_event(payload, excluded=["renovate-bot"])) == ["alice"]
    assert parse_assignment_event(issue_payload("open", assignees=["renovate-bot"]), ["renovate-bot"]) is None
