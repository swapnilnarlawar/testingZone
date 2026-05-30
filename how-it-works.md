# How it works — v1

## Core algorithm

Three steps, all deterministic:

### 1. Parse

Extracts variable definitions using two regexes:

```
Quoted:   ^(?:export\s+)?([A-Za-z_]\w*)=(['"])(.*?)\2(?:\s*#.*)?$
Plain:    ^(?:export\s+)?([A-Za-z_]\w*)=(.+?)(?:\s*#.*)?$
```

For each variable the parser also captures any preceding `#` comment lines
as a description. Lines that don't match (function defs, conditionals, etc.)
are silently ignored.

### 2. Diff

Compares the old and new variable lists by name:

- Name in new, not in old → **added**
- Name in old, not in new → **removed**
- Same name, different value → **changed**
- Same name, same value → **unchanged**

Order follows the new file's variable order (the platform team controls the
canonical ordering).

### 3. Generate

Produces a complete annotated `.sh` file:

- **New tenants**: all variables included, placeholders flagged
- **Existing tenants**: new/changed variables annotated, unchanged preserved with
  their existing values, removed variables listed in a trailing comment block

## File matching

When multiple files are processed (web app: by upload name, CLI: by canonical
paths), they are matched by filename only — `Tenant.sh` old vs `Tenant.sh` new.
If a file exists in the new tag but not the old, all its variables are treated as
new. If a file exists in the old but not the new, it is omitted from output.

## Placeholder detection

Values are flagged with `# [FILL IN REQUIRED]` if they match:

```
TODO | PLACEHOLDER | <YOUR_ | <ENTER_ | ^<[A-Z]
```

This catches common platform conventions for placeholder values. Extend the
regex in `lib/parser.py` (`PLACEHOLDER`) if your platform uses different markers.

## Web app vs CLI — same logic

The web app (`public/index.html`) contains a direct JavaScript port of the
Python library in `scripts/lib/`. Both implement the same algorithm; the web
app just runs it client-side so no server is needed.

If you change the annotation format in `generator.py`, reflect the same change
in `public/index.html`'s `generateNewTenant` / `generateExistingTenant`
functions to keep them consistent.

## Known limitations

- Does not handle multiline values (`VAR=$(cat <<EOF ... EOF)`)
- Does not handle conditional assignments (`VAR=${VAR:-default}`)
- Does not handle variables set by sourcing other files (`source ./other.sh`)
- Inline comments after values are stripped — `export X=1  # note` → value is `1`

These are acceptable for flat declaration-style config files. If your platform
uses more complex patterns, extend the parser regexes accordingly.
