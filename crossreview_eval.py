"""Dev-only eval harness for CrossReview fixture aggregation.

The v0 harness is intentionally an offline aggregator:

- It reads saved fixture inputs and saved runtime outputs.
- It does not call reviewer backends by itself.
- It computes the release-gate metrics defined in docs/v0-scope.md §4/§12.

This keeps product runtime concerns separate from eval-layer judgment and lets
humans review and amend adjudication files without re-running model calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from crossreview.schema import (
    ReviewResult,
    ReviewStatus,
    review_pack_from_dict,
    review_result_from_dict,
    to_serializable,
    validate_eval_review_result_contract,
    validate_review_pack,
    validate_review_result,
)


VALID_FINDING_JUDGMENTS = {"valid", "invalid", "unclear"}
VALID_ACTIONABILITY_JUDGMENTS = {"actionable", "not_actionable", "unclear"}
VALID_POOLS = {"external", "self_hosting"}
FAILURE_REVIEW_STATUSES = {ReviewStatus.REJECTED, ReviewStatus.FAILED}
VALID_EVAL_MODES = {"release-gate", "regression"}


class EvalContractError(ValueError):
    """Raised when fixture files violate the eval contract."""


@dataclass(frozen=True)
class ManualContextItem:
    type: str
    path_or_desc: str
    required: bool
    covered_by_pack: bool | None


@dataclass(frozen=True)
class ManualFinding:
    id: str
    summary: str
    file: str | None
    severity_estimate: str


@dataclass(frozen=True)
class ManualFindingsRecord:
    fixture_id: str
    source: str
    reviewer_model: str
    reviewed_at: str
    context_items: list[ManualContextItem]
    findings: list[ManualFinding]


@dataclass(frozen=True)
class AutoAdjudicationFinding:
    auto_finding_id: str
    judgment: str
    matched_manual_id: str | None
    actionability_judgment: str


@dataclass(frozen=True)
class AutoAdjudicationsRecord:
    fixture_id: str
    run_id: str
    adjudicated_at: str
    findings: list[AutoAdjudicationFinding]


@dataclass(frozen=True)
class EvalFixture:
    fixture_id: str
    pool: str
    pack: Any
    review_result: ReviewResult
    manual_findings: ManualFindingsRecord
    auto_adjudications: AutoAdjudicationsRecord
    path: Path


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalContractError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise EvalContractError(f"{path} is not valid UTF-8: {exc}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise EvalContractError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvalContractError(f"{path} must contain a top-level JSON object")
    return data


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(_read_text(path))
    except yaml.YAMLError as exc:
        raise EvalContractError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise EvalContractError(f"{path} must contain a top-level mapping")
    return data


def _require_str(data: dict[str, Any], key: str, *, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise EvalContractError(f"{path}: field '{key}' must be a non-empty string")
    return value


def _require_bool(data: dict[str, Any], key: str, *, path: Path) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise EvalContractError(f"{path}: field '{key}' must be a boolean")
    return value


def _optional_bool(data: dict[str, Any], key: str, *, path: Path) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise EvalContractError(f"{path}: field '{key}' must be a boolean or null")
    return value


def _require_list(data: dict[str, Any], key: str, *, path: Path) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise EvalContractError(f"{path}: field '{key}' must be a list")
    return value


def _load_manual_findings(path: Path) -> ManualFindingsRecord:
    data = _read_yaml(path)
    context_items: list[ManualContextItem] = []
    for idx, item in enumerate(_require_list(data, "context_items", path=path), start=1):
        if not isinstance(item, dict):
            raise EvalContractError(f"{path}: context_items[{idx}] must be a mapping")
        context_items.append(
            ManualContextItem(
                type=_require_str(item, "type", path=path),
                path_or_desc=_require_str(item, "path_or_desc", path=path),
                required=_require_bool(item, "required", path=path),
                covered_by_pack=_optional_bool(item, "covered_by_pack", path=path),
            )
        )

    findings: list[ManualFinding] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(_require_list(data, "findings", path=path), start=1):
        if not isinstance(item, dict):
            raise EvalContractError(f"{path}: findings[{idx}] must be a mapping")
        finding_id = _require_str(item, "id", path=path)
        if finding_id in seen_ids:
            raise EvalContractError(f"{path}: duplicate manual finding id '{finding_id}'")
        seen_ids.add(finding_id)
        severity_estimate = _require_str(item, "severity_estimate", path=path)
        if severity_estimate not in {"high", "medium", "low"}:
            raise EvalContractError(
                f"{path}: findings[{idx}].severity_estimate must be high|medium|low"
            )
        file_value = item.get("file")
        if file_value is not None and not isinstance(file_value, str):
            raise EvalContractError(f"{path}: findings[{idx}].file must be string or null")
        findings.append(
            ManualFinding(
                id=finding_id,
                summary=_require_str(item, "summary", path=path),
                file=file_value,
                severity_estimate=severity_estimate,
            )
        )

    return ManualFindingsRecord(
        fixture_id=_require_str(data, "fixture_id", path=path),
        source=_require_str(data, "source", path=path),
        reviewer_model=_require_str(data, "reviewer_model", path=path),
        reviewed_at=_require_str(data, "reviewed_at", path=path),
        context_items=context_items,
        findings=findings,
    )


def _load_auto_adjudications(path: Path) -> AutoAdjudicationsRecord:
    data = _read_yaml(path)
    findings: list[AutoAdjudicationFinding] = []
    seen_auto_ids: set[str] = set()
    for idx, item in enumerate(_require_list(data, "findings", path=path), start=1):
        if not isinstance(item, dict):
            raise EvalContractError(f"{path}: findings[{idx}] must be a mapping")
        auto_finding_id = _require_str(item, "auto_finding_id", path=path)
        if auto_finding_id in seen_auto_ids:
            raise EvalContractError(f"{path}: duplicate auto finding id '{auto_finding_id}'")
        seen_auto_ids.add(auto_finding_id)

        judgment = _require_str(item, "judgment", path=path)
        if judgment not in VALID_FINDING_JUDGMENTS:
            raise EvalContractError(
                f"{path}: findings[{idx}].judgment must be valid|invalid|unclear"
            )

        actionability_judgment = _require_str(item, "actionability_judgment", path=path)
        if actionability_judgment not in VALID_ACTIONABILITY_JUDGMENTS:
            raise EvalContractError(
                f"{path}: findings[{idx}].actionability_judgment must be "
                "actionable|not_actionable|unclear"
            )

        matched_manual_id = item.get("matched_manual_id")
        if matched_manual_id is not None and not isinstance(matched_manual_id, str):
            raise EvalContractError(
                f"{path}: findings[{idx}].matched_manual_id must be string or null"
            )

        findings.append(
            AutoAdjudicationFinding(
                auto_finding_id=auto_finding_id,
                judgment=judgment,
                matched_manual_id=matched_manual_id,
                actionability_judgment=actionability_judgment,
            )
        )

    return AutoAdjudicationsRecord(
        fixture_id=_require_str(data, "fixture_id", path=path),
        run_id=_require_str(data, "run_id", path=path),
        adjudicated_at=_require_str(data, "adjudicated_at", path=path),
        findings=findings,
    )


def load_fixture(path: Path) -> EvalFixture:
    """Load one fixture directory and validate cross-file consistency."""
    if not path.is_dir():
        raise EvalContractError(f"{path} is not a fixture directory")

    manifest_path = path / "fixture.yaml"
    pack_path = path / "pack.json"
    result_path = path / "review-result.json"
    manual_path = path / "manual-findings.yaml"
    adjudications_path = path / "auto-adjudications.yaml"

    manifest = _read_yaml(manifest_path)
    fixture_id = _require_str(manifest, "fixture_id", path=manifest_path)
    pool = _require_str(manifest, "pool", path=manifest_path)
    if pool not in VALID_POOLS:
        raise EvalContractError(f"{manifest_path}: field 'pool' must be external|self_hosting")

    try:
        pack = review_pack_from_dict(_read_json(pack_path))
    except (KeyError, TypeError, ValueError) as exc:
        raise EvalContractError(f"{pack_path}: invalid ReviewPack payload: {exc}") from exc

    result_json = _read_json(result_path)
    try:
        review_result = review_result_from_dict(result_json)
    except (KeyError, TypeError, ValueError) as exc:
        raise EvalContractError(f"{result_path}: invalid ReviewResult payload: {exc}") from exc

    manual_findings = _load_manual_findings(manual_path)
    auto_adjudications = _load_auto_adjudications(adjudications_path)

    pack_violations = validate_review_pack(pack)
    if pack_violations:
        raise EvalContractError(
            f"{pack_path}: invalid ReviewPack ({', '.join(pack_violations)})"
        )

    result_violations = validate_review_result(review_result)
    if result_violations:
        raise EvalContractError(
            f"{result_path}: invalid ReviewResult ({', '.join(result_violations)})"
        )
    eval_result_violations = validate_eval_review_result_contract(result_json)
    if eval_result_violations:
        raise EvalContractError(
            f"{result_path}: invalid eval ReviewResult contract "
            f"({', '.join(eval_result_violations)})"
        )

    if manual_findings.fixture_id != fixture_id:
        raise EvalContractError(
            f"{manual_path}: fixture_id '{manual_findings.fixture_id}' != manifest '{fixture_id}'"
        )
    if auto_adjudications.fixture_id != fixture_id:
        raise EvalContractError(
            f"{adjudications_path}: fixture_id '{auto_adjudications.fixture_id}' != manifest '{fixture_id}'"
        )
    if review_result.pack_fingerprint != pack.pack_fingerprint:
        raise EvalContractError(
            f"{result_path}: pack_fingerprint does not match pack.json for fixture '{fixture_id}'"
        )

    manual_ids = {item.id for item in manual_findings.findings}
    raw_auto_ids = {item.id for item in review_result.raw_findings}
    adjudicated_auto_ids = {item.auto_finding_id for item in auto_adjudications.findings}
    for item in auto_adjudications.findings:
        if item.auto_finding_id not in raw_auto_ids:
            raise EvalContractError(
                f"{adjudications_path}: auto_finding_id '{item.auto_finding_id}' "
                "not present in review-result.json"
            )
        if item.matched_manual_id and item.matched_manual_id not in manual_ids:
            raise EvalContractError(
                f"{adjudications_path}: matched_manual_id '{item.matched_manual_id}' "
                "not present in manual-findings.yaml"
            )
    missing_adjudications = raw_auto_ids - adjudicated_auto_ids
    if missing_adjudications:
        missing_ids = ", ".join(sorted(missing_adjudications))
        raise EvalContractError(
            f"{adjudications_path}: missing adjudications for review-result raw_findings "
            f"({missing_ids})"
        )

    return EvalFixture(
        fixture_id=fixture_id,
        pool=pool,
        pack=pack,
        review_result=review_result,
        manual_findings=manual_findings,
        auto_adjudications=auto_adjudications,
        path=path,
    )


def load_fixtures(fixtures_root: Path) -> list[EvalFixture]:
    """Load all fixture directories under a root path."""
    if not fixtures_root.is_dir():
        raise EvalContractError(f"{fixtures_root} is not a directory")

    _FIXTURE_ARTIFACTS = ("pack.json", "review-result.json", "manual-findings.yaml", "auto-adjudications.yaml")

    fixtures: list[EvalFixture] = []
    seen_fixture_ids: set[str] = set()
    for child in sorted(fixtures_root.iterdir()):
        if not child.is_dir():
            continue
        if not (child / "fixture.yaml").is_file():
            # Detect directories that look like incomplete fixtures.
            present = [name for name in _FIXTURE_ARTIFACTS if (child / name).exists()]
            if present:
                raise EvalContractError(
                    f"{child.name}: missing fixture.yaml but contains {', '.join(present)}"
                )
            continue
        fixture = load_fixture(child)
        if fixture.fixture_id in seen_fixture_ids:
            raise EvalContractError(f"duplicate fixture_id '{fixture.fixture_id}' across fixtures")
        seen_fixture_ids.add(fixture.fixture_id)
        fixtures.append(fixture)
    return fixtures


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _evaluate_scope(fixtures: list[EvalFixture]) -> dict[str, Any]:
    """Aggregate metrics for a set of fixtures.

    Note: ``invalid_findings_per_run`` uses *successful* runs as the
    denominator (failed/rejected runs produce no findings).
    """
    total_runs = len(fixtures)
    failed_runs = 0
    successful_runs = 0
    total_valid = 0
    total_invalid = 0
    total_unclear = 0
    total_auto_findings = 0
    total_valid_actionable = 0
    total_required_context = 0
    total_covered_required_context = 0
    total_manual_findings = 0
    matched_manual_ids: set[tuple[str, str]] = set()
    max_invalid_single_run = 0

    fixture_summaries: list[dict[str, Any]] = []

    for fixture in fixtures:
        result = fixture.review_result
        is_failure = result.review_status in FAILURE_REVIEW_STATUSES
        if is_failure:
            failed_runs += 1
        else:
            successful_runs += 1

        run_invalid = 0
        run_unclear = 0
        run_valid = 0
        for item in fixture.auto_adjudications.findings:
            total_auto_findings += 1
            if item.judgment == "valid":
                total_valid += 1
                run_valid += 1
                if item.matched_manual_id:
                    matched_manual_ids.add((fixture.fixture_id, item.matched_manual_id))
                if item.actionability_judgment == "actionable":
                    total_valid_actionable += 1
            elif item.judgment == "invalid":
                total_invalid += 1
                run_invalid += 1
            else:
                total_unclear += 1
                run_unclear += 1

        max_invalid_single_run = max(max_invalid_single_run, run_invalid)

        manual_findings_count = len(fixture.manual_findings.findings)
        if manual_findings_count:
            total_manual_findings += manual_findings_count

        for context_item in fixture.manual_findings.context_items:
            if not context_item.required or context_item.covered_by_pack is None:
                continue
            total_required_context += 1
            if context_item.covered_by_pack is True:
                total_covered_required_context += 1

        fixture_summaries.append(
            {
                "fixture_id": fixture.fixture_id,
                "pool": fixture.pool,
                "path": str(fixture.path),
                "review_status": result.review_status.value,
                "advisory_verdict": result.advisory_verdict.verdict.value,
                "manual_findings_count": manual_findings_count,
                "auto_findings_count": len(fixture.auto_adjudications.findings),
                "raw_findings_len": len(result.raw_findings),
                "emitted_findings_len": len(result.findings),
                "valid_count": run_valid,
                "invalid_count": run_invalid,
                "unclear_count": run_unclear,
                "raw_findings_count": result.quality_metrics.raw_findings_count,
                "emitted_findings_count": result.quality_metrics.emitted_findings_count,
                "noise_count": result.quality_metrics.noise_count,
                "speculative_ratio": result.quality_metrics.speculative_ratio,
                "pack_completeness": result.quality_metrics.pack_completeness,
            }
        )

    matched_manual_count = len(matched_manual_ids)
    return {
        "fixture_count": total_runs,
        "failed_runs": failed_runs,
        "successful_runs": successful_runs,
        "manual_recall": _fraction(matched_manual_count, total_manual_findings),
        "precision": _fraction(total_valid, total_valid + total_invalid),
        "invalid_findings_per_run": _fraction(total_invalid, successful_runs),
        "max_invalid_single_run": max_invalid_single_run if total_runs else None,
        "unclear_rate": _fraction(total_unclear, total_auto_findings),
        "actionability": _fraction(total_valid_actionable, total_valid),
        "failure_rate": _fraction(failed_runs, total_runs),
        "context_fidelity": _fraction(total_covered_required_context, total_required_context),
        "totals": {
            "manual_findings": total_manual_findings,
            "matched_manual_findings": matched_manual_count,
            "auto_findings": total_auto_findings,
            "valid_findings": total_valid,
            "invalid_findings": total_invalid,
            "unclear_findings": total_unclear,
            "required_context_items": total_required_context,
            "covered_required_context_items": total_covered_required_context,
        },
        "fixtures": fixture_summaries,
    }


def _passes_release_gate(metrics: dict[str, Any]) -> dict[str, bool]:
    """Evaluate v0 release gates for one reporting scope.

    `None` means "not enough denominator to compute"; that is treated as not
    passing because the gate cannot be claimed from missing evidence.
    """
    return {
        "manual_recall": (metrics["manual_recall"] is not None and metrics["manual_recall"] >= 0.80),
        "precision": (metrics["precision"] is not None and metrics["precision"] >= 0.70),
        "invalid_findings_per_run": (
            metrics["invalid_findings_per_run"] is not None
            and metrics["invalid_findings_per_run"] <= 2.0
        ),
        "max_invalid_single_run": (
            metrics["max_invalid_single_run"] is not None
            and metrics["max_invalid_single_run"] <= 5
        ),
        "unclear_rate": (metrics["unclear_rate"] is not None and metrics["unclear_rate"] <= 0.15),
        "context_fidelity": (
            metrics["context_fidelity"] is not None and metrics["context_fidelity"] >= 0.80
        ),
        "actionability": (
            metrics["actionability"] is not None and metrics["actionability"] >= 0.90
        ),
        "failure_rate": (metrics["failure_rate"] is not None and metrics["failure_rate"] <= 0.10),
        "fixture_count": metrics["fixture_count"] >= 20,
    }


def _self_hosting_pool_limit_ok(fixtures: list[EvalFixture]) -> bool:
    if not fixtures:
        return True
    self_hosting_count = sum(1 for fixture in fixtures if fixture.pool == "self_hosting")
    return (self_hosting_count / len(fixtures)) <= 0.25


def evaluate_fixtures(fixtures: list[EvalFixture], *, mode: str = "release-gate") -> dict[str, Any]:
    """Aggregate fixture metrics for release-gate or regression reporting."""
    if mode not in VALID_EVAL_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_EVAL_MODES))}")

    external_fixtures = [fixture for fixture in fixtures if fixture.pool == "external"]
    overall_metrics = _evaluate_scope(fixtures)
    external_metrics = _evaluate_scope(external_fixtures)

    report = {
        "mode": mode,
        "fixture_count": len(fixtures),
        "scopes": {
            "external_only": external_metrics,
            "overall": overall_metrics,
        },
    }
    if mode == "regression":
        return report

    external_gates = _passes_release_gate(external_metrics)
    overall_gates = _passes_release_gate(overall_metrics)

    # v0-scope.md §12 exception: fixture_count gate uses overall pool size,
    # not external-only count, so early development isn't blocked by pool split.
    external_gates["fixture_count"] = overall_gates["fixture_count"]

    release_gate = {
        "primary_scope": "external_only",
        "supplementary_scope": "overall",
        "external_only": external_gates,
        "overall": overall_gates,
        "self_hosting_pool_limit_ok": _self_hosting_pool_limit_ok(fixtures),
    }
    release_gate["blocking_pass"] = (
        all(release_gate["external_only"].values())
        and release_gate["self_hosting_pool_limit_ok"]
    )
    report["release_gate"] = release_gate
    return report


def build_report(fixtures_root: Path, *, mode: str = "release-gate") -> dict[str, Any]:
    fixtures = load_fixtures(fixtures_root)
    return {
        "schema_version": "0.1-alpha",
        "fixtures_root": str(fixtures_root),
        "report": evaluate_fixtures(fixtures, mode=mode),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crossreview_eval",
        description="CrossReview dev-only eval harness.",
    )
    parser.add_argument(
        "--fixtures",
        required=True,
        metavar="DIR",
        help="Root directory containing fixture subdirectories.",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(VALID_EVAL_MODES),
        default="release-gate",
        help="Reporting mode: release-gate enforces v0 gate semantics; regression omits them.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        report = build_report(Path(args.fixtures), mode=args.mode)
    except EvalContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(to_serializable(report), indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        try:
            output_path.write_text(rendered + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"error: cannot write {output_path}: {exc}", file=sys.stderr)
            return 1
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
