# Configuration reference

Configuration lives in four places. None of them holds anything secret.

| Where | What | Who reads it |
|---|---|---|
| `function_app/config/automation.json` (in Git) | How the automation behaves | Function and scripts |
| Function App settings (set by Bicep) | `KEYVAULT_URL`, `AZURE_CLIENT_ID` | Function |
| GitHub variables / local `.env` | `KEYVAULT_URL`, `WEBHOOK_URL` | Scripts and workflows |
| **Key Vault** | GitLab token, webhook secret | Function and scripts, via managed identity |

Changes to `automation.json` take effect when merged to `main` (the Deploy
Function workflow redeploys). CI rejects an invalid file on the pull request.

## A complete example

```json
{
  "gitlab_url": "https://gitlab.com",

  "source_groups": ["my-group"],
  "source_repos": ["other-group/tooling"],
  "exclude_repos": ["my-group/sandbox/*", "my-group/archived-*"],

  "routes": [
    { "source": "my-group/payments/*",
      "targets": ["{source}", "my-group/payments/payments-api", "my-group/shared-config"] },
    { "source": "*",
      "targets": ["{source}", "my-group/backend", "my-group/frontend"] }
  ],

  "release_branch": "release",
  "branch_name_template": "feature/{project}-{iid}",

  "target_overrides": {
    "my-group/shared-config": { "branch_name_template": "issue/{group}-{project}-{iid}" },
    "my-group/legacy/*":      { "release_branch": "release/*", "branch_name_template": "{iid}-{title_slug}" }
  },

  "comment_on_issue": true
}
```

What this does, for issue #42 in `my-group/payments/ledger`:

| Repo | Branch | Cut from |
|---|---|---|
| `my-group/payments/ledger` (the issue's own repo, `{source}`) | `feature/ledger-42` | `release` |
| `my-group/payments/payments-api` | `feature/ledger-42` | `release` |
| `my-group/shared-config` (override) | `issue/payments-ledger-42` | `release` |

And for issue #7 in `my-group/web`, the catch-all route applies: `feature/web-7`
in `my-group/web`, `my-group/backend` and `my-group/frontend`.

## 1. Which repos are watched

| Key | Default | Description |
|---|---|---|
| `source_groups` | `[]` | Every non-archived project in these groups, **including subgroups**, gets the webhook. New projects are picked up by the daily *Webhook Sync* job (or `webhooks.py setup`) |
| `source_repos` | `[]` | Extra individual projects to watch, for example outside those groups |
| `exclude_repos` | `[]` | Projects never watched (path or glob). The function also ignores events from them |

Patterns are case-insensitive globs on the full project path: `my-group/sandbox/*`
matches everything below `sandbox`, `*-archive` matches any path ending in `-archive`.

Why not a group webhook? Group webhooks need GitLab Premium, which isn't
available here, so the sync job puts a project webhook on every repo in the
group instead. A repo created in the group is covered at the next sync run;
run `python scripts/webhooks.py setup` (or the *Webhook Sync* workflow) to
cover it immediately.

## 2. Where branches are created: `routes`

`routes` is an ordered list. For an issue in project *P*, the **first** route
whose `source` pattern matches *P* decides the target repos. If no route
matches, the issue is ignored (and `verify` warns about that repo).

| Field | Description |
|---|---|
| `source` | Path or glob matched against the issue's project. Use `"*"` as a final catch-all |
| `targets` | Repos where the branch is created. `"{source}"` means the issue's own repo |

Put specific routes first and the catch-all last.

## 3. Branch names and release branches

One branch is created **per issue** in each target repo. The name is built from
the issue only, never from who is assigned. So:

* an issue with three assignees gets one branch per target repo
* adding a second assignee later, or reassigning the issue, finds the branch
  already there and creates nothing (and posts no new comment)
* unassigning never deletes anything

| Key | Default | Description |
|---|---|---|
| `release_branch` | `release` | Branch to cut from. A glob such as `release/*` uses the matching branch with the newest commit in that repo |
| `branch_name_template` | `feature/{project}-{iid}` | Default naming convention, see placeholders below |
| `target_overrides` | `{}` | Per target repo (path or glob): its own `release_branch` and/or `branch_name_template`. First matching pattern wins |

Placeholders (all describe the **issue**, not the target repo):

| Placeholder | Example | Meaning |
|---|---|---|
| `{iid}` | `42` | Issue number as shown in GitLab (`#42`) |
| `{id}` | `90817` | Global issue id, unique across the whole GitLab instance |
| `{project}` | `ledger` | Slug of the project the issue is in |
| `{group}` | `payments` | Slug of that project's parent group |
| `{title_slug}` | `fix-login-timeout` | Issue title, lowercased, max 40 characters |

Rules, checked when the config loads:

* the template must contain `{iid}` or `{id}`, so names are unique per issue
* `{username}` is not allowed, because branches are per issue
* if issues from different repos route to the same target, include `{project}`
  (or use `{id}`) so `#42` from two repos does not collide

`{title_slug}` is readable but the name changes if someone renames the issue;
a later assignment would then create a second branch. Prefer it only where
titles are stable.

The result is cleaned up to be a valid git branch name.

## 4. Other settings

| Key | Default | Description |
|---|---|---|
| `gitlab_url` | `https://gitlab.com` | Base URL of your GitLab instance |
| `comment_on_issue` | `true` | Post a comment listing the branches when any are created or fail |
| `gitlab_token_secret_name` | `gitlab-api-token` | Key Vault secret holding the GitLab token |
| `webhook_secret_name` | `gitlab-webhook-secret` | Key Vault secret holding the webhook secret |
| `previous_secret_grace_hours` | `24` | After a rotation, how long the old webhook secret is still accepted |

Unknown keys are rejected, which catches typos.

## Environment variables

Simple keys can be overridden by an environment variable with the same name in
upper case, for example `SOURCE_GROUPS=grp-a,grp-b` or `COMMENT_ON_ISSUE=false`
(lists are comma separated). `routes` and `target_overrides` can only be set in
the file. Use overrides for one-off script runs; make permanent changes in the file.

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
* **Function/scripts → GitLab**: the token stored in Key Vault. Watching a whole
  group means the token needs **Maintainer** on every project in it (to manage
  webhooks), which a group access token on that group gives.

If you want separate identities for runtime and deployment, create a second
UAMI in `main.bicep`, give it the GitHub federation and *Website Contributor*,
and keep *Key Vault Secrets User* (read-only) on the function's identity.
