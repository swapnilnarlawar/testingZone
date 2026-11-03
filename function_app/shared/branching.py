"""Branch name rendering and git ref sanitising."""

from __future__ import annotations

import re

from .events import Assignee, AssignmentEvent

PLACEHOLDERS = ("username", "iid", "id", "project", "title_slug")


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:max_len].rstrip("-")


def sanitize_ref(name: str) -> str:
    """Make ``name`` a valid git branch name (see ``git check-ref-format``)."""
    name = re.sub(r"[\s~^:?*\[\\\x00-\x1f\x7f]+", "-", name)
    name = name.replace("@{", "-")
    name = re.sub(r"\.{2,}", ".", name)
    parts = []
    for part in name.split("/"):
        part = part.strip(".-")
        while part.endswith(".lock"):
            part = part[: -len(".lock")].rstrip(".-")
        if part:
            parts.append(part)
    result = "/".join(parts)[:200].rstrip("/.")
    if not result or result == "@":
        raise ValueError(f"Cannot build a valid branch name from {name!r}")
    return result


def render_branch_name(template: str, event: AssignmentEvent, assignee: Assignee) -> str:
    values = {
        "username": assignee.username,
        "iid": event.issue_iid,
        "id": event.issue_id,
        "project": slugify(event.project_path.split("/")[-1]) or "project",
        "title_slug": slugify(event.issue_title) or "issue",
    }
    try:
        name = template.format(**values)
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"Unknown placeholder {exc} in branch_name_template; allowed: {', '.join(PLACEHOLDERS)}"
        ) from exc
    return sanitize_ref(name)
