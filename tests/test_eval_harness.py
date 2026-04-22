"""Tests for the dev-only eval harness."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from crossreview import schema as schema_mod
from crossreview.schema import (
    AdvisoryVerdict,
    BudgetStatus,
    Confidence,
    FileMeta,
    Finding,
    IntentCoverage,
    Locatability,
    QualityMetrics,
    ReviewPack,
    ReviewResult,
    ReviewStatus,
    ReviewerMeta,
    ResultBudget,
    Severity,
    Verdict,
    review_result_to_json,
    to_serializable,
)
from crossreview_eval import EvalContractError, build_report, evaluate_fixtures, load_fixture, main


def _write_fixture(
    root: Path,
    *,
    fixture_id: str,
    pool: str,
    review_status: ReviewStatus = ReviewStatus.COMPLETE,
    manual_findings: list[dict] | None = None,
    auto_adjudications: list[dict] | None = None,
    covered_required_context: bool | None = True,
) -> Path:
    fixture_dir = root / fixture_id
    fixture_dir.mkdir()

    pack = ReviewPack(
        diff="diff --git a/a.py b/a.py\n@@ -1 +1 @@\n-print('a')\n+print('b')\n",
        changed_files=[FileMeta(path="a.py", language="python")],
        artifact_fingerprint="artifact",
        pack_fingerprint=f"pack-{fixture_id}",
        intent="fix behavior",
    )
    result = ReviewResult(
        schema_version=schema_mod.SCHEMA_VERSION,
        artifact_fingerprint=pack.artifact_fingerprint,
        pack_fingerprint=pack.pack_fingerprint,
        review_status=review_status,
        intent_coverage=IntentCoverage.COVERED,
        raw_findings=[
            Finding(
                id="f-001",
                severity=Severity.MEDIUM,
                summary="behavior changed",
                detail="detail",
                category="logic_error",
                locatability=Locatability.EXACT,
                confidence=Confidence.PLAUSIBLE,
                file="a.py",
                line=1,
            )
        ],
        findings=[
            Finding(
                id="f-001",
                severity=Severity.MEDIUM,
                summary="behavior changed",
                detail="detail",
                category="logic_error",
                locatability=Locatability.EXACT,
                confidence=Confidence.PLAUSIBLE,
                file="a.py",
                line=1,
            )
        ],
        advisory_verdict=AdvisoryVerdict(
            verdict=Verdict.CONCERNS,
            rationale="found issue",
        ),
        quality_metrics=QualityMetrics(
            pack_completeness=0.8,
            noise_count=0,
            raw_findings_count=1,
            emitted_findings_count=1,
            locatability_distribution=schema_mod.LocalizabilityDistribution(1.0, 0.0, 0.0),
            speculative_ratio=0.0,
        ),
        reviewer=ReviewerMeta(model="claude-sonnet-4-20250514"),
        budget=ResultBudget(
            status=BudgetStatus.COMPLETE,
            files_reviewed=1,
            files_total=1,
            chars_consumed=120,
            chars_limit=1000,
        ),
    )

    if review_status in {ReviewStatus.REJECTED, ReviewStatus.FAILED}:
        result.raw_findings = []
        result.findings = []
        result.quality_metrics.raw_findings_count = 0
        result.quality_metrics.emitted_findings_count = 0
        result.advisory_verdict = AdvisoryVerdict(
            verdict=Verdict.INCONCLUSIVE,
            rationale="runtime failed",
        )

    (fixture_dir / "fixture.yaml").write_text(
        yaml.safe_dump(
            {
                "fixture_id": fixture_id,
                "pool": pool,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    (fixture_dir / "pack.json").write_text(
        json.dumps(to_serializable(pack), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (fixture_dir / "review-result.json").write_text(
        review_result_to_json(result),
        encoding="utf-8",
    )
    (fixture_dir / "manual-findings.yaml").write_text(
        yaml.safe_dump(
            {
                "fixture_id": fixture_id,
                "source": "manual_fresh_session",
                "reviewer_model": "claude-sonnet-4-20250514",
                "reviewed_at": "2026-04-21T20:00:00+08:00",
                "context_items": [
                    {
                        "type": "diff",
                        "path_or_desc": "a.py",
                        "required": True,
                        "covered_by_pack": covered_required_context,
                    }
                ],
                "findings": manual_findings
                or [
                    {
                        "id": "mf-001",
                        "summary": "behavior changed",
                        "file": "a.py",
                        "severity_estimate": "medium",
                    }
                ],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    default_auto_adjudications = [
        {
            "auto_finding_id": "f-001",
            "judgment": "valid",
            "matched_manual_id": "mf-001",
            "actionability_judgment": "actionable",
        }
    ]
    if review_status in {ReviewStatus.REJECTED, ReviewStatus.FAILED}:
        default_auto_adjudications = []

    (fixture_dir / "auto-adjudications.yaml").write_text(
        yaml.safe_dump(
            {
                "fixture_id": fixture_id,
                "run_id": f"run-{fixture_id}",
                "adjudicated_at": "2026-04-21T20:05:00+08:00",
                "findings": auto_adjudications
                if auto_adjudications is not None
                else default_auto_adjudications,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return fixture_dir


class TestEvalHarness:
    def test_load_fixture_validates_cross_file_links(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        fixture = load_fixture(fixture_dir)
        assert fixture.fixture_id == "001-auth"
        assert fixture.pool == "external"
        assert fixture.review_result.pack_fingerprint == fixture.pack.pack_fingerprint

    def test_load_fixture_rejects_unknown_auto_finding_id(self, tmp_path):
        fixture_dir = _write_fixture(
            tmp_path,
            fixture_id="001-auth",
            pool="external",
            auto_adjudications=[
                {
                    "auto_finding_id": "f-999",
                    "judgment": "valid",
                    "matched_manual_id": "mf-001",
                    "actionability_judgment": "actionable",
                }
            ],
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "auto_finding_id 'f-999'" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_requires_adjudication_for_every_emitted_finding(self, tmp_path):
        fixture_dir = _write_fixture(
            tmp_path,
            fixture_id="001-auth",
            pool="external",
            auto_adjudications=[],
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "missing adjudications" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_requires_adjudication_for_every_raw_finding(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        broken = json.loads((fixture_dir / "review-result.json").read_text(encoding="utf-8"))
        broken["raw_findings"].append(
            {
                "id": "f-002",
                "severity": "low",
                "summary": "extra raw finding",
                "detail": "detail",
                "category": "style",
                "locatability": "file_only",
                "confidence": "speculative",
                "evidence_related_file": False,
                "actionable": False,
                "file": "a.py",
                "line": None,
                "diff_hunk": None,
                "requirement_ref": None,
            }
        )
        broken["quality_metrics"]["raw_findings_count"] = 2
        (fixture_dir / "review-result.json").write_text(
            json.dumps(broken, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "missing adjudications for review-result raw_findings" in str(exc)
            assert "f-002" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_rejects_invalid_review_result_shape(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        broken = json.loads((fixture_dir / "review-result.json").read_text(encoding="utf-8"))
        broken["reviewer"]["model"] = ""
        (fixture_dir / "review-result.json").write_text(
            json.dumps(broken, indent=2),
            encoding="utf-8",
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "invalid ReviewResult" in str(exc)
            assert "reviewer_model_required" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_wraps_malformed_pack_payload(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        broken = json.loads((fixture_dir / "pack.json").read_text(encoding="utf-8"))
        broken["changed_files"] = [{}]
        (fixture_dir / "pack.json").write_text(
            json.dumps(broken, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "invalid ReviewPack payload" in str(exc)
            assert "'path'" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_rejects_eval_contract_mismatch(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        broken = json.loads((fixture_dir / "review-result.json").read_text(encoding="utf-8"))
        broken["quality_metrics"]["raw_findings_count"] = 99
        (fixture_dir / "review-result.json").write_text(
            json.dumps(broken, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "invalid eval ReviewResult contract" in str(exc)
            assert "raw_findings_count_mismatch" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_load_fixture_rejects_missing_advisory_verdict(self, tmp_path):
        fixture_dir = _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        broken = json.loads((fixture_dir / "review-result.json").read_text(encoding="utf-8"))
        broken.pop("advisory_verdict", None)
        (fixture_dir / "review-result.json").write_text(
            json.dumps(broken, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            load_fixture(fixture_dir)
        except EvalContractError as exc:
            assert "invalid eval ReviewResult contract" in str(exc)
            assert "advisory_verdict_required" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_build_report_aggregates_external_and_overall_scopes(self, tmp_path):
        _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        _write_fixture(
            tmp_path,
            fixture_id="002-self-host",
            pool="self_hosting",
            auto_adjudications=[
                {
                    "auto_finding_id": "f-001",
                    "judgment": "invalid",
                    "matched_manual_id": None,
                    "actionability_judgment": "not_actionable",
                }
            ],
            covered_required_context=False,
        )

        report = build_report(tmp_path)["report"]
        external = report["scopes"]["external_only"]
        overall = report["scopes"]["overall"]

        assert external["fixture_count"] == 1
        assert external["manual_recall"] == 1.0
        assert external["precision"] == 1.0
        assert overall["fixture_count"] == 2
        assert overall["precision"] == 0.5
        assert overall["context_fidelity"] == 0.5
        assert report["mode"] == "release-gate"
        assert report["release_gate"]["primary_scope"] == "external_only"

    def test_build_report_treats_rejected_and_failed_as_failures(self, tmp_path):
        _write_fixture(
            tmp_path,
            fixture_id="001-failed",
            pool="external",
            review_status=ReviewStatus.FAILED,
            manual_findings=[],
            auto_adjudications=[],
        )
        report = build_report(tmp_path)["report"]
        external = report["scopes"]["external_only"]
        assert external["failed_runs"] == 1
        assert external["failure_rate"] == 1.0

    def test_actionability_uses_all_valid_findings_as_denominator(self, tmp_path):
        _write_fixture(
            tmp_path,
            fixture_id="001-auth",
            pool="external",
            auto_adjudications=[
                {
                    "auto_finding_id": "f-001",
                    "judgment": "valid",
                    "matched_manual_id": "mf-001",
                    "actionability_judgment": "unclear",
                }
            ],
        )
        report = build_report(tmp_path)["report"]
        external = report["scopes"]["external_only"]
        assert external["totals"]["valid_findings"] == 1
        assert external["actionability"] == 0.0

    def test_release_gate_uses_external_only_for_primary_metrics(self, tmp_path):
        _write_fixture(
            tmp_path,
            fixture_id="001-external-good",
            pool="external",
        )
        _write_fixture(
            tmp_path,
            fixture_id="002-self-bad",
            pool="self_hosting",
            auto_adjudications=[
                {
                    "auto_finding_id": "f-001",
                    "judgment": "invalid",
                    "matched_manual_id": None,
                    "actionability_judgment": "not_actionable",
                }
            ],
        )

        report = build_report(tmp_path)["report"]
        assert report["release_gate"]["external_only"]["precision"] is True
        assert report["release_gate"]["overall"]["precision"] is False

    def test_fixture_count_gate_uses_overall_pool(self, tmp_path):
        for index in range(1, 21):
            pool = "external" if index == 1 else "self_hosting"
            _write_fixture(
                tmp_path,
                fixture_id=f"{index:03d}-fixture",
                pool=pool,
            )

        report = build_report(tmp_path)["report"]
        assert report["scopes"]["external_only"]["fixture_count"] == 1
        assert report["scopes"]["overall"]["fixture_count"] == 20
        assert report["release_gate"]["external_only"]["fixture_count"] is True
        # 95% self-hosting exceeds 25% limit
        assert report["release_gate"]["self_hosting_pool_limit_ok"] is False
        assert report["release_gate"]["blocking_pass"] is False

    def test_context_fidelity_excludes_unreviewed_required_items(self, tmp_path):
        _write_fixture(
            tmp_path,
            fixture_id="001-auth",
            pool="external",
            covered_required_context=None,
        )

        report = build_report(tmp_path)["report"]
        external = report["scopes"]["external_only"]
        assert external["totals"]["required_context_items"] == 0
        assert external["totals"]["covered_required_context_items"] == 0
        assert external["context_fidelity"] is None

    def test_load_fixtures_ignores_non_fixture_directories(self, tmp_path):
        _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        # Hidden directory (e.g. .git)
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        # Non-hidden junk directory without fixture.yaml
        scratch_dir = tmp_path / "scratch"
        scratch_dir.mkdir()
        (scratch_dir / "notes.txt").write_text("wip\n", encoding="utf-8")

        report = build_report(tmp_path)["report"]
        assert report["fixture_count"] == 1
        assert report["scopes"]["overall"]["fixture_count"] == 1

    def test_load_fixtures_rejects_incomplete_fixture_directory(self, tmp_path):
        _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        # Directory with fixture artifacts but no fixture.yaml manifest
        broken_dir = tmp_path / "002-broken"
        broken_dir.mkdir()
        (broken_dir / "pack.json").write_text("{}", encoding="utf-8")

        try:
            build_report(tmp_path)
        except EvalContractError as exc:
            assert "missing fixture.yaml" in str(exc)
            assert "pack.json" in str(exc)
        else:
            raise AssertionError("expected EvalContractError")

    def test_regression_mode_omits_release_gate_blocking(self, tmp_path):
        _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        _write_fixture(tmp_path, fixture_id="002-self-host", pool="self_hosting")

        report = build_report(tmp_path, mode="regression")["report"]
        assert report["mode"] == "regression"
        assert "release_gate" not in report
        assert report["scopes"]["overall"]["fixture_count"] == 2

    def test_evaluate_fixtures_rejects_unknown_mode(self, tmp_path):
        _write_fixture(tmp_path, fixture_id="001-auth", pool="external")
        fixtures = [load_fixture(tmp_path / "001-auth")]

        try:
            evaluate_fixtures(fixtures, mode="unknown")
        except ValueError as exc:
            assert "mode must be one of" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_main_writes_output_file(self, tmp_path, capsys):
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, fixture_id="001-auth", pool="external")
        output_path = tmp_path / "report.json"
        rc = main(["--fixtures", str(fixtures_dir), "--output", str(output_path)])
        assert rc == 0
        rendered = json.loads(output_path.read_text(encoding="utf-8"))
        assert rendered["report"]["fixture_count"] == 1
        assert '"fixture_count": 1' in capsys.readouterr().out

    def test_main_returns_error_when_output_path_unwritable(self, tmp_path, capsys):
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, fixture_id="001-auth", pool="external")

        rc = main(["--fixtures", str(fixtures_dir), "--output", str(tmp_path)])

        assert rc == 1
        assert f"error: cannot write {tmp_path}" in capsys.readouterr().err

    def test_main_supports_regression_mode(self, tmp_path, capsys):
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        _write_fixture(fixtures_dir, fixture_id="001-auth", pool="external")

        rc = main(["--fixtures", str(fixtures_dir), "--mode", "regression"])

        assert rc == 0
        rendered = json.loads(capsys.readouterr().out)
        assert rendered["report"]["mode"] == "regression"
        assert "release_gate" not in rendered["report"]
