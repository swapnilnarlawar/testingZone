# GitLab Branch Automation

When a GitLab issue is assigned to someone, a branch is created for that person
in each configured repository, cut from the release branch. The branches are
posted back to the issue as a comment.

```
 GitLab issue assigned to @alice
          │  Issue Hook (X-Gitlab-Token = webhook secret)
          ▼
 Azure Function  /api/gitlab-webhook ──── reads secrets ───► Azure Key Vault
          │       (runs as a User Assigned Managed Identity)
          │  GitLab API
          ▼
 alice/backend-42  created from `release` in every target repo
 + comment on the issue listing the branches
```

Supporting pieces:

| Piece | What it does |
|---|---|
| `function_app/` | Azure Function (Python) that receives the webhook and creates the branches |
| `function_app/config/automation.json` | **The one file you edit**: source repos, target repos, release branch, branch naming |
| `scripts/webhooks.py` | Ops CLI: store the GitLab token, create/verify/rotate/clean up webhooks |
| `infra/` | Bicep template + `deploy.sh` that create every Azure resource |
| `.github/workflows/` | CI, function deployment, and scheduled verify / rotate / cleanup jobs |
| `docs/` | Deployment runbook, configuration reference, operations guide, troubleshooting |

## How it behaves

* **Trigger**: an issue is opened with assignees, or people are added to an
  issue's assignees. Only the *newly added* people get branches, so editing an
  issue never re-creates anything. Unassigning does nothing.
* **Branch name**: `{username}/{project}-{iid}` by default, for example
  `alice/backend-42`. Configurable, see [CONFIGURATION.md](docs/CONFIGURATION.md).
* **Source branch**: `release`, or a pattern like `release/*` to use the most
  recently updated matching branch in each repo.
* **Existing branches** are left untouched and reported as "already existed".
* **Failures** in one repo never stop the others; every result is logged and
  listed in the issue comment.
* **Security**: no secrets in code, GitHub, or app settings. The GitLab token
  and webhook secret live only in Key Vault, are read by the managed identity,
  and the webhook secret is generated and rotated by script without ever being
  printed. GitHub Actions logs in to Azure with OIDC federation (no client secret).

## Quick start

Full step-by-step instructions are in **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. In short:

```bash
# 1. Edit the repos and release branch
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

Then assign an issue in one of the source repos and watch the branches appear.

## Scheduled jobs

| Workflow | Schedule (UTC) | Action |
|---|---|---|
| Webhook Verification | Mondays 09:00 | Checks webhooks, release branches, and the function end to end |
| Secret Rotation | 1st of each month 02:00 | New webhook secret in Key Vault and on every webhook (old one valid 24h) |
| Webhook Cleanup | 1st of Jan/Apr/Jul/Oct 03:00 | Lists stale or duplicate webhooks (deletes only when run manually with *apply*) |
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
