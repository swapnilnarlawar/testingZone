# Configuration reference

There are three places configuration lives. Nothing secret is in any of them.

| Where | What | Who reads it |
|---|---|---|
| `function_app/config/automation.json` (in Git) | How the automation behaves | Function and scripts |
| Function App settings (set by Bicep) | `KEYVAULT_URL`, `AZURE_CLIENT_ID` | Function |
| GitHub variables / local `.env` | `KEYVAULT_URL`, `WEBHOOK_URL` | Scripts and workflows |
| **Key Vault** | GitLab token, webhook secret | Function and scripts, via managed identity |

## automation.json

| Key | Default | Description |
|---|---|---|
| `gitlab_url` | `https://gitlab.com` | Base URL of your GitLab instance |
| `source_repos` | `[]` | Projects where issues are assigned. Each gets a webhook |
| `target_repos` | `[]` | Projects where branches are created |
| `release_branch` | `release` | Branch to cut from. A glob such as `release/*` picks the matching branch with the newest commit, per repo |
| `branch_name_template` | `{username}/{project}-{iid}` | See below |
| `comment_on_issue` | `true` | Post the list of branches as a comment on the issue |
| `excluded_assignees` | `[]` | Usernames that never get branches (bots, for example) |
| `gitlab_token_secret_name` | `gitlab-api-token` | Key Vault secret holding the GitLab token |
| `webhook_secret_name` | `gitlab-webhook-secret` | Key Vault secret holding the webhook secret |
| `previous_secret_grace_hours` | `24` | After a rotation, how long the old webhook secret is still accepted |

Unknown keys are rejected (catches typos). CI validates the file on every PR.

### Branch name placeholders

| Placeholder | Example | Meaning |
|---|---|---|
| `{username}` | `alice` | GitLab username of the new assignee |
| `{iid}` | `42` | Issue number as shown in GitLab (`#42`) |
| `{id}` | `90817` | Global issue id |
| `{project}` | `backend` | Slug of the project the issue is in |
| `{title_slug}` | `fix-login-timeout` | Issue title, lowercased, max 40 chars |

Examples:

| Template | Result |
|---|---|
| `{username}/{project}-{iid}` (default) | `alice/backend-42` |
| `feature/{username}/{iid}-{title_slug}` | `feature/alice/42-fix-login-timeout` |
| `{username}/issue-{iid}` | `alice/issue-42` (may clash if two source repos share issue numbers) |

The result is cleaned up to be a valid git branch name.

## Environment variable overrides

Every key above can be overridden by an environment variable of the same name
in upper case, for example `TARGET_REPOS=grp/a,grp/b` or `COMMENT_ON_ISSUE=false`.
Lists are comma separated. This is handy for a one-off script run; for permanent
changes, edit the JSON file so the change is reviewed and versioned.

| Variable | Used by | Description |
|---|---|---|
| `KEYVAULT_URL` | function, scripts | Key Vault URL |
| `WEBHOOK_URL` | scripts | Function webhook URL, `https://<app>.azurewebsites.net/api/gitlab-webhook` |
| `AZURE_CLIENT_ID` | function (scripts optional) | Client id of the managed identity to authenticate as |
| `AUTOMATION_CONFIG` | function, scripts | Use a different config file |
| `GITLAB_TOKEN`, `WEBHOOK_SECRET` | local dev only | Bypass Key Vault. Never set these in Azure or GitHub |

## Authentication

* **Function → Key Vault**: the User Assigned Managed Identity (`AZURE_CLIENT_ID`).
* **GitHub Actions → Azure**: OIDC federation to the same identity. The
  federated credential trusts only `repo:<owner>/<repo>:ref:refs/heads/main`,
  so workflows from other branches or forks cannot log in.
* **Your machine → Key Vault**: your `az login` account (granted Secrets Officer by `deploy.sh`).
* **GitLab → Function**: GitLab sends the webhook secret in the `X-Gitlab-Token`
  header; the function compares it in constant time against the secret in Key
  Vault (and the previous one during the grace period). The secret is cached for
  5 minutes and re-read immediately if a call fails to match, so rotations need
  no restart.
* **Function/scripts → GitLab**: the token stored in Key Vault.

If you want separate identities for runtime and deployment, create a second
UAMI in `main.bicep`, give it the GitHub federation and *Website Contributor*,
and keep *Key Vault Secrets User* (read-only) on the function's identity.
