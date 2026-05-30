# Copilot workspace instructions

<!--
  HOW TO USE THIS FILE
  ─────────────────────────────────────────────────────────────────
  GitHub Copilot reads only ONE file at .github/copilot-instructions.md.
  This file cannot be renamed.

  If you already have a copilot-instructions.md:
    → Do NOT replace it. Paste the section below (everything between the
      START / END markers) anywhere inside your existing file.

  If you do not have one yet:
    → Place this file as-is at .github/copilot-instructions.md.
  ─────────────────────────────────────────────────────────────────
-->

<!-- ── START: PlatformInfra DevOps Git Workflow ─────────────────── -->
## PlatformInfra — DevOps git workflow

### Repo map

| Alias | Path | Managed file |
|-------|------|--------------|
| abc2-configs | `/projects/platform-infra/abc2-configs` | `pom.xml` → `NEXUS_TENANT_CONFIG_VERSION` |
| abc-infra    | `/projects/platform-infra/abc-infra`    | `pom.xml` → `NEXUS_PLATFORM_INFRA_VERSION` |
| AA1234-xyz   | `/projects/azure-repos/AA1234-xyz`      | `PipelineCode/PAAC/VariablesTemplates/VARIABLES.yml` |

### Conventions

- **Feature branches**: `feature/<ISSUE>` — identical name in all three repos.
- **Release base**: always `release/<RELEASE>`. Never branch from `main`.
- **Snapshot pattern**: comment out the original line, insert `<ISSUE>-SNAPSHOT` below it.
  - pom.xml → XML comment `<!-- ... -->`
  - VARIABLES.yml → YAML comment `# ...`
- **Commit type**: `chore`, `feat`, or `fix` — user chooses, never default.
- **Commit message**: identical across all three repos.
- **Push**: always `git push -u origin HEAD`.

### Never without explicit user instruction

- `git merge` / `git rebase`
- `git stash` / `git reset` / `git clean`
- Touch any `<version>` in pom.xml except the `${revision}${sha1}${changelist}` line.
- Touch any VARIABLES.yml key except `NEXUS_PLATFORM_INFRA_VERSION` and `NEXUS_TENANT_CONFIG_VERSION`.
- Commit or push while any repo is not on a `feature/*` branch.

### Available prompts

| Prompt | When | Inputs |
|--------|------|--------|
| `@workspace /PlatformInfra_DevOps_GitFeatureSnapshot` | New issue setup | `RELEASE`, `ISSUE`, `TYPE` |
| `@workspace /PlatformInfra_DevOps_GitSyncRepos` | Ongoing add+commit+push | `MSG` |
<!-- ── END: PlatformInfra DevOps Git Workflow ───────────────────── -->
