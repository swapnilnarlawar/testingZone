---
mode: agent
tools: [runInTerminal]
description: Feature snapshot setup — asks for RELEASE, ISSUE, TYPE only. All file edits via terminal; no readFile/writeFile.
---

Ask for three values then stop asking:
- `RELEASE` — semver e.g. `3.2.1`  → reject if not `\d+\.\d+\.\d+`
- `ISSUE`   — e.g. `PROJ-1234`     → reject if not `[A-Z]+-\d+`
- `TYPE`    — one of `chore` | `feat` | `fix` → reject anything else

Derive:
```
REPO1   = /projects/platform-infra/abc2-configs
REPO2   = /projects/platform-infra/abc-infra
REPO3   = /projects/azure-repos/AA1234-xyz
VARS    = PipelineCode/PAAC/VariablesTemplates/VARIABLES.yml
BRANCH  = feature/${ISSUE}
MSG     = "${TYPE}(${ISSUE}): snapshot versions for release ${RELEASE}"
```

---

## Step 0 — pre-flight (abort entire workflow on any failure)

```sh
# 1. Dirty tree — must be empty for all three repos
git -C $REPO1 status --porcelain
git -C $REPO2 status --porcelain
git -C $REPO3 status --porcelain
```
Non-empty output → abort: "Repo X has uncommitted changes. Commit or stash before running."

```sh
# 2. Release branch must exist on remote
git -C $REPO1 ls-remote --exit-code --heads origin release/${RELEASE}
git -C $REPO2 ls-remote --exit-code --heads origin release/${RELEASE}
git -C $REPO3 ls-remote --exit-code --heads origin release/${RELEASE}
```
Non-zero exit → abort: "release/${RELEASE} not found in Repo X remote."

```sh
# 3. Feature branch must not exist locally or remotely
git -C $REPO1 branch -a | grep -q feature/${ISSUE}
git -C $REPO2 branch -a | grep -q feature/${ISSUE}
git -C $REPO3 branch -a | grep -q feature/${ISSUE}
```
Match found → abort: "feature/${ISSUE} already exists in Repo X. Delete it or use /sync-repos."

---

## Step 1 — branch setup (separate terminal per repo)

```sh
# T1
cd $REPO1 && git checkout release/${RELEASE} && git pull && git checkout -b feature/${ISSUE}
# T2
cd $REPO2 && git checkout release/${RELEASE} && git pull && git checkout -b feature/${ISSUE}
# T3
cd $REPO3 && git checkout release/${RELEASE} && git pull && git checkout -b feature/${ISSUE}
```
Abort on any non-zero exit.

---

## Step 2 — patch pom.xml (T1 and T2, run identically in each)

Token-efficient: use python3 in-terminal; file content never enters model context.

```sh
python3 - <<'EOF'
import re, sys
path = 'pom.xml'
src  = open(path).read()
old  = '<version>${revision}${sha1}${changelist}</version>'
if '<!-- ' + old in src:
    print('SKIP: already patched'); sys.exit(0)
m = re.search(r'^(\s*)' + re.escape(old), src, re.M)
indent = m.group(1) if m else '    '
patched = src.replace(
    indent + old,
    indent + '<!-- ' + old + ' -->\n' + indent + '<version>ISSUE_NUMBER-SNAPSHOT</version>'
)
open(path, 'w').write(patched)
print('OK')
EOF
```
Replace `ISSUE_NUMBER` with the actual value of `${ISSUE}` when generating this command.

Verify:
```sh
grep -A1 '<!-- <version>' pom.xml
```
Must show comment line then `<version>${ISSUE}-SNAPSHOT</version>`. On mismatch → abort, run `git checkout pom.xml`.

---

## Step 3 — patch VARIABLES.yml (T3)

```sh
cd $REPO3
python3 - <<'EOF'
import sys
path = 'PipelineCode/PAAC/VariablesTemplates/VARIABLES.yml'
lines = open(path).readlines()
keys  = {'NEXUS_PLATFORM_INFRA_VERSION', 'NEXUS_TENANT_CONFIG_VERSION'}
out   = []
for line in lines:
    matched = next((k for k in keys if line.lstrip().startswith(k + ':')), None)
    if matched and not line.lstrip().startswith('#'):
        indent = line[: len(line) - len(line.lstrip())]
        out.append(indent + '# ' + line.lstrip())
        out.append(indent + matched + ': "ISSUE_NUMBER-SNAPSHOT"\n')
    else:
        out.append(line)
open(path, 'w').writelines(out)
print('OK')
EOF
```
Replace `ISSUE_NUMBER` with `${ISSUE}`. Script skips already-commented keys (idempotent).

Verify:
```sh
grep -A1 'NEXUS_PLATFORM_INFRA_VERSION\|NEXUS_TENANT_CONFIG_VERSION' $REPO3/$VARS
```
Each key must appear as a `#` comment line followed by the new snapshot value.

---

## Step 4 — commit and push

Show pending changes in each repo and wait for user confirmation before proceeding.

```sh
# T1
cd $REPO1 && git status
# T2
cd $REPO2 && git status
# T3
cd $REPO3 && git status
```

Print all three outputs to console. Ask: **"Proceed with add, commit and push across all 3 repos? (yes/no)"**
Stop if the user says no.

```sh
# T1
cd $REPO1 && git add pom.xml && git commit -m "${MSG}" && git push -u origin feature/${ISSUE}
# T2
cd $REPO2 && git add pom.xml && git commit -m "${MSG}" && git push -u origin feature/${ISSUE}
# T3
cd $REPO3 && git add $VARS  && git commit -m "${MSG}" && git push -u origin feature/${ISSUE}
```

Push failure → stop immediately. Do not attempt remaining repos. Report which succeeded.

**Rollback if partial failure:**
```sh
# Undo last commit (keeps file changes staged — inspect then re-commit or discard)
git reset --soft HEAD~1
# Discard file changes entirely
git checkout pom.xml      # or $VARS in T3
```
Tell user exactly which repos committed and which need manual recovery.

---

## Step 5 — summary

```sh
git -C $REPO1 log -1 --oneline
git -C $REPO2 log -1 --oneline
git -C $REPO3 log -1 --oneline
```

| Repo | Branch | Commit |
|------|--------|--------|
| abc2-configs | feature/${ISSUE} | (hash) |
| abc-infra    | feature/${ISSUE} | (hash) |
| AA1234-xyz   | feature/${ISSUE} | (hash) |
