import pytest

from shared.branching import render_branch_name, sanitize_ref, slugify
from shared.events import Assignee, AssignmentEvent

EVENT = AssignmentEvent(7, "grp/My App", 900, 42, "Fix: login bug!!", "", ())
ALICE = Assignee(1, "alice.smith", "Alice")


def test_default_template():
    assert render_branch_name("{username}/{project}-{iid}", EVENT, ALICE) == "alice.smith/my-app-42"


def test_all_placeholders():
    name = render_branch_name("feature/{username}/{iid}-{id}-{title_slug}", EVENT, ALICE)
    assert name == "feature/alice.smith/42-900-fix-login-bug"


def test_unknown_placeholder():
    with pytest.raises(ValueError, match="Unknown placeholder"):
        render_branch_name("{user}/{iid}", EVENT, ALICE)


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
