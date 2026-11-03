"""Branch name rendering and git ref sanitising.

Branch names are built from the issue only (never from the assignee), so every
assignment of the same issue maps to the same branch name and the branch is
created exactly once per issue and target repo.
"""

from __future__ import annotations

import re
import string

from .events import AssignmentEvent

PLACEHOLDERS = ("iid", "id", "project", "group", "title_slug")


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


def validate_template(template: str) -> None:
    """Reject templates with unknown placeholders or without the issue number."""
    try:
        fields = {f for _, f, _, _ in string.Formatter().parse(template) if f is not None}
    except ValueError as exc:
        raise ValueError(f"Invalid branch_name_template {template!r}: {exc}") from exc
    unknown = fields - set(PLACEHOLDERS)
    if unknown:
        hint = " ({username} is not allowed: branches are per issue)" if "username" in unknown else ""
        raise ValueError(
            f"Unknown placeholder(s) {', '.join(sorted(unknown))} in branch_name_template {template!r}{hint}; "
            f"allowed: {', '.join(PLACEHOLDERS)}"
        )
    if not fields & {"iid", "id"}:
        raise ValueError(f"branch_name_template {template!r} must contain {{iid}} or {{id}} to be unique per issue")


def render_branch_name(template: str, event: AssignmentEvent) -> str:
    parts = event.project_path.split("/")
    values = {
        "iid": event.issue_iid,
        "id": event.issue_id,
        "project": slugify(parts[-1]) or "project",
        "group": slugify(parts[-2]) if len(parts) > 1 else "group",
        "title_slug": slugify(event.issue_title) or "issue",
    }
    validate_template(template)
    return sanitize_ref(template.format(**values))
