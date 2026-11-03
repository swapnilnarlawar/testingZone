# GitLab Branch Automation

When an issue anywhere in your GitLab group is assigned, a branch for that
issue is created in each repository routed to it, cut from the release branch.
The branches are posted back to the issue as a comment.

```
 Issue #42 in my-group/web assigned (to one person or several)
          │  Issue Hook (X-Gitlab-Token = webhook secret)
          ▼
 Azure Function  /api/gitlab-webhook ──── reads secrets ───► Azure Key Vault
          │       (runs as a User Assigned Managed Identity)
          │  GitLab API
          ▼
 feature/web-42  created from `release` in every routed target repo
 + comment on the issue listing the branches
```

Supporting pieces:

| Piece | What it does |
|---|---|
| `function_app/` | Azure Function (Python) that receives the webhook and creates the branches |
| `function_app/config/automation.json` | **The one file you edit**: watched groups, routes to target repos, release branch, naming per repo |
| `scripts/webhooks.py` | Ops CLI: store the GitLab token, create/verify/rotate/clean up webhooks |
| `infra/` | Bicep template + `deploy.sh` that create every Azure resource |
| `.github/workflows/` | CI, function deployment, and scheduled sync / verify / rotate / cleanup jobs |
| `docs/` | Deployment runbook, configuration reference, operations guide, troubleshooting |

## How it behaves

* **Watching**: every project in the configured GitLab groups (subgroups
  included) gets a project webhook, minus any you exclude. A daily sync job adds
  the webhook to newly created repos.
* **Trigger**: an issue is opened with assignees, or someone is added to an
  issue's assignees. Unassigning, closing and other edits do nothing.
* **One branch per issue**: the name comes from the issue, never the assignee,
  so multiple assignees share one branch per repo. A second assignee or a
  reassignment finds the branch already there and nothing new is created.
* **Where**: `routes` map source repos (or patterns such as `my-group/payments/*`)
  to their own list of target repos; `{source}` means the issue's own repo.
* **Branch name**: `feature/{project}-{iid}` by default, for example
  `feature/web-42`, with per-target-repo overrides of the naming and the release
  branch. See [CONFIGURATION.md](docs/CONFIGURATION.md).
* **Source branch**: `release`, or a pattern like `release/*` to use the most
  recently updated matching branch in each repo.
* **Existing branches** are never touched.
* **Failures** in one repo never stop the others; every result is logged and
  listed in the issue comment.
* **Security**: no secrets in code, GitHub, or app settings. The GitLab token
  and webhook secret live only in Key Vault, are read by the managed identity,
  and the webhook secret is generated and rotated by script without ever being
  printed. GitHub Actions logs in to Azure with OIDC federation (no client secret).

## Quick start

Full step-by-step instructions are in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. In short:

```bash
# 1. Set your groups, routes and release branch
$EDITOR function_app/config/automation.json

# 2. Create the Azure resources (prints the GitHub secrets/variables to set)
az login
./infra/deploy.sh -g rg-gitlab-automation -r <github-owner>/<this-repo>

# 3. Set the GitHub secrets/variables printed by the script, then push to main
#    -> the "Deploy Function" workflow deploys the code

# 4. Store the GitLab token in Key Vault and create the webhooks
pip install -r scripts/requirements.txt
cp .env.example .env            # fill in KEYVAULT_URL and WEBHOOK_URL
python scripts/webhooks.py store-token
python scripts/webhooks.py setup
python scripts/webhooks.py verify
```

Then assign an issue in one of the watched repos and watch the branches appear.

## Scheduled jobs

| Workflow | Schedule (UTC) | Action |
|---|---|---|
| Webhook Sync | Daily 06:00 | Adds the webhook to repos newly created in the watched groups, repairs disabled hooks |
| Webhook Verification | Mondays 09:00 | Checks webhooks, routes, release branches, and the function end to end |
| Secret Rotation | 1st of each month 02:00 | New webhook secret in Key Vault and on every webhook (old one valid 24h) |
| Webhook Cleanup | 1st of Jan/Apr/Jul/Oct 03:00 | Lists webhooks on excluded repos and duplicates (deletes only when run manually with *apply*) |
| Deploy Function | On push to `main` touching `function_app/` | Tests, deploys, smoke-tests |
| CI | Every PR and push | Unit tests and config validation |

Results appear in each run's job summary in the GitHub Actions tab, and GitHub
emails you when a scheduled run fails.

## Documentation

* [Deployment runbook](docs/DEPLOYMENT.md): first-time setup, end to end
* [Configuration reference](docs/CONFIGURATION.md): every setting and where it lives
* [Operations guide](docs/OPERATIONS.md): day-to-day use of the CLI and workflows
* [Troubleshooting](docs/TROUBLESHOOTING.md): common problems and fixes

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

To run the function locally with Azure Functions Core Tools, copy
`function_app/local.settings.json.example` to `function_app/local.settings.json`,
then `cd function_app && func start`.
