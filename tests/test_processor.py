from shared.events import Assignee, AssignmentEvent
from shared.processor import process_assignment

ALICE, BOB = Assignee(1, "alice", "Alice"), Assignee(2, "bob", "Bob")


def event(project="grp/app", added=(ALICE, BOB)):
    return AssignmentEvent(7, project, 900, 42, "Fix", "", added, added)


def test_one_branch_per_issue_regardless_of_assignee_count(settings, fake_gitlab):
    results = process_assignment(event(), fake_gitlab, settings)
    assert sorted(fake_gitlab.created) == [("grp/app", "feature/app-42", "release"),
                                           ("grp/lib", "feature/app-42", "release")]
    assert {r.status for r in results} == {"created"}
    (project, iid, body), = fake_gitlab.notes
    assert project == 7 and iid == 42 and "feature/app-42" in body


def test_second_assignee_reuses_branch_and_does_not_comment(settings, fake_gitlab):
    process_assignment(event(added=(ALICE,)), fake_gitlab, settings)
    results = process_assignment(event(added=(BOB,)), fake_gitlab, settings)
    assert {r.status for r in results} == {"exists"}
    assert len(fake_gitlab.created) == 2 and len(fake_gitlab.notes) == 1


def test_routes_and_target_overrides(settings, fake_gitlab):
    fake_gitlab.branches["grp/pay/ledger"] = {"release": "x"}
    fake_gitlab.branches["grp/pay-api"] = {"release/1.0": "x"}
    fake_gitlab.resolve_ref = lambda repo, ref: "release/1.0" if ref == "release/*" else ref
    process_assignment(event("grp/pay/ledger"), fake_gitlab, settings)
    assert sorted(fake_gitlab.created) == [("grp/pay-api", "pay/42", "release/1.0"),
                                           ("grp/pay/ledger", "feature/ledger-42", "release")]


def test_failures_do_not_stop_other_targets(settings, fake_gitlab):
    del fake_gitlab.branches["grp/lib"]["release"]
    fake_gitlab.fail_create.add("grp/app")
    results = {r.repo: r for r in process_assignment(event(), fake_gitlab, settings)}
    assert results["grp/lib"].status == "failed" and "not found" in results["grp/lib"].detail
    assert results["grp/app"].status == "failed" and "403" in results["grp/app"].detail
    assert len(fake_gitlab.notes) == 1  # failures are reported on the issue


def test_comment_can_be_disabled(settings, fake_gitlab):
    settings.comment_on_issue = False
    process_assignment(event(), fake_gitlab, settings)
    assert fake_gitlab.notes == []
