import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "function_app"))
sys.path.insert(0, str(ROOT / "scripts"))

from shared.config import Settings  # noqa: E402
from shared.gitlab_client import GitLabError  # noqa: E402


class FakeGitLab:
    """In-memory stand-in for GitLabClient."""

    base_url = "https://gitlab.example.com"

    def __init__(self, branches=None, hooks=None):
        # branches: {repo: {branch_name: committed_date}}
        self.branches = branches or {}
        self.hooks = hooks or {}
        self.notes = []
        self.created = []
        self.fail_create = set()
        self._next_hook = 100

    def current_user(self):
        return {"username": "automation-bot"}

    def resolve_ref(self, repo, ref):
        if repo not in self.branches:
            raise GitLabError(404, "404 Project Not Found")
        if ref not in self.branches[repo]:
            raise GitLabError(404, f"Branch '{ref}' not found in {repo}")
        return ref

    def create_branch(self, repo, branch, ref):
        if repo in self.fail_create:
            raise GitLabError(403, "403 Forbidden")
        if branch in self.branches[repo]:
            return "exists"
        self.branches[repo][branch] = "now"
        self.created.append((repo, branch, ref))
        return "created"

    def add_issue_note(self, project, iid, body):
        self.notes.append((project, iid, body))

    def list_hooks(self, repo):
        return [dict(h) for h in self.hooks.get(repo, [])]

    def create_hook(self, repo, url, token):
        self._next_hook += 1
        hook = {"id": self._next_hook, "url": url, "token": token, "issues_events": True}
        self.hooks.setdefault(repo, []).append(hook)
        return hook

    def update_hook(self, repo, hook_id, url, token):
        for h in self.hooks[repo]:
            if h["id"] == hook_id:
                h.update(url=url, token=token)
                return h
        raise GitLabError(404, "hook not found")

    def delete_hook(self, repo, hook_id):
        self.hooks[repo] = [h for h in self.hooks[repo] if h["id"] != hook_id]

    def list_group_projects(self, group):
        return [{"path_with_namespace": r} for r in self.hooks if r.startswith(group + "/")]


class FakeStore:
    def __init__(self, data=None):
        self.data = dict(data or {})  # name -> (value, tags)

    def get(self, name):
        return self.data[name][0] if name in self.data else None

    def get_with_tags(self, name):
        return self.data.get(name)

    def set(self, name, value, tags=None):
        self.data[name] = (value, dict(tags or {}))


@pytest.fixture
def settings():
    return Settings.load(path="/nonexistent.json", env={
        "SOURCE_REPOS": "grp/app",
        "TARGET_REPOS": "grp/app,grp/lib",
        "WEBHOOK_URL": "https://func.example.net/api/gitlab-webhook",
        "KEYVAULT_URL": "https://kv.vault.azure.net/",
    })


@pytest.fixture
def fake_gitlab():
    return FakeGitLab(branches={"grp/app": {"release": "2026-01-01"}, "grp/lib": {"release": "2026-01-01"}})


def issue_payload(action="update", previous=(), current=(), assignees=None):
    def users(names):
        return [{"id": abs(hash(n)) % 10000, "username": n, "name": n.title()} for n in names]

    payload = {
        "object_kind": "issue",
        "project": {"id": 7, "path_with_namespace": "grp/app"},
        "object_attributes": {"id": 900, "iid": 42, "title": "Fix login bug!", "action": action,
                              "url": "https://gitlab.example.com/grp/app/-/issues/42"},
        "assignees": users(assignees if assignees is not None else current),
    }
    if action == "update":
        payload["changes"] = {"assignees": {"previous": users(previous), "current": users(current)}}
    return payload
