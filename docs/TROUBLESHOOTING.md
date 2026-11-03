# Troubleshooting

Start with `python scripts/webhooks.py verify`; it pinpoints most problems.

## No branches were created

1. **Was the webhook called?** Source repo → Settings → Webhooks → Edit →
   *Recent events*.
   * No event: the repo is not in `source_repos` or `setup` was not run.
     Run `python scripts/webhooks.py setup`.
   * Response **401**: the webhook's secret does not match Key Vault. Run
     `python scripts/webhooks.py setup` to re-sync it.
   * Response **5xx** or timeout: see "Function errors" below.
   * Response **200 `{"status": "ignored"}`**: the event was not an assignment.
     Only *opening an issue with assignees* or *adding assignees* triggers it;
     unassigning, editing other fields and closing are ignored, as are users in
     `excluded_assignees`.
2. **Response 200 with `"failed"` results**: the `detail` field says why.
   Common ones:

| Detail | Fix |
|---|---|
| `Branch 'release' not found in grp/repo` | Create the release branch in that repo, or change `release_branch` |
| `404 Project Not Found` | Wrong path in `target_repos`, or the token cannot see the project |
| `403 Forbidden` | The token's user needs Developer (or higher) on the target repo, or a protected-branch rule blocks the name |
| `Invalid reference name` | The template produced an odd name; check `branch_name_template` |

## The webhook is disabled in GitLab

GitLab disables webhooks that fail repeatedly. Fix the cause, then in the
webhook settings click *Enable* (or run `setup`, which updates it), and run
`verify`. The function deliberately answers 200 for authenticated calls even
when some branches fail, so only auth or infrastructure problems should cause this.

## Key Vault "Forbidden" / "does not have secrets get permission"

* Right after `deploy.sh`: role assignments take a few minutes. Wait and retry.
* Locally: your account needs *Key Vault Secrets Officer* on the vault. `deploy.sh`
  grants it to whoever ran it. For someone else:

  ```bash
  az role assignment create --role "Key Vault Secrets Officer" \
    --assignee <user@domain> \
    --scope $(az keyvault show -n <vault-name> --query id -o tsv)
  ```
* The vault uses RBAC, so `az keyvault set-policy` has no effect.

## GitHub Actions: "AADSTS70021: No matching federated identity record found"

The federated credential only trusts workflows running on the `main` branch of
the repo given to `deploy.sh -r`. Check:

* the workflow ran on `main` (manual runs on other branches cannot log in)
* the repo name matches exactly (`owner/repo`); re-run `deploy.sh` if it changed
* the job does not use a GitHub `environment:` (that changes the OIDC subject)

To allow another branch, re-run `deploy.sh -b <branch>`.

## GitHub Actions: Azure login fails with "client-id missing"

The secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` are
not set, or the workflow ran from a fork (forks get no secrets).

## Deploy Function: smoke test fails

* Check the run log of the *Deploy to Azure Functions* step for build errors.
* Azure Portal → Function App → *Functions* should list `gitlab_webhook` and
  `health`. If empty, check *Log stream* for import errors on startup.
* A cold start on the Consumption plan can take up to a minute; the smoke test
  retries for about two minutes.

## Function errors (5xx)

Look at Application Insights → *Failures*, or *Log stream*. Typical causes:

* `KEYVAULT_URL is not configured`: the app setting is missing; re-run `deploy.sh`.
* `Secret 'gitlab-api-token' not found`: run `store-token`.
* GitLab unreachable from Azure (self-managed GitLab behind a firewall): allow
  the Function App's outbound IPs (Function App → *Networking*), or move the
  function onto a plan with VNet integration.

## verify: "function deep health HTTP 503"

The body names the failing check. `gitlab: error: ... 401` means the stored
GitLab token is invalid or expired; run `store-token` with a new token.

## Branches created twice / for the wrong person

Each assignment event only creates branches for people *added* in that event,
and existing branches are never touched. If you see duplicates with different
names, two templates were in use (for example the template changed between
assignments).

## Self-managed GitLab with a private CA

Set `REQUESTS_CA_BUNDLE` to your CA bundle path (locally and as a Function App
setting with the bundle deployed alongside the code), and keep SSL verification
on in the webhooks.
