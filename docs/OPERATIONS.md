# Operations guide

## The ops CLI

All commands read `function_app/config/automation.json` plus `.env` (or the
environment). They authenticate to Key Vault with your `az login` account
locally and with the managed identity in GitHub Actions. No command prints a
secret. Exit code is `0` on success, `1` if anything failed, `2` for a configuration error.

```bash
python scripts/webhooks.py <command> --help
```

### store-token

```bash
python scripts/webhooks.py store-token            # hidden prompt
GITLAB_TOKEN=... python scripts/webhooks.py store-token --from-env
```

Checks the token against GitLab (`/user`) and stores it in Key Vault. Use it
again whenever you renew the token. The function picks up the new token within 5 minutes.

### setup

```bash
python scripts/webhooks.py setup --dry-run
python scripts/webhooks.py setup
python scripts/webhooks.py setup --force-update   # re-write every hook with the current secret
```

Creates the webhook secret in Key Vault if it does not exist yet, works out the
watched repos (every project in `source_groups`, plus `source_repos`, minus
`exclude_repos`), and makes sure each has a webhook to `WEBHOOK_URL` (issue
events only, SSL verification on). Missing hooks are created; disabled or
misconfigured ones are repaired; healthy ones are left alone. Safe to re-run.
The daily **Webhook Sync** workflow runs exactly this, which is how repos newly
created in a group get covered.

### verify

```bash
python scripts/webhooks.py verify
python scripts/webhooks.py verify --skip-endpoint   # GitLab checks only
```

Checks:

* the GitLab token works
* every watched repo has exactly one enabled webhook with issue events on
  (a repo created since the last sync shows as "webhook missing")
* every watched repo matches a route (otherwise its issues create no branches)
* every routed target repo has its release branch (or a branch matching the pattern)
* `GET /api/health` returns 200
* the function rejects a wrong token with 401
* `POST /api/health` with the real secret returns 200, proving the function can
  read Key Vault and call GitLab

### rotate

```bash
python scripts/webhooks.py rotate
python scripts/webhooks.py rotate --grace-hours 2
```

1. Copies the current secret to `<name>-previous` with an expiry (default 24h)
2. Generates and stores a new secret
3. Updates the webhook on every watched repo with the new secret

The function accepts both secrets until the expiry, so nothing is dropped
during the switch. If some webhooks fail to update, fix the cause and run
`rotate` or `setup` again before the grace period ends.

### cleanup

```bash
python scripts/webhooks.py cleanup                       # dry run
python scripts/webhooks.py cleanup --group other-group   # also scan an extra group
python scripts/webhooks.py cleanup --legacy-url https://old-func.azurewebsites.net/api/gitlab-webhook
python scripts/webhooks.py cleanup --apply               # actually delete
python scripts/webhooks.py cleanup --remove-all --apply  # teardown: remove all of them
```

Deletes webhooks pointing at this function from repos that are excluded or no
longer watched, duplicate webhooks on watched repos (the oldest is kept), and
webhooks pointing at any `--legacy-url`. It scans every project in
`source_groups` (excluded ones included), `source_repos`, and any `--group` /
`--repo` given.

## GitHub workflows

All can be started by hand from **Actions → (workflow) → Run workflow**.

| Workflow | Runs | Notes |
|---|---|---|
| CI | PRs and pushes | Unit tests and config validation |
| Deploy Function | Push to `main` touching `function_app/` | Test → deploy → wait for `/api/health` |
| Webhook Sync | Daily 06:00 UTC | `setup`: adds the webhook to new repos in the watched groups, repairs disabled hooks. Change the cron in `webhook-sync.yml` to run more often |
| Webhook Verification | Mondays 09:00 UTC | `verify` |
| Secret Rotation | 1st of month 02:00 UTC | `rotate` |
| Webhook Cleanup | Quarterly 03:00 UTC | `cleanup` as a dry run; run manually with **apply** ticked to delete. |

Each run writes a results table to its **job summary**. GitHub emails the
person who last edited a scheduled workflow when it fails (configure under your
GitHub *Settings → Notifications → Actions*).

Note: GitHub disables scheduled workflows after 60 days without repository
activity; re-enable them from the Actions tab if that happens.

## Logs and monitoring

* **Function logs**: Azure Portal → Function App → *Log stream*, or Application
  Insights → *Logs*:

  ```kusto
  traces
  | where timestamp > ago(1d)
  | where message has "created" or message has "failed" or message has "Rejected"
  | order by timestamp desc
  ```

* **GitLab side**: Source repo → *Settings → Webhooks → Edit → Recent events*
  shows every delivery, the response code and body (the body lists each branch result).

* **Issue comment**: each assignment leaves a comment with a table of branches and results.
