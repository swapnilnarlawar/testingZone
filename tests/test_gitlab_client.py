import pytest

from shared.gitlab_client import GitLabClient, GitLabError


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.content = b"x" if body is not None else b""
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def client(*responses):
    session = FakeSession(responses)
    return GitLabClient("https://gl.example.com/", "tok", session=session), session


def test_project_paths_are_url_encoded():
    gl, session = client(FakeResponse(200, {"name": "release"}))
    gl.get_branch("grp/sub/app", "feature/x")
    assert session.calls[0][1] == "https://gl.example.com/api/v4/projects/grp%2Fsub%2Fapp/repository/branches/feature%2Fx"
    assert session.headers["PRIVATE-TOKEN"] == "tok"


def test_create_branch_created_and_exists():
    gl, _ = client(FakeResponse(201, {"name": "b"}), FakeResponse(400, {"message": "Branch already exists"}))
    assert gl.create_branch("g/p", "b", "release") == "created"
    assert gl.create_branch("g/p", "b", "release") == "exists"


def test_create_branch_other_error_raises():
    gl, _ = client(FakeResponse(400, {"message": "Invalid reference name"}))
    with pytest.raises(GitLabError, match="Invalid reference"):
        gl.create_branch("g/p", "b", "nope")


def test_resolve_literal_ref_missing():
    gl, _ = client(FakeResponse(404, {"message": "404 Branch Not Found"}))
    with pytest.raises(GitLabError, match="not found"):
        gl.resolve_ref("g/p", "release")


def test_resolve_glob_picks_latest_across_pages():
    page1 = [{"name": "release/1.0", "commit": {"committed_date": "2026-01-01T00:00:00Z"}},
             {"name": "release-notes", "commit": {"committed_date": "2026-09-01T00:00:00Z"}}]
    page2 = [{"name": "release/1.1", "commit": {"committed_date": "2026-03-01T00:00:00Z"}}]
    gl, session = client(FakeResponse(200, page1, {"X-Next-Page": "2"}), FakeResponse(200, page2))
    assert gl.resolve_ref("g/p", "release/*") == "release/1.1"
    assert session.calls[0][2]["params"]["search"] == "^release/"
    assert session.calls[1][2]["params"]["page"] == 2


def test_hook_payload_only_issue_events():
    gl, session = client(FakeResponse(201, {"id": 1}))
    gl.create_hook("g/p", "https://f/api/gitlab-webhook", "secret")
    payload = session.calls[0][2]["json"]
    assert payload["issues_events"] and payload["confidential_issues_events"]
    assert payload["push_events"] is False and payload["enable_ssl_verification"] is True
