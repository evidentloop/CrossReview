#!/usr/bin/env python3
"""One-time migration: prompt-lab/cases → fixtures/.

Reads each Prompt Lab case directory and produces a valid eval-harness fixture:
  fixture.yaml, pack.json, review-result.json, manual-findings.yaml, auto-adjudications.yaml

Usage:
  uv run python scripts/migrate_prompt_lab_to_fixtures.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

# ── project imports ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crossreview.schema import (
    FileMeta,
    to_serializable,
)
from crossreview.pack import assemble_pack
from crossreview.ingest import run_ingest

# ── constants ────────────────────────────────────────────────────────

SELF_HOSTING_CASES = {"003-crossreview-review-fixes"}
CANONICAL_RAW_OUTPUT = "raw-output-r3.md"
CANONICAL_ADJUDICATION = "adjudication-r3.yaml"
REVIEWER_MODEL = "claude-sonnet-4-20250514"
PROMPT_SOURCE = "product"
PROMPT_VERSION = "v0.1"

CASES_DIR = Path("prompt-lab/cases")
FIXTURES_DIR = Path("fixtures")


def _infer_language(path: str) -> str | None:
    ext_map = {
        ".py": "python", ".ts": "typescript", ".js": "javascript",
        ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".toml": "toml", ".sh": "shell", ".bash": "shell",
        ".css": "css", ".html": "html", ".sql": "sql",
    }
    suffix = Path(path).suffix.lower()
    return ext_map.get(suffix)


def convert_pack(old_pack: dict):
    """Convert old-format pack (string changed_files) to current schema."""
    diff = old_pack.get("diff", "")
    intent = old_pack.get("intent")
    focus = old_pack.get("focus")

    raw_files = old_pack.get("changed_files", [])
    if raw_files and isinstance(raw_files[0], str):
        changed_files = [
            FileMeta(path=p, language=_infer_language(p))
            for p in raw_files
        ]
    else:
        changed_files = [
            FileMeta(path=f["path"], language=f.get("language"))
            for f in raw_files
        ]

    pack = assemble_pack(
        diff=diff,
        changed_files=changed_files,
        intent=intent,
        focus=focus if isinstance(focus, list) else ([focus] if focus else None),
    )
    return to_serializable(pack), pack


def transform_adjudication(adjud_data: dict, raw_finding_ids: set[str], fixture_id: str) -> dict:
    """Transform prompt-lab adjudication-r3.yaml → eval-harness auto-adjudications.yaml."""
    findings_out = []
    for f in adjud_data.get("findings", []):
        fid = f.get("id", "")
        if fid not in raw_finding_ids:
            print(f"  ⚠ adjudication finding '{fid}' not in raw_findings, skipping", file=sys.stderr)
            continue

        judgment = f.get("judgment", f.get("verdict", "unclear"))
        if judgment not in ("valid", "invalid", "unclear"):
            judgment = "unclear"

        matched_manual = f.get("baseline_match", f.get("matched_manual_id"))

        if judgment == "valid":
            actionability = f.get("actionability_judgment", "actionable")
        elif judgment == "invalid":
            actionability = f.get("actionability_judgment", "not_actionable")
        else:
            actionability = f.get("actionability_judgment", "unclear")
        if actionability not in ("actionable", "not_actionable", "unclear"):
            actionability = "unclear"

        findings_out.append({
            "auto_finding_id": fid,
            "judgment": judgment,
            "matched_manual_id": matched_manual,
            "actionability_judgment": actionability,
        })

    return {
        "fixture_id": fixture_id,
        "run_id": f"prompt-lab-r3-{fixture_id}",
        "adjudicated_at": adjud_data.get("adjudicated_at", "2026-04-24"),
        "findings": findings_out,
    }


def migrate_case(case_dir: Path, fixture_dir: Path, *, dry_run: bool = False) -> bool:
    """Migrate one Prompt Lab case → fixture directory. Returns True on success."""
    case_name = case_dir.name
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating {case_name}...")

    # ── 1. Read and convert pack ────────────────────────────────────
    old_pack_path = case_dir / "pack.json"
    with open(old_pack_path) as f:
        old_pack = json.load(f)
    pack_dict, pack_obj = convert_pack(old_pack)

    # ── 2. Read raw output ──────────────────────────────────────────
    raw_output_path = case_dir / CANONICAL_RAW_OUTPUT
    if not raw_output_path.exists():
        print(f"  ✗ missing {CANONICAL_RAW_OUTPUT}", file=sys.stderr)
        return False
    raw_analysis = raw_output_path.read_text(encoding="utf-8")

    # ── 3. Run ingest → ReviewResult ────────────────────────────────
    try:
        review_result = run_ingest(
            pack=pack_obj,
            raw_analysis=raw_analysis,
            model=REVIEWER_MODEL,
            prompt_source=PROMPT_SOURCE,
            prompt_version=PROMPT_VERSION,
        )
    except Exception as exc:
        print(f"  ✗ ingest failed: {exc}", file=sys.stderr)
        return False

    result_dict = to_serializable(review_result)
    raw_finding_ids = {f["id"] for f in result_dict.get("raw_findings", [])}
    print(f"  ingest: status={result_dict['review_status']}, "
          f"raw_findings={len(raw_finding_ids)}, "
          f"findings={len(result_dict.get('findings', []))}")

    # ── 4. Read and transform adjudication ──────────────────────────
    adjud_path = case_dir / CANONICAL_ADJUDICATION
    if not adjud_path.exists():
        print(f"  ✗ missing {CANONICAL_ADJUDICATION}", file=sys.stderr)
        return False
    adjud_text = adjud_path.read_text(encoding="utf-8")
    # Some adjudication files have unquoted backticks in observations.
    # We only need the findings section, so truncate before observations/recall/etc.
    for cut_marker in ("\nobservations:", "\nrecall:", "\nverdict:", "\nsummary:", "\npass_criteria:"):
        idx = adjud_text.find(cut_marker)
        if idx != -1:
            adjud_text = adjud_text[:idx]
            break
    try:
        adjud_data = yaml.safe_load(adjud_text)
    except yaml.YAMLError as exc:
        print(f"  ✗ cannot parse {CANONICAL_ADJUDICATION}: {exc}", file=sys.stderr)
        return False

    auto_adjud = transform_adjudication(adjud_data, raw_finding_ids, case_name)

    # Check coverage: every raw_finding must have an adjudication
    adjud_ids = {f["auto_finding_id"] for f in auto_adjud["findings"]}
    missing = raw_finding_ids - adjud_ids
    if missing:
        print(f"  ⚠ raw_findings without adjudication: {sorted(missing)}", file=sys.stderr)
        print(f"  → adding placeholder 'unclear' adjudications", file=sys.stderr)
        for fid in sorted(missing):
            auto_adjud["findings"].append({
                "auto_finding_id": fid,
                "judgment": "unclear",
                "matched_manual_id": None,
                "actionability_judgment": "unclear",
            })

    # ── 5. Create fixture.yaml ──────────────────────────────────────
    pool = "self_hosting" if case_name in SELF_HOSTING_CASES else "external"
    fixture_yaml = {
        "fixture_id": case_name,
        "pool": pool,
    }

    # ── 6. Copy manual-findings.yaml ────────────────────────────────
    manual_src = case_dir / "manual-findings.yaml"
    if not manual_src.exists():
        print(f"  ✗ missing manual-findings.yaml", file=sys.stderr)
        return False

    # ── 7. Write outputs ────────────────────────────────────────────
    if dry_run:
        print(f"  → would create {fixture_dir}/")
        print(f"    fixture.yaml: pool={pool}")
        print(f"    pack.json: {len(pack_dict.get('changed_files', []))} files, "
              f"fp={pack_dict['artifact_fingerprint'][:12]}...")
        print(f"    review-result.json: {len(raw_finding_ids)} raw_findings")
        print(f"    auto-adjudications.yaml: {len(auto_adjud['findings'])} entries")
        print(f"    manual-findings.yaml: copied")
        return True

    fixture_dir.mkdir(parents=True, exist_ok=True)

    # fixture.yaml
    with open(fixture_dir / "fixture.yaml", "w") as f:
        yaml.dump(fixture_yaml, f, default_flow_style=False, allow_unicode=True)

    # pack.json
    with open(fixture_dir / "pack.json", "w") as f:
        json.dump(pack_dict, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # review-result.json
    with open(fixture_dir / "review-result.json", "w") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # auto-adjudications.yaml
    with open(fixture_dir / "auto-adjudications.yaml", "w") as f:
        yaml.dump(auto_adjud, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # manual-findings.yaml
    shutil.copy2(manual_src, fixture_dir / "manual-findings.yaml")

    print(f"  ✓ created {fixture_dir}/")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if not CASES_DIR.exists():
        print(f"error: {CASES_DIR} not found", file=sys.stderr)
        return 1

    case_dirs = sorted(p for p in CASES_DIR.iterdir() if p.is_dir())
    print(f"Found {len(case_dirs)} Prompt Lab cases")

    success = 0
    failed = 0
    for case_dir in case_dirs:
        fixture_dir = FIXTURES_DIR / case_dir.name
        if migrate_case(case_dir, fixture_dir, dry_run=args.dry_run):
            success += 1
        else:
            failed += 1

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done: {success} succeeded, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
