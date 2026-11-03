"""Create the per-assignee branches in every target repository."""

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
    assignee: str
    status: str  # created | exists | failed
    source_ref: str = ""
    detail: str = ""


def _resolve_refs(gitlab: GitLabClient, repos: list[str], ref: str) -> dict[str, str | GitLabError]:
    resolved: dict[str, str | GitLabError] = {}
    for repo in repos:
        try:
            resolved[repo] = gitlab.resolve_ref(repo, ref)
        except GitLabError as exc:
            resolved[repo] = exc
    return resolved


def process_assignment(event: AssignmentEvent, gitlab: GitLabClient, settings: Settings,
                       max_workers: int = 8) -> list[BranchResult]:
    refs = _resolve_refs(gitlab, settings.target_repos, settings.release_branch)

    jobs = []
    results: list[BranchResult] = []
    for assignee in event.new_assignees:
        branch = render_branch_name(settings.branch_name_template, event, assignee)
        for repo in settings.target_repos:
            ref = refs[repo]
            if isinstance(ref, GitLabError):
                results.append(BranchResult(repo, branch, assignee.username, "failed", settings.release_branch, ref.message))
            else:
                jobs.append((repo, branch, assignee.username, ref))

    def run(job):
        repo, branch, username, ref = job
        try:
            status = gitlab.create_branch(repo, branch, ref)
            return BranchResult(repo, branch, username, status, ref)
        except Exception as exc:  # report every failure, never abort the batch
            return BranchResult(repo, branch, username, "failed", ref, str(exc))

    if jobs:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(jobs))) as pool:
            results.extend(pool.map(run, jobs))

    for r in results:
        log = logger.warning if r.status == "failed" else logger.info
        log("%s %s in %s (from %s) %s", r.status, r.branch, r.repo, r.source_ref, r.detail)

    if settings.comment_on_issue and results:
        try:
            gitlab.add_issue_note(event.project_id, event.issue_iid, format_issue_note(results, gitlab.base_url))
        except Exception as exc:
            logger.warning("Could not comment on issue %s#%s: %s", event.project_path, event.issue_iid, exc)

    return results


_ICONS = {"created": ":white_check_mark: created", "exists": ":information_source: already existed",
          "failed": ":x: failed"}


def format_issue_note(results: list[BranchResult], gitlab_url: str) -> str:
    lines = ["**Branch automation**", "", "| Assignee | Repository | Branch | Result |", "|---|---|---|---|"]
    for r in sorted(results, key=lambda r: (r.assignee, r.repo)):
        branch = r.branch if r.status == "failed" else f"[`{r.branch}`]({gitlab_url}/{r.repo}/-/tree/{r.branch})"
        result = _ICONS.get(r.status, r.status)
        if r.status == "failed" and r.detail:
            result += f" ({r.detail})"
        else:
            result += f" from `{r.source_ref}`"
        lines.append(f"| @{r.assignee} | {r.repo} | {branch} | {result} |")
    return "\n".join(lines)
