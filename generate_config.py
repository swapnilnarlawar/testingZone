#!/usr/bin/env python3
"""
Config Generator v1 — CLI
Fetches .sh config files from GitLab by tag and generates annotated output.
No external dependencies — stdlib only.

Usage:
    python generate_config.py \\
        --gitlab  https://gitlab.yourcompany.com \\
        --project group/tenant-deploy-pipelines \\
        --stage   dev \\
        --new-tag v2.4.1 \\
        [--existing-tag v2.3.0] \\
        --tenant-type existing \\
        --out ./generated

Environment variables:
    GITLAB_TOKEN   GitLab PAT with read_repository scope (required)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Add the scripts directory to sys.path for `lib` imports
sys.path.insert(0, str(Path(__file__).parent))
from lib.parser import parse
from lib.differ import diff, DiffResult
from lib.generator import generate_new_tenant, generate_existing_tenant

# ─── File paths in the platform repo ─────────────────────────
STAGE_FILES = [
    "meg2-configs/env/{stage}/Tenant.sh",
    "meg2-configs/env/{stage}/TenantGroupAdmin.sh",
    "meg2-configs/env/{stage}/TenantGroupCommon.sh",
]
ROOT_FILES = [
    "meg2-configs/env/RECOMMENDED_VARIABLE.sh",
]


def all_file_paths(stage: str) -> list[str]:
    staged = [p.format(stage=stage) for p in STAGE_FILES]
    return staged + ROOT_FILES


# ─── GitLab API ───────────────────────────────────────────────

def gitlab_fetch_file(gitlab_url: str, project: str, file_path: str, ref: str, token: str) -> str | None:
    """Fetch a single file's raw content. Returns None if 404."""
    encoded_project = urllib.parse.quote(project, safe="")
    encoded_path    = urllib.parse.quote(file_path, safe="")
    url = f"{gitlab_url}/api/v4/projects/{encoded_project}/repository/files/{encoded_path}/raw?ref={urllib.parse.quote(ref)}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise RuntimeError(f"GitLab API error {e.code} fetching {file_path}@{ref}: {e.reason}") from e


# ─── Main logic ───────────────────────────────────────────────

def run(args: argparse.Namespace) -> int:
    token = os.environ.get("GITLAB_TOKEN", "").strip()
    if not token:
        print("ERROR: GITLAB_TOKEN environment variable not set", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = all_file_paths(args.stage)
    results: list[dict] = []
    total_new = total_changed = total_unchanged = total_removed = 0

    for file_path in files:
        file_name = Path(file_path).name
        print(f"  processing {file_name}...", file=sys.stderr)

        # Fetch new tag version
        new_content = gitlab_fetch_file(args.gitlab, args.project, file_path, args.new_tag, token)
        if new_content is None:
            print(f"    ↳ not found in {args.new_tag}, skipping", file=sys.stderr)
            continue
        new_vars = parse(new_content)

        if args.tenant_type == "new":
            generated = generate_new_tenant(file_name, new_vars, stage=args.stage)
            file_results = {
                "file": file_name,
                "new": len(new_vars),
                "changed": 0,
                "unchanged": 0,
                "removed": 0,
            }
            total_new += len(new_vars)

        else:  # existing
            existing_content = gitlab_fetch_file(args.gitlab, args.project, file_path, args.existing_tag, token)
            old_vars = parse(existing_content) if existing_content else []

            diff_result: DiffResult = diff(old_vars, new_vars)
            generated = generate_existing_tenant(file_name, diff_result, old_vars, new_vars, stage=args.stage)

            print(f"    ↳ {diff_result.summary()}", file=sys.stderr)
            file_results = {
                "file": file_name,
                "new":       len(diff_result.added),
                "changed":   len(diff_result.changed),
                "unchanged": len(diff_result.unchanged),
                "removed":   len(diff_result.removed),
            }
            total_new       += len(diff_result.added)
            total_changed   += len(diff_result.changed)
            total_unchanged += len(diff_result.unchanged)
            total_removed   += len(diff_result.removed)

        # Write output file
        out_path = out_dir / file_name
        out_path.write_text(generated, encoding="utf-8")
        print(f"    ↳ wrote {out_path}", file=sys.stderr)
        results.append(file_results)

    # Write analysis report
    report = {
        "summary": {
            "newCount":       total_new,
            "changedCount":   total_changed,
            "unchangedCount": total_unchanged,
            "removedCount":   total_removed,
            "totalFiles":     len(results),
        },
        "tenantType": args.tenant_type,
        "stage":      args.stage,
        "newTag":     args.new_tag,
        "existingTag": args.existing_tag or None,
        "files": results,
    }
    report_path = out_dir / "analysis-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("", file=sys.stderr)
    print(f"Done. {len(results)} file(s) → {out_dir}/", file=sys.stderr)
    print(f"Summary: +{total_new} new  ~{total_changed} changed  ={total_unchanged} unchanged  -{total_removed} removed", file=sys.stderr)

    return 0


# ─── CLI entry point ──────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate annotated .sh config files for a tenant migration.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--gitlab",        required=True,  help="GitLab base URL")
    parser.add_argument("--project",       required=True,  help="GitLab project path, e.g. group/tenant-deploy-pipelines")
    parser.add_argument("--stage",         required=True,  help="Environment stage, e.g. dev / staging / prod")
    parser.add_argument("--new-tag",       required=True,  help="New platform release tag")
    parser.add_argument("--existing-tag",  default=None,   help="Tenant's current deployed tag (required for --tenant-type existing)")
    parser.add_argument("--tenant-type",   required=True,  choices=["new", "existing"])
    parser.add_argument("--out",           default="./generated", help="Output directory")

    args = parser.parse_args()

    if args.tenant_type == "existing" and not args.existing_tag:
        parser.error("--existing-tag is required when --tenant-type=existing")

    sys.exit(run(args))


if __name__ == "__main__":
    main()
