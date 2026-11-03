"""Minimal GitLab REST API (v4) client covering only what this project uses."""

from __future__ import annotations

import fnmatch
from urllib.parse import quote

import requests

# Hook settings applied to every webhook this project manages: issue events only.
HOOK_EVENTS = {
    "issues_events": True,
    "confidential_issues_events": True,
    "push_events": False,
    "tag_push_events": False,
    "merge_requests_events": False,
    "note_events": False,
    "confidential_note_events": False,
    "job_events": False,
    "pipeline_events": False,
    "wiki_page_events": False,
    "deployment_events": False,
    "releases_events": False,
    "enable_ssl_verification": True,
}


class GitLabError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitLab API error {status}: {message}")
        self.status = status
        self.message = message


class GitLabClient:
    def __init__(self, base_url: str, token: str, timeout: float = 8, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.api = self.base_url + "/api/v4"
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": token, "User-Agent": "gitlab-branch-automation"})

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _pid(project) -> str:
        return quote(str(project), safe="")

    def _send(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, self.api + path, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            try:
                body = resp.json()
                message = body.get("message") or body.get("error") or resp.text
            except ValueError:
                message = resp.text
            raise GitLabError(resp.status_code, str(message))
        return resp

    def _json(self, method: str, path: str, **kwargs):
        resp = self._send(method, path, **kwargs)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def _paginate(self, path: str, params: dict | None = None):
        params = dict(params or {}, per_page=100, page=1)
        while True:
            resp = self._send("GET", path, params=params)
            yield from resp.json()
            next_page = resp.headers.get("X-Next-Page")
            if not next_page:
                return
            params["page"] = int(next_page)

    # ------------------------------------------------------------------ users / projects
    def current_user(self) -> dict:
        return self._json("GET", "/user")

    def get_project(self, project) -> dict:
        return self._json("GET", f"/projects/{self._pid(project)}")

    def list_group_projects(self, group) -> list[dict]:
        return list(
            self._paginate(f"/groups/{self._pid(group)}/projects", {"include_subgroups": "true", "archived": "false"})
        )

    # ------------------------------------------------------------------ branches
    def get_branch(self, project, branch: str) -> dict | None:
        try:
            return self._json("GET", f"/projects/{self._pid(project)}/repository/branches/{quote(branch, safe='')}")
        except GitLabError as exc:
            if exc.status == 404:
                return None
            raise

    def resolve_ref(self, project, ref: str) -> str:
        """Return the branch to branch from.

        ``ref`` is either a literal branch name (``release``) or a glob such as
        ``release/*``, in which case the matching branch with the most recent
        commit is used.
        """
        if not any(ch in ref for ch in "*?["):
            if self.get_branch(project, ref) is None:
                raise GitLabError(404, f"Branch '{ref}' not found in {project}")
            return ref
        prefix = ref.split("*")[0].split("?")[0].split("[")[0]
        params = {"search": f"^{prefix}"} if prefix else {}
        matches = [
            b for b in self._paginate(f"/projects/{self._pid(project)}/repository/branches", params)
            if fnmatch.fnmatchcase(b["name"], ref)
        ]
        if not matches:
            raise GitLabError(404, f"No branch matching '{ref}' in {project}")
        matches.sort(key=lambda b: (b.get("commit") or {}).get("committed_date") or "", reverse=True)
        return matches[0]["name"]

    def create_branch(self, project, branch: str, ref: str) -> str:
        """Create ``branch`` from ``ref``. Returns ``"created"`` or ``"exists"``."""
        try:
            self._json("POST", f"/projects/{self._pid(project)}/repository/branches", data={"branch": branch, "ref": ref})
            return "created"
        except GitLabError as exc:
            if exc.status == 400 and "already exists" in exc.message.lower():
                return "exists"
            raise

    # ------------------------------------------------------------------ issues
    def add_issue_note(self, project, issue_iid: int, body: str) -> dict:
        return self._json("POST", f"/projects/{self._pid(project)}/issues/{issue_iid}/notes", data={"body": body})

    # ------------------------------------------------------------------ webhooks
    def list_hooks(self, project) -> list[dict]:
        return list(self._paginate(f"/projects/{self._pid(project)}/hooks"))

    def create_hook(self, project, url: str, token: str) -> dict:
        payload = {"url": url, "token": token, **HOOK_EVENTS}
        return self._json("POST", f"/projects/{self._pid(project)}/hooks", json=payload)

    def update_hook(self, project, hook_id: int, url: str, token: str) -> dict:
        payload = {"url": url, "token": token, **HOOK_EVENTS}
        return self._json("PUT", f"/projects/{self._pid(project)}/hooks/{hook_id}", json=payload)

    def delete_hook(self, project, hook_id: int) -> None:
        self._json("DELETE", f"/projects/{self._pid(project)}/hooks/{hook_id}")
