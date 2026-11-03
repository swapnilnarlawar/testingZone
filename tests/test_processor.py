from shared.events import Assignee, AssignmentEvent
from shared.processor import process_assignment

EVENT = AssignmentEvent(7, "grp/app", 900, 42, "Fix", "", (Assignee(1, "alice", "Alice"), Assignee(2, "bob", "Bob")))


def test_creates_branch_per_assignee_per_target(settings, fake_gitlab):
    results = process_assignment(EVENT, fake_gitlab, settings)
    assert sorted(fake_gitlab.created) == [
        ("grp/app", "alice/app-42", "release"), ("grp/app", "bob/app-42", "release"),
        ("grp/lib", "alice/app-42", "release"), ("grp/lib", "bob/app-42", "release"),
    ]
    assert {r.status for r in results} == {"created"}
    (project, iid, body), = fake_gitlab.notes
    assert project == 7 and iid == 42 and "alice/app-42" in body


def test_existing_branch_reported_as_exists(settings, fake_gitlab):
    fake_gitlab.branches["grp/lib"]["alice/app-42"] = "old"
    results = process_assignment(EVENT, fake_gitlab, settings)
    statuses = {(r.repo, r.assignee): r.status for r in results}
    assert statuses[("grp/lib", "alice")] == "exists"
    assert statuses[("grp/app", "alice")] == "created"


def test_missing_release_branch_and_api_errors_do_not_stop_others(settings, fake_gitlab):
    del fake_gitlab.branches["grp/lib"]["release"]
    fake_gitlab.fail_create.add("grp/app")
    results = process_assignment(EVENT, fake_gitlab, settings)
    assert len(results) == 4 and all(r.status == "failed" for r in results)
    assert any("not found" in r.detail for r in results if r.repo == "grp/lib")
    assert any("403" in r.detail for r in results if r.repo == "grp/app")


def test_comment_can_be_disabled(settings, fake_gitlab):
    settings.comment_on_issue = False
    process_assignment(EVENT, fake_gitlab, settings)
    assert fake_gitlab.notes == []
