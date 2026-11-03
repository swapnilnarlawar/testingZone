# Deployment runbook

First-time setup, start to finish. Plan for about 30 minutes. Every step can be
re-run safely.

## 0. Prerequisites

| Need | Why |
|---|---|
| Azure subscription, and **Owner** (or Contributor + User Access Administrator) on a resource group | The template creates role assignments |
| [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 2.60+ | Runs the Bicep deployment (`az bicep` is bundled) |
| Python 3.11+ | Runs the ops scripts |
| [GitHub CLI](https://cli.github.com/) (optional) | Sets the GitHub secrets in one go |
| A GitLab account to act as the automation (see step 1) | Creates branches, manages webhooks |

## 1. Prepare the GitLab token

The automation needs one GitLab token with the **`api`** scope.

Recommended, in order:

1. **Group access token** on the group that contains your repos
   (Group → Settings → Access tokens), role **Maintainer**, scope `api`.
   Not tied to a person, so it survives people leaving. Available on GitLab
   self-managed (all tiers) and GitLab.com Premium/Ultimate.
2. **Service account / bot user** with a personal access token, added as
   Maintainer to the repos.
3. Your own **personal access token** (fine for trying it out).

Required permissions:

* **Maintainer** on every *source* repo (managing webhooks needs Maintainer).
* At least **Developer** on every *target* repo (creating branches). If you
  protect branch name patterns such as `*/*`, the token's user must be allowed to push to them.

Set an expiry and put a reminder in your calendar; `verify` will start failing
when the token expires. Keep the token handy for step 5; you will paste it once
into a hidden prompt and it goes straight to Key Vault.

## 2. Configure the automation

Edit `function_app/config/automation.json`:

```json
{
  "gitlab_url": "https://gitlab.com",
  "source_repos": ["my-group/backend", "my-group/frontend"],
  "target_repos": ["my-group/backend", "my-group/frontend", "my-group/shared-config"],
  "release_branch": "release",
  "branch_name_template": "{username}/{project}-{iid}"
}
```

* **source_repos**: repos where issues are created and assigned (they get the webhook).
* **target_repos**: repos where the branches are created.
* Paths are the full `group/subgroup/project` path as shown in the GitLab URL.

All keys are described in [CONFIGURATION.md](CONFIGURATION.md). Commit the change.

## 3. Create the Azure resources

```bash
az login
az account set --subscription "<subscription name or id>"

./infra/deploy.sh \
  -g rg-gitlab-automation \
  -r <github-owner>/<this-repo> \
  -l eastus
```

Options: `-p` name prefix (default `glbranch`), `-b` the branch GitHub Actions
deploys from (default `main`).

This creates, in the resource group:

* User Assigned Managed Identity, federated with GitHub Actions for `<repo>` on `main`
* Key Vault (RBAC mode); the identity and **you** get *Key Vault Secrets Officer*
* Function App (Linux, Python 3.11, Consumption plan), storage account, Application Insights
* *Website Contributor* on the Function App for the identity (so GitHub can deploy)

At the end the script prints your Function App name, webhook URL, Key Vault URL
and the exact commands for the next step. Keep that output.

> **Role assignment delay**: Azure RBAC can take a few minutes to apply. If the
> next steps report "Forbidden" on Key Vault, wait 5 minutes and retry.

## 4. Configure GitHub

In the GitHub repo: **Settings → Secrets and variables → Actions**. The deploy
script printed `gh` commands that do all of this; otherwise add them by hand.

**Secrets** (these are identifiers, not passwords, but keep them as secrets):

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | UAMI client id |
| `AZURE_TENANT_ID` | Azure tenant id |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription id |

**Variables**:

| Name | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | Resource group name |
| `FUNCTION_APP_NAME` | Function App name |
| `KEYVAULT_URL` | `https://kv-....vault.azure.net/` |
| `WEBHOOK_URL` | `https://func-....azurewebsites.net/api/gitlab-webhook` |
| `CLEANUP_GROUP` | *(optional)* GitLab group the cleanup job should scan for stale webhooks |

## 5. Deploy the function code

Merge this code to `main` (or run **Actions → Deploy Function → Run workflow**
on `main`). The workflow runs the tests, deploys `function_app/`, then waits
until `GET /api/health` answers 200.

## 6. Store the GitLab token and create the webhooks

From your machine (you are logged in with `az login` and have Secrets Officer):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt

cp .env.example .env
# edit .env: set KEYVAULT_URL and WEBHOOK_URL from the deploy output

python scripts/webhooks.py store-token     # paste the token; it is validated, then stored
python scripts/webhooks.py setup --dry-run # shows what will be created
python scripts/webhooks.py setup           # generates the webhook secret and creates the webhooks
```

`setup` generates a random webhook secret, writes it to Key Vault and to each
webhook, and never prints it.

## 7. Verify

```bash
python scripts/webhooks.py verify
```

Every line should say `ok`, including the three function checks (liveness,
rejects a bad token, deep health with Key Vault + GitLab access).

Then do a real test: assign an issue in a source repo to yourself. Within a few
seconds the branches exist in every target repo and a comment appears on the
issue. You can also see the call under **Source repo → Settings → Webhooks →
Edit → Recent events**.

## 8. Done

The scheduled workflows now keep things healthy: weekly verification, monthly
secret rotation and quarterly cleanup reports. See [OPERATIONS.md](OPERATIONS.md).

## Updating later

| Change | What to do |
|---|---|
| Add/remove target repos, change release branch or naming | Edit `automation.json`, merge to `main` (auto-deploys) |
| Add a source repo | Edit `automation.json`, merge, then run `python scripts/webhooks.py setup` (or wait for the next rotation) |
| Remove a source repo | Edit `automation.json`, merge, then run the **Webhook Cleanup** workflow with *apply* |
| Renew the GitLab token | `python scripts/webhooks.py store-token` (picked up by the function within 5 minutes) |
| Change Azure resources | Edit `infra/main.bicep`, re-run `infra/deploy.sh` with the same arguments |

## Removing everything

```bash
python scripts/webhooks.py cleanup --remove-all --apply   # removes the webhooks from GitLab
az group delete -n rg-gitlab-automation                    # removes all Azure resources
az keyvault purge -n <key-vault-name>                       # optional: purge the soft-deleted vault
```
