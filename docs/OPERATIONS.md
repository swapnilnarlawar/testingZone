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
```

Creates the webhook secret in Key Vault if it does not exist yet, then makes
sure each source repo has a webhook to `WEBHOOK_URL` (created or updated in
place, issue events only, SSL verification on). Safe to re-run; run it after
adding a source repo.

### verify

```bash
python scripts/webhooks.py verify
python scripts/webhooks.py verify --skip-endpoint   # GitLab checks only
```

Checks:

* the GitLab token works
* every source repo has exactly one enabled webhook with issue events on
* every target repo has the release branch (or a branch matching the pattern)
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
3. Updates every source repo webhook with the new secret

The function accepts both secrets until the expiry, so nothing is dropped
during the switch. If some webhooks fail to update, fix the cause and run
`rotate` or `setup` again before the grace period ends.

### cleanup

```bash
python scripts/webhooks.py cleanup                       # dry run
python scripts/webhooks.py cleanup --group my-group      # also scan every project in a group
python scripts/webhooks.py cleanup --legacy-url https://old-func.azurewebsites.net/api/gitlab-webhook
python scripts/webhooks.py cleanup --apply               # actually delete
python scripts/webhooks.py cleanup --remove-all --apply  # teardown: remove all of them
```

Deletes webhooks pointing at this function from repos that are no longer in
`source_repos`, duplicate webhooks in source repos (the oldest is kept), and
webhooks pointing at any `--legacy-url`. Only repos it knows about are scanned:
the source repos, `--repo` entries, and every project under `--group`.

## GitHub workflows

All can be started by hand from **Actions → (workflow) → Run workflow**.

| Workflow | Runs | Notes |
|---|---|---|
| CI | PRs and pushes | Unit tests and config validation |
| Deploy Function | Push to `main` touching `function_app/` | Test → deploy → wait for `/api/health` |
| Webhook Verification | Mondays 09:00 UTC | `verify` |
| Secret Rotation | 1st of month 02:00 UTC | `rotate` |
| Webhook Cleanup | Quarterly 03:00 UTC | `cleanup` as a dry run; run manually with **apply** ticked to delete. Set the `CLEANUP_GROUP` variable to scan a whole group |

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
