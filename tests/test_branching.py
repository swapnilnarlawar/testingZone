import pytest

from shared.branching import render_branch_name, sanitize_ref, slugify, validate_template
from shared.events import AssignmentEvent

EVENT = AssignmentEvent(7, "grp/Pay Team/My App", 900, 42, "Fix: login bug!!", "", (), ())


def test_default_template():
    assert render_branch_name("feature/{project}-{iid}", EVENT) == "feature/my-app-42"


def test_all_placeholders():
    name = render_branch_name("{group}/{iid}-{id}-{title_slug}", EVENT)
    assert name == "pay-team/42-900-fix-login-bug"


def test_name_does_not_depend_on_assignee():
    other = AssignmentEvent(7, "grp/Pay Team/My App", 900, 42, "Fix: login bug!!", "", ("x",), ("x",))
    assert render_branch_name("feature/{project}-{iid}", EVENT) == render_branch_name("feature/{project}-{iid}", other)


@pytest.mark.parametrize("template,message", [
    ("{username}/{iid}", "branches are per issue"),
    ("{nope}-{iid}", "Unknown placeholder"),
    ("feature/{project}", "must contain"),
    ("feature/{iid", "Invalid"),
])
def test_invalid_templates(template, message):
    with pytest.raises(ValueError, match=message):
        validate_template(template)


@pytest.mark.parametrize("raw,expected", [
    ("a b/c", "a-b/c"),
    ("x..y", "x.y"),
    ("/lead//trail/", "lead/trail"),
    ("name.lock", "name"),
    (".hidden/ok", "hidden/ok"),
    ("we~ird^na:me?*[", "we-ird-na-me"),
])
def test_sanitize_ref(raw, expected):
    assert sanitize_ref(raw) == expected


def test_sanitize_ref_rejects_empty():
    with pytest.raises(ValueError):
        sanitize_ref("///")


def test_slugify_truncates():
    assert slugify("A" * 100, max_len=10) == "a" * 10
