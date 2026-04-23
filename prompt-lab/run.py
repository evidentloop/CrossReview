#!/usr/bin/env python3
"""
Prompt Lab runner — testing CrossReview reviewer prompt.

Usage:
    python run.py --render-only cases/001-auth-refresh
    python run.py --api-only --label r4 cases/001-auth-refresh
    python run.py --api-only --provider anthropic --model claude-opus-4-5-20251101 \\
        --api-key-env ANTHROPIC_API_KEY --label r4 cases/001-auth-refresh

Modes:
    --render-only   Render prompt-template.md to rendered-prompt.md for manual paste.
    --api-only      Call the reviewer API via the canonical verify pipeline and save
                    run-<label>.json (canonical ReviewResult) to the case directory.
"""

import json
import sys
import argparse
from pathlib import Path

# Shared core — single renderer for Prompt Lab and crossreview verify
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crossreview.core.prompt import render_reviewer_prompt
from crossreview.config import ConfigError, resolve_reviewer_config
from crossreview.pack import assemble_pack, extract_changed_files
from crossreview.schema import (
    ContextFile,
    Evidence,
    EvidenceStatus,
    FileMeta,
    review_result_to_json,
    validate_review_result,
)
from crossreview.verify import run_verify_pack


def load_pack(case_dir: Path) -> dict:
    pack_path = case_dir / "pack.json"
    if not pack_path.exists():
        raise ValueError(f"{pack_path} not found")
    pack = json.loads(pack_path.read_text(encoding="utf-8"))

    if pack.get("artifact_type") != "code_diff":
        raise ValueError(f"artifact_type must be 'code_diff', got '{pack.get('artifact_type')}'")
    if not pack.get("diff", "").strip():
        raise ValueError("pack.json 'diff' is empty")
    if not pack.get("changed_files"):
        raise ValueError("pack.json 'changed_files' is empty")

    return pack


def load_prompt_lab_template() -> str:
    """Load the editable Prompt Lab template used by render-only experiments."""
    return (Path(__file__).resolve().parent / "prompt-template.md").read_text(encoding="utf-8")


def load_review_pack(case_dir: Path):
    """Load legacy Prompt Lab pack.json through the canonical pack assembler."""
    raw_pack = load_pack(case_dir)
    return assemble_pack(
        raw_pack["diff"],
        changed_files=_changed_files_from_legacy(raw_pack.get("changed_files"), raw_pack["diff"]),
        intent=raw_pack.get("intent"),
        task_file=raw_pack.get("task_file"),
        focus=raw_pack.get("focus"),
        context_files=_context_files_from_legacy(raw_pack.get("context_files")),
        evidence=_evidence_from_legacy(raw_pack.get("evidence")),
    )


def _changed_files_from_legacy(value, diff: str) -> list[FileMeta]:
    if not value:
        return extract_changed_files(diff)
    result: list[FileMeta] = []
    for item in value:
        if isinstance(item, str):
            result.append(FileMeta(path=item))
            continue
        if isinstance(item, dict):
            result.append(FileMeta(path=item["path"], language=item.get("language")))
            continue
        raise ValueError("pack.json 'changed_files' must contain strings or objects")
    return result


def _context_files_from_legacy(value) -> list[ContextFile] | None:
    if not value:
        return None
    return [
        ContextFile(
            path=item["path"],
            content=item["content"],
            role=item.get("role"),
        )
        for item in value
    ]


def _evidence_from_legacy(value) -> list[Evidence] | None:
    if not value:
        return None
    return [
        Evidence(
            source=item["source"],
            status=EvidenceStatus(item["status"]),
            summary=item["summary"],
            command=item.get("command"),
            detail=item.get("detail"),
        )
        for item in value
    ]


def run_api_only(
    case_dir: Path,
    *,
    label: str,
    provider: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
) -> int:
    """Run the product verify path and save a canonical ReviewResult JSON."""
    try:
        pack = load_review_pack(case_dir)
        config = resolve_reviewer_config(
            cli_provider=provider,
            cli_model=model,
            cli_api_key_env=api_key_env,
        )
    except (ConfigError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = run_verify_pack(pack, config)
    violations = validate_review_result(result)
    if violations:
        print(f"Error: invalid ReviewResult: {', '.join(violations)}", file=sys.stderr)
        return 1

    output_path = case_dir / f"run-{label}.json"
    output_path.write_text(review_result_to_json(result), encoding="utf-8")
    print(f"Saved: {output_path}")
    print(
        f"Review status: {result.review_status.value}; "
        f"findings: {len(result.raw_findings)} raw / {len(result.findings)} emitted; "
        f"model: {result.reviewer.model}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prompt Lab runner for CrossReview reviewer prompt experiments.",
        allow_abbrev=False,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--render-only",
        action="store_true",
        help="render prompt-template.md to rendered-prompt.md for manual paste",
    )
    mode.add_argument(
        "--api-only",
        action="store_true",
        help="call the configured reviewer API and save run-<label>.json",
    )
    parser.add_argument(
        "--label",
        default="api",
        help="output label for --api-only (default: api)",
    )
    parser.add_argument(
        "--provider",
        help="override reviewer provider (e.g. anthropic)",
    )
    parser.add_argument(
        "--model",
        help="override reviewer model",
    )
    parser.add_argument(
        "--api-key-env",
        help="override API key environment variable name",
    )
    parser.add_argument("case_dir", type=Path)
    return parser.parse_args(argv)


def main():
    args = parse_args()
    case_dir = args.case_dir
    if not case_dir.is_dir():
        print(f"Error: {case_dir} is not a directory")
        sys.exit(1)

    if args.api_only:
        sys.exit(run_api_only(
            case_dir,
            label=args.label,
            provider=args.provider,
            model=args.model,
            api_key_env=args.api_key_env,
        ))

    template = load_prompt_lab_template()
    try:
        pack = load_pack(case_dir)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    prompt = render_reviewer_prompt(template, pack)

    print(f"Case: {case_dir.name}")
    print(f"Diff size: {len(pack.get('diff', ''))} chars")
    print(f"Intent: {pack.get('intent', '(none)')}")

    if args.render_only:
        rendered_path = case_dir / "rendered-prompt.md"
        rendered_path.write_text(prompt, encoding="utf-8")
        print(f"Rendered prompt saved: {rendered_path}")
        print(f"Paste this into your LLM session, then save output to {case_dir / 'raw-output-<label>.md'}")
        return


if __name__ == "__main__":
    main()
