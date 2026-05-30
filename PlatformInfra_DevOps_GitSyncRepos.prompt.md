---
mode: agent
tools: [runInTerminal]
description: git add + commit + push across all 3 repos. One commit message. Branch-guarded.
---

Ask for one value then stop asking:
- `MSG` — commit message e.g. `"feat(PROJ-1234): add retry logic"` or `"fix(PROJ-1234): correct null check"`

---

## Step 0 — branch guard (abort if any repo is not on a feature branch)

```sh
git -C /projects/platform-infra/abc2-configs branch --show-current
git -C /projects/platform-infra/abc-infra    branch --show-current
git -C /projects/azure-repos/AA1234-xyz      branch --show-current
```
If any result does not start with `feature/` → abort: "Repo X is on branch Y — not a feature branch. Switch before syncing."

---

## Step 1 — add, commit, push

Show pending changes across all three repos and wait for confirmation.

```sh
git -C /projects/platform-infra/abc2-configs status
git -C /projects/platform-infra/abc-infra    status
git -C /projects/azure-repos/AA1234-xyz      status
```

Print all three outputs to console. Ask: **"Proceed with add, commit and push across all 3 repos? (yes/no)"**
Stop if the user says no.

```sh
# T1
cd /projects/platform-infra/abc2-configs && git add -A && git commit -m "${MSG}" && git push -u origin HEAD

# T2
cd /projects/platform-infra/abc-infra    && git add -A && git commit -m "${MSG}" && git push -u origin HEAD

# T3
cd /projects/azure-repos/AA1234-xyz      && git add -A && git commit -m "${MSG}" && git push -u origin HEAD
```

Rules:
- `git push -u origin HEAD` always sets upstream correctly regardless of whether the branch was pushed before.
- `nothing to commit` → skip that repo's push, note it, continue with others.
- Push rejected (non-fast-forward) → stop that repo, tell user to run `git pull --rebase` then retry `/sync-repos`.

---

## Step 2 — summary

```sh
git -C /projects/platform-infra/abc2-configs log -1 --oneline
git -C /projects/platform-infra/abc-infra    log -1 --oneline
git -C /projects/azure-repos/AA1234-xyz      log -1 --oneline
```
