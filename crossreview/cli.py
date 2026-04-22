"""CrossReview CLI — ``crossreview pack`` / ``crossreview verify``.

Implements 1C.1 (pack CLI). Verify is a stub until 1B.4+ land.

Usage::

    crossreview pack --diff HEAD~1 > pack.json
    crossreview pack --diff HEAD~1 --intent "fix auth" --focus auth > pack.json
    crossreview pack --diff HEAD~1 --task ./task.md --context ./plan.md > pack.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .adjudicator import determine_advisory_verdict, determine_intent_coverage
from .budget import apply_budget_gate
from .config import ConfigError, resolve_reviewer_config
from .normalizer import normalize_review_output
from .pack import (
    GitDiffError,
    assemble_pack,
    changed_files_from_git,
    compute_pack_completeness,
    diff_from_git,
    pack_to_json,
    read_context_files,
    read_task_file,
)
from .reviewer import (
    ReviewerError,
    resolve_reviewer_backend,
)
from .schema import (
    AdvisoryVerdict,
    BudgetStatus,
    ReviewResult,
    ReviewStatus,
    ReviewerFailureReason,
    ReviewerMeta,
    ResultBudget,
    SCHEMA_VERSION,
    Verdict,
    review_pack_from_dict,
    review_result_to_json,
    validate_review_pack,
    validate_review_result,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crossreview",
        description="Context-isolated verification harness for AI-generated code.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- pack ---
    pack_p = sub.add_parser(
        "pack",
        help="Assemble a ReviewPack from a git diff.",
    )
    pack_p.add_argument(
        "--diff",
        required=True,
        metavar="REF",
        help="Git ref for diff base (e.g. HEAD~1, abc123, main..feat).",
    )
    pack_p.add_argument(
        "--intent",
        default=None,
        help="Task intent string.",
    )
    pack_p.add_argument(
        "--task",
        default=None,
        metavar="FILE",
        help="Path to a task description file (content stored in task_file).",
    )
    pack_p.add_argument(
        "--focus",
        action="append",
        default=None,
        help="Focus area (repeatable).",
    )
    pack_p.add_argument(
        "--context",
        action="append",
        default=None,
        metavar="FILE",
        help="Extra context file path (repeatable).",
    )

    # --- verify (stub) ---
    verify_p = sub.add_parser(
        "verify",
        help="Review a ReviewPack and emit ReviewResult JSON.",
    )
    verify_p.add_argument(
        "--pack",
        required=True,
        metavar="FILE",
        help="Path to a ReviewPack JSON file.",
    )
    verify_p.add_argument("--model", default=None, help="Override reviewer model.")
    verify_p.add_argument("--provider", default=None, help="Override reviewer provider.")
    verify_p.add_argument(
        "--api-key-env",
        default=None,
        metavar="ENV_VAR",
        help="Override API key environment variable name.",
    )

    return parser


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute ``crossreview pack``."""

    # 1. Obtain diff
    try:
        diff = diff_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not diff.strip():
        print("error: git diff produced empty output — nothing to pack.", file=sys.stderr)
        return 1

    # 2. Get changed files via git (NUL-delimited, handles special-char paths)
    try:
        changed_files = changed_files_from_git(args.diff)
    except GitDiffError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 3. Read optional files
    task_content: str | None = None
    if args.task:
        try:
            task_content = read_task_file(args.task)
        except OSError as exc:
            print(f"error: cannot read task file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: task file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    context_files = None
    if args.context:
        try:
            context_files = read_context_files(args.context)
        except OSError as exc:
            print(f"error: cannot read context file: {exc}", file=sys.stderr)
            return 1
        except UnicodeDecodeError as exc:
            print(f"error: context file is not valid UTF-8: {exc}", file=sys.stderr)
            return 1

    # 4. Assemble
    try:
        pack = assemble_pack(
            diff,
            changed_files=changed_files,
            intent=args.intent,
            task_file=task_content,
            focus=args.focus,
            context_files=context_files,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # 5. Diagnostic to stderr
    completeness = compute_pack_completeness(pack)
    n_files = len(pack.changed_files)
    print(
        f"crossreview pack: {n_files} file(s), completeness={completeness:.2f}, "
        f"artifact={pack.artifact_fingerprint[:12]}",
        file=sys.stderr,
    )

    # 6. JSON to stdout
    print(pack_to_json(pack))
    return 0


def _load_pack(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as exc:
        print(f"error: cannot read pack file: {exc}", file=sys.stderr)
        return None
    except UnicodeDecodeError as exc:
        print(f"error: pack file is not valid UTF-8: {exc}", file=sys.stderr)
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: pack file is not valid JSON: {exc}", file=sys.stderr)
        return None

    try:
        return review_pack_from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: pack JSON has invalid structure: {exc}", file=sys.stderr)
        return None


def _build_result(
    *,
    pack,
    reviewer_model: str,
    budget_status: BudgetStatus,
    files_reviewed: int,
    files_total: int,
    chars_consumed: int,
    chars_limit: int | None,
    review_status: ReviewStatus,
    raw_findings: list | None = None,
    findings=None,
    raw_analysis: str | None = None,
    latency_sec: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    failure_reason: ReviewerFailureReason | None = None,
    advisory_verdict: AdvisoryVerdict | None = None,
    quality_metrics=None,
    intent_coverage=None,
) -> ReviewResult:
    result = ReviewResult(
        schema_version=SCHEMA_VERSION,
        artifact_fingerprint=pack.artifact_fingerprint,
        pack_fingerprint=pack.pack_fingerprint,
        review_status=review_status,
        intent_coverage=intent_coverage or determine_intent_coverage(pack, findings or []),
        raw_findings=raw_findings or [],
        findings=findings or [],
        evidence=list(pack.evidence or []),
        advisory_verdict=advisory_verdict or AdvisoryVerdict(
            verdict=Verdict.INCONCLUSIVE,
            rationale="review did not produce a final advisory verdict",
        ),
        quality_metrics=quality_metrics or ReviewResult().quality_metrics,
        reviewer=ReviewerMeta(
            model=reviewer_model,
            raw_analysis=raw_analysis,
            latency_sec=latency_sec,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            failure_reason=failure_reason,
        ),
        budget=ResultBudget(
            status=budget_status,
            files_reviewed=files_reviewed,
            files_total=files_total,
            chars_consumed=chars_consumed,
            chars_limit=chars_limit,
        ),
    )
    return result


def _cmd_verify(args: argparse.Namespace) -> int:
    """Execute ``crossreview verify --pack pack.json``."""
    pack = _load_pack(args.pack)
    if pack is None:
        return 1

    violations = validate_review_pack(pack)
    if violations:
        print(f"error: invalid ReviewPack: {', '.join(violations)}", file=sys.stderr)
        return 1

    try:
        reviewer_config = resolve_reviewer_config(
            cli_model=args.model,
            cli_provider=args.provider,
            cli_api_key_env=args.api_key_env,
        )
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    budget_result = apply_budget_gate(pack)
    pack_completeness = compute_pack_completeness(pack)

    if budget_result.status == BudgetStatus.REJECTED:
        result = _build_result(
            pack=pack,
            reviewer_model=reviewer_config.model,
            budget_status=budget_result.status,
            files_reviewed=budget_result.files_reviewed,
            files_total=budget_result.files_total,
            chars_consumed=budget_result.chars_consumed,
            chars_limit=budget_result.chars_limit,
            review_status=ReviewStatus.REJECTED,
            failure_reason=budget_result.failure_reason,
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.INCONCLUSIVE,
                rationale="review input was rejected by the budget gate",
            ),
        )
        if validate_review_result(result):
            print("error: internal error while building rejected ReviewResult", file=sys.stderr)
            return 1
        print(review_result_to_json(result))
        print("crossreview verify: review_status=rejected", file=sys.stderr)
        return 0

    if budget_result.effective_pack is None:
        print("error: budget gate passed but effective_pack is None", file=sys.stderr)
        return 1

    try:
        backend = resolve_reviewer_backend(reviewer_config)
        review = backend.review(budget_result.effective_pack, reviewer_config)
    except ReviewerError as exc:
        result = _build_result(
            pack=pack,
            reviewer_model=reviewer_config.model,
            budget_status=budget_result.status,
            files_reviewed=budget_result.files_reviewed,
            files_total=budget_result.files_total,
            chars_consumed=budget_result.chars_consumed,
            chars_limit=budget_result.chars_limit,
            review_status=ReviewStatus.FAILED,
            failure_reason=exc.failure_reason,
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.INCONCLUSIVE,
                rationale=str(exc),
            ),
        )
        if validate_review_result(result):
            print("error: internal error while building failed ReviewResult", file=sys.stderr)
            return 1
        print(review_result_to_json(result))
        print("crossreview verify: review_status=failed", file=sys.stderr)
        return 0

    normalization = normalize_review_output(
        review.raw_analysis,
        budget_result.effective_pack,
        pack_completeness=pack_completeness,
    )

    advisory_verdict = determine_advisory_verdict(
        findings=normalization.findings,
        pack=pack,
        budget_status=budget_result.status,
        pack_completeness=pack_completeness,
        speculative_ratio=normalization.quality_metrics.speculative_ratio,
    )
    review_status = (
        ReviewStatus.TRUNCATED
        if budget_result.status == BudgetStatus.TRUNCATED
        else ReviewStatus.COMPLETE
    )
    result = _build_result(
        pack=pack,
        reviewer_model=review.model,
        budget_status=budget_result.status,
        files_reviewed=budget_result.files_reviewed,
        files_total=budget_result.files_total,
        chars_consumed=budget_result.chars_consumed,
        chars_limit=budget_result.chars_limit,
        review_status=review_status,
        findings=normalization.findings,
        raw_findings=normalization.raw_findings,
        raw_analysis=review.raw_analysis,
        latency_sec=review.latency_sec,
        input_tokens=review.input_tokens,
        output_tokens=review.output_tokens,
        advisory_verdict=advisory_verdict,
        quality_metrics=normalization.quality_metrics,
    )
    violations = validate_review_result(result)
    if violations:
        print(f"error: internal invalid ReviewResult: {', '.join(violations)}", file=sys.stderr)
        return 1

    print(review_result_to_json(result))
    print(
        f"crossreview verify: review_status={result.review_status.value}, "
        f"findings={len(result.findings)}, model={result.reviewer.model}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "pack":
        return _cmd_pack(args)
    if args.command == "verify":
        return _cmd_verify(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


def _entry_point() -> None:
    """Console-script entry point — propagates return code to exit status."""
    raise SystemExit(main())
