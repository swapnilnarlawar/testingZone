"""Create the issue's branch in every target repository routed from the source repo."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .branching import render_branch_name
from .config import Settings
from .events import AssignmentEvent
from .gitlab_client import GitLabClient, GitLabError

logger = logging.getLogger(__name__)


@dataclass
class BranchResult:
    repo: str
    branch: str
    status: str  # created | exists | failed
    source_ref: str = ""
    detail: str = ""


def _create_in_target(gitlab: GitLabClient, settings: Settings, event: AssignmentEvent, repo: str) -> BranchResult:
    release, template = settings.target_settings(repo)
    branch = ""
    try:
        branch = render_branch_name(template, event)
        # Cheap check first: on a second assignment the branch is already there.
        if gitlab.get_branch(repo, branch) is not None:
            return BranchResult(repo, branch, "exists")
        ref = gitlab.resolve_ref(repo, release)
        return BranchResult(repo, branch, gitlab.create_branch(repo, branch, ref), ref)
    except GitLabError as exc:
        return BranchResult(repo, branch, "failed", release, exc.message)
    except Exception as exc:  # report every failure, never abort the batch
        return BranchResult(repo, branch, "failed", release, str(exc))


def process_assignment(event: AssignmentEvent, gitlab: GitLabClient, settings: Settings,
                       max_workers: int = 8) -> list[BranchResult]:
    targets = settings.targets_for(event.project_path)
    if not targets:
        return []

    with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as pool:
        results = list(pool.map(lambda repo: _create_in_target(gitlab, settings, event, repo), targets))

    for r in results:
        log = logger.warning if r.status == "failed" else logger.info
        log("%s %s in %s (from %s) %s", r.status, r.branch, r.repo, r.source_ref or "-", r.detail)

    # Comment only when something changed or went wrong: a second assignee does not spam the issue.
    if settings.comment_on_issue and any(r.status != "exists" for r in results):
        try:
            gitlab.add_issue_note(event.project_id, event.issue_iid, format_issue_note(results, gitlab.base_url))
        except Exception as exc:
            logger.warning("Could not comment on issue %s#%s: %s", event.project_path, event.issue_iid, exc)

    return results


_ICONS = {"created": ":white_check_mark: created", "exists": ":information_source: already existed",
          "failed": ":x: failed"}


def format_issue_note(results: list[BranchResult], gitlab_url: str) -> str:
    lines = ["**Branch automation**: branches for this issue", "",
             "| Repository | Branch | Result |", "|---|---|---|"]
    for r in sorted(results, key=lambda r: r.repo):
        branch = f"`{r.branch}`" if r.status == "failed" else f"[`{r.branch}`]({gitlab_url}/{r.repo}/-/tree/{r.branch})"
        result = _ICONS.get(r.status, r.status)
        if r.status == "failed":
            result += f" ({r.detail})" if r.detail else ""
        elif r.status == "created":
            result += f" from `{r.source_ref}`"
        lines.append(f"| {r.repo} | {branch} | {result} |")
    return "\n".join(lines)
