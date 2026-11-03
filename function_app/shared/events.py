"""Turn a GitLab "Issue Hook" payload into an assignment event.

Only two situations count as an assignment:

* an issue is opened with one or more assignees (``action == "open"``)
* an issue is updated and its assignee list gained people (``action == "update"``
  with ``changes.assignees``); only the *newly added* people are returned, so
  re-saving an issue never re-creates branches for existing assignees.
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
    new_assignees: tuple[Assignee, ...]


def _to_assignee(user: dict) -> Assignee | None:
    if not user or not user.get("username"):
        return None
    return Assignee(id=user.get("id"), username=user["username"], name=user.get("name") or user["username"])


def _key(user: dict):
    return user.get("id") if user.get("id") is not None else user.get("username")


def parse_assignment_event(payload: dict, excluded: list[str] | None = None) -> AssignmentEvent | None:
    """Return the assignment event, or ``None`` if the payload should be ignored."""
    if not isinstance(payload, dict) or payload.get("object_kind") != "issue":
        return None

    attrs = payload.get("object_attributes") or {}
    action = attrs.get("action")

    if action == "open":
        added = payload.get("assignees") or []
    elif action == "update":
        change = (payload.get("changes") or {}).get("assignees")
        if not change:
            return None
        previous = {_key(u) for u in change.get("previous") or []}
        added = [u for u in change.get("current") or [] if _key(u) not in previous]
    else:
        return None

    excluded_set = {u.lower() for u in (excluded or [])}
    assignees = tuple(
        a for a in (_to_assignee(u) for u in added) if a and a.username.lower() not in excluded_set
    )
    if not assignees:
        return None

    project = payload.get("project") or {}
    return AssignmentEvent(
        project_id=project.get("id") or attrs.get("project_id"),
        project_path=project.get("path_with_namespace") or project.get("name") or "",
        issue_id=attrs.get("id"),
        issue_iid=attrs.get("iid"),
        issue_title=attrs.get("title") or "",
        issue_url=attrs.get("url") or "",
        new_assignees=assignees,
    )
