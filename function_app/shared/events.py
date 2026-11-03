"""Turn a GitLab "Issue Hook" payload into an assignment event.

Two situations count as an assignment:

* an issue is opened with one or more assignees (``action == "open"``)
* an issue is updated and people were added to its assignees (``action ==
  "update"`` with ``changes.assignees`` gaining someone)

Branches are created once per issue, not per assignee, and their names do not
depend on who is assigned. So a second, third ... assignee, or a reassignment,
finds the branches already there and nothing new is created. Unassigning,
closing and other edits are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assignee:
    id: int
    username: str
    name: str


@dataclass(frozen=True)
class AssignmentEvent:
    project_id: int
    project_path: str
    issue_id: int
    issue_iid: int
    issue_title: str
    issue_url: str
    assignees: tuple[Assignee, ...]  # everyone assigned after this event
    added: tuple[Assignee, ...]      # who was added by this event


def _to_assignee(user: dict) -> Assignee | None:
    if not user or not user.get("username"):
        return None
    return Assignee(id=user.get("id"), username=user["username"], name=user.get("name") or user["username"])


def _key(user: dict):
    return user.get("id") if user.get("id") is not None else user.get("username")


def _assignees(users) -> tuple[Assignee, ...]:
    return tuple(a for a in (_to_assignee(u) for u in users or []) if a)


def parse_assignment_event(payload: dict) -> AssignmentEvent | None:
    """Return the assignment event, or ``None`` if the payload should be ignored."""
    if not isinstance(payload, dict) or payload.get("object_kind") != "issue":
        return None

    attrs = payload.get("object_attributes") or {}
    action = attrs.get("action")

    if action == "open":
        current = payload.get("assignees") or []
        added = current
    elif action == "update":
        change = (payload.get("changes") or {}).get("assignees")
        if not change:
            return None
        current = change.get("current") or []
        previous = {_key(u) for u in change.get("previous") or []}
        added = [u for u in current if _key(u) not in previous]
    else:
        return None

    added_assignees = _assignees(added)
    if not added_assignees:
        return None

    project = payload.get("project") or {}
    return AssignmentEvent(
        project_id=project.get("id") or attrs.get("project_id"),
        project_path=project.get("path_with_namespace") or project.get("name") or "",
        issue_id=attrs.get("id"),
        issue_iid=attrs.get("iid"),
        issue_title=attrs.get("title") or "",
        issue_url=attrs.get("url") or "",
        assignees=_assignees(current),
        added=added_assignees,
    )
