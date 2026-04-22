"""Tests for crossreview.schema — covers 1A.1, 1A.2, 1A.3.

Validates:
  - ReviewPack, Finding, ReviewResult structural correctness and defaults
  - Finding severity constraints (v0-scope.md §7 constraint rules)
  - ReviewPack / ReviewResult required-field validation
  - Finding ID format (f-NNN)
  - Category naming (snake_case, non-empty)
  - Fingerprint computation
  - Enum coverage
"""

import pytest

from crossreview.schema import (
    AdvisoryVerdict,
    ArtifactType,
    BudgetStatus,
    Confidence,
    ContextFile,
    Evidence,
    EvidenceStatus,
    FileMeta,
    Finding,
    IntentCoverage,
    Locatability,
    PackBudget,
    ResultBudget,
    ReviewerConfig,
    ReviewerFailureReason,
    ReviewerMeta,
    ReviewPack,
    ReviewResult,
    ReviewStatus,
    Severity,
    Verdict,
    compute_fingerprint,
    validate_eval_review_result_contract,
    validate_category,
    validate_finding_constraints,
    validate_finding_id,
    validate_review_pack,
    validate_review_result,
    SCHEMA_VERSION,
)


# ===== ReviewPack =====

class TestReviewPack:
    """1A.1 — ReviewPack schema tests."""

    def test_default_schema_version(self):
        pack = ReviewPack()
        assert pack.schema_version == SCHEMA_VERSION

    def test_artifact_type_code_diff_only(self):
        pack = ReviewPack()
        assert pack.artifact_type == ArtifactType.CODE_DIFF
        assert pack.artifact_type.value == "code_diff"

    def test_required_fields_have_defaults(self):
        """ReviewPack can be constructed with no args — all fields have defaults."""
        pack = ReviewPack()
        assert pack.diff == ""
        assert pack.changed_files == []
        assert pack.artifact_fingerprint == ""
        assert pack.pack_fingerprint == ""

    def test_optional_fields_null_by_default(self):
        """context_files, evidence, task_file, intent, focus default to None."""
        pack = ReviewPack()
        assert pack.intent is None
        assert pack.task_file is None
        assert pack.focus is None
        assert pack.context_files is None
        assert pack.evidence is None

    def test_budget_default(self):
        pack = ReviewPack()
        assert pack.budget.max_files is None
        assert pack.budget.max_chars_total is None
        assert pack.budget.timeout_sec is None

    def test_full_pack_construction(self):
        """Construct a pack with all fields populated — mirrors a real fixture."""
        pack = ReviewPack(
            diff="--- a/foo.py\n+++ b/foo.py\n",
            changed_files=[FileMeta(path="foo.py", language="python")],
            artifact_fingerprint="abc123",
            pack_fingerprint="def456",
            intent="Fix bug in auth module",
            task_file="Full task description...",
            focus=["auth", "session"],
            context_files=[ContextFile(path="plan.md", content="...")],
            evidence=[Evidence(source="pytest", status=EvidenceStatus.PASS, summary="all passed")],
            budget=PackBudget(max_files=10, max_chars_total=50000, timeout_sec=120),
        )
        assert pack.artifact_type == ArtifactType.CODE_DIFF
        assert len(pack.changed_files) == 1
        assert pack.changed_files[0].path == "foo.py"
        assert pack.focus == ["auth", "session"]

    def test_context_files_empty_list_vs_none(self):
        """Empty list and None are both valid but semantically different."""
        pack_none = ReviewPack(context_files=None)
        pack_empty = ReviewPack(context_files=[])
        assert pack_none.context_files is None
        assert pack_empty.context_files == []


# ===== ReviewPack Validation =====

class TestReviewPackValidation:
    """1A.1 — Required-field validation for ReviewPack."""

    def test_empty_pack_fails_validation(self):
        """Default-constructed pack has empty required fields → violations."""
        pack = ReviewPack()
        violations = validate_review_pack(pack)
        assert "diff_required" in violations
        assert "changed_files_required" in violations
        assert "artifact_fingerprint_required" in violations
        assert "pack_fingerprint_required" in violations

    def test_valid_pack_passes(self):
        """Pack with required fields populated → no violations."""
        pack = ReviewPack(
            diff="--- a/foo.py\n+++ b/foo.py\n",
            changed_files=[FileMeta(path="foo.py")],
            artifact_fingerprint="abc123",
            pack_fingerprint="def456",
        )
        assert validate_review_pack(pack) == []

    def test_diff_only_still_fails(self):
        """diff present but changed_files empty → violation."""
        pack = ReviewPack(diff="some diff")
        violations = validate_review_pack(pack)
        assert "diff_required" not in violations
        assert "changed_files_required" in violations

    def test_changed_files_only_still_fails(self):
        """changed_files present but diff empty → violation."""
        pack = ReviewPack(changed_files=[FileMeta(path="a.py")])
        violations = validate_review_pack(pack)
        assert "diff_required" in violations
        assert "changed_files_required" not in violations

    def test_schema_version_required(self):
        """Blank schema_version → violation."""
        pack = ReviewPack(
            schema_version="",
            diff="diff",
            changed_files=[FileMeta(path="a.py")],
        )
        violations = validate_review_pack(pack)
        assert "schema_version_required" in violations


# ===== Finding =====

class TestFinding:
    """1A.2 — Finding schema tests."""

    @pytest.fixture
    def valid_finding(self) -> Finding:
        return Finding(
            id="f-001",
            severity=Severity.MEDIUM,
            summary="Missing null check",
            detail="The function does not handle None input.",
            category="logic_error",
            locatability=Locatability.EXACT,
            confidence=Confidence.PLAUSIBLE,
            file="src/auth.py",
            line=42,
        )

    def test_finding_defaults(self, valid_finding):
        assert valid_finding.evidence_related_file is False
        assert valid_finding.actionable is True
        assert valid_finding.diff_hunk is None
        assert valid_finding.requirement_ref is None

    def test_category_is_str(self, valid_finding):
        """category is str, not enum — per design decision."""
        assert isinstance(valid_finding.category, str)
        assert valid_finding.category == "logic_error"

    def test_finding_all_optional_fields(self):
        """Construct a minimal finding with all optional fields None."""
        f = Finding(
            id="f-002",
            severity=Severity.NOTE,
            summary="General observation",
            detail="...",
            category="suggestion",
            locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE,
        )
        assert f.file is None
        assert f.line is None
        assert f.actionable is True  # default, but constraints would flag this


# ===== Finding Constraints =====

class TestFindingConstraints:
    """1A.2 — Severity × locatability × confidence constraint rules."""

    def test_valid_high_severity(self):
        """high + exact + plausible = valid."""
        f = Finding(
            id="f-001", severity=Severity.HIGH, summary="s", detail="d",
            category="logic_error", locatability=Locatability.EXACT,
            confidence=Confidence.PLAUSIBLE, file="a.py", line=1,
        )
        assert validate_finding_constraints(f) == []

    def test_high_requires_exact_and_plausible(self):
        """high severity without exact locatability or plausible confidence → violation."""
        f = Finding(
            id="f-001", severity=Severity.HIGH, summary="s", detail="d",
            category="logic_error", locatability=Locatability.FILE_ONLY,
            confidence=Confidence.PLAUSIBLE, file="a.py",
        )
        violations = validate_finding_constraints(f)
        assert "high_requires_exact_and_plausible" in violations

    def test_speculative_severity_cap(self):
        """speculative + high → violation (cap at medium)."""
        f = Finding(
            id="f-001", severity=Severity.HIGH, summary="s", detail="d",
            category="logic_error", locatability=Locatability.EXACT,
            confidence=Confidence.SPECULATIVE, file="a.py", line=1,
            actionable=False,
        )
        violations = validate_finding_constraints(f)
        assert "speculative_severity_cap" in violations

    def test_speculative_medium_is_ok(self):
        """speculative + medium → no severity cap violation."""
        f = Finding(
            id="f-001", severity=Severity.MEDIUM, summary="s", detail="d",
            category="logic_error", locatability=Locatability.EXACT,
            confidence=Confidence.SPECULATIVE, file="a.py", line=1,
            actionable=False,
        )
        violations = validate_finding_constraints(f)
        assert "speculative_severity_cap" not in violations

    def test_no_location_severity_cap(self):
        """locatability=none + medium → violation (cap at low)."""
        f = Finding(
            id="f-001", severity=Severity.MEDIUM, summary="s", detail="d",
            category="logic_error", locatability=Locatability.NONE,
            confidence=Confidence.PLAUSIBLE,
        )
        violations = validate_finding_constraints(f)
        assert "no_location_severity_cap" in violations

    def test_speculative_none_must_be_note(self):
        """speculative + none + anything other than note → violation."""
        f = Finding(
            id="f-001", severity=Severity.LOW, summary="s", detail="d",
            category="suggestion", locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE, actionable=False,
        )
        violations = validate_finding_constraints(f)
        assert "speculative_none_is_note" in violations

    def test_speculative_none_note_is_valid(self):
        """speculative + none + note = valid (the only valid combo for this pair)."""
        f = Finding(
            id="f-001", severity=Severity.NOTE, summary="s", detail="d",
            category="suggestion", locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE, actionable=False,
        )
        violations = validate_finding_constraints(f)
        assert "speculative_none_is_note" not in violations

    def test_speculative_not_actionable(self):
        """speculative + actionable=True → violation."""
        f = Finding(
            id="f-001", severity=Severity.NOTE, summary="s", detail="d",
            category="suggestion", locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE, actionable=True,
        )
        violations = validate_finding_constraints(f)
        assert "speculative_not_actionable" in violations

    def test_plausible_actionable_ok(self):
        """plausible + actionable=True → no violation."""
        f = Finding(
            id="f-001", severity=Severity.LOW, summary="s", detail="d",
            category="logic_error", locatability=Locatability.FILE_ONLY,
            confidence=Confidence.PLAUSIBLE, file="a.py",
        )
        violations = validate_finding_constraints(f)
        assert "speculative_not_actionable" not in violations

    def test_multiple_violations(self):
        """A single finding can violate multiple rules."""
        f = Finding(
            id="f-001", severity=Severity.HIGH, summary="s", detail="d",
            category="suggestion", locatability=Locatability.NONE,
            confidence=Confidence.SPECULATIVE, actionable=True,
        )
        violations = validate_finding_constraints(f)
        # Should hit: high_requires_exact_and_plausible, speculative_severity_cap,
        # no_location_severity_cap, speculative_none_is_note, speculative_not_actionable
        assert len(violations) >= 4


# ===== Finding ID & Category Validation =====

class TestFindingValidation:
    """1A.2 — ID format and category naming."""

    @pytest.mark.parametrize("fid,expected", [
        ("f-001", True),
        ("f-010", True),
        ("f-999", True),
        ("f-1", False),       # too short
        ("f-0001", False),    # too long
        ("F-001", False),     # uppercase
        ("g-001", False),     # wrong prefix
        ("f001", False),      # no dash
        ("", False),
    ])
    def test_finding_id_format(self, fid, expected):
        assert validate_finding_id(fid) == expected

    @pytest.mark.parametrize("cat,expected", [
        ("logic_error", True),
        ("missing_test", True),
        ("spec_mismatch", True),
        ("security", True),
        ("performance", True),
        ("over_engineering", True),
        ("scope_drift", True),
        ("missing_verification", True),
        ("suggestion", True),
        ("style", True),
        ("a", True),
        ("a1b", True),
        ("", False),
        ("Logic_Error", False),     # uppercase
        ("logic-error", False),     # hyphen, not underscore
        ("123_bad", False),         # starts with digit
        ("with spaces", False),
    ])
    def test_category_naming(self, cat, expected):
        assert validate_category(cat) == expected


# ===== ReviewResult =====

class TestReviewResult:
    """1A.3 — ReviewResult schema tests (full shell per v0-scope.md)."""

    def test_default_construction(self):
        """ReviewResult can be constructed with defaults — full shell, all nullable."""
        result = ReviewResult()
        assert result.schema_version == SCHEMA_VERSION
        assert result.review_status == ReviewStatus.COMPLETE
        assert result.intent_coverage == IntentCoverage.UNKNOWN
        assert result.raw_findings == []
        assert result.findings == []
        assert result.evidence == []
        assert result.advisory_verdict.verdict == Verdict.INCONCLUSIVE
        assert result.reviewer.type == "fresh_llm"
        assert result.budget.status == BudgetStatus.COMPLETE

    def test_reviewer_meta_defaults(self):
        result = ReviewResult()
        assert result.reviewer.model == ""
        assert result.reviewer.session_isolated is True
        assert result.reviewer.failure_reason is None
        assert result.reviewer.raw_analysis is None
        assert result.reviewer.latency_sec is None

    def test_quality_metrics_defaults(self):
        result = ReviewResult()
        assert result.quality_metrics.pack_completeness == 0.0
        assert result.quality_metrics.noise_count == 0
        assert result.quality_metrics.speculative_ratio == 0.0

    def test_budget_defaults(self):
        result = ReviewResult()
        assert result.budget.files_reviewed == 0
        assert result.budget.files_total == 0
        assert result.budget.chars_limit is None

    def test_full_result_construction(self):
        """Construct a complete result — simulates a full pipeline run."""
        finding = Finding(
            id="f-001", severity=Severity.MEDIUM, summary="s", detail="d",
            category="logic_error", locatability=Locatability.EXACT,
            confidence=Confidence.PLAUSIBLE, file="a.py", line=10,
        )
        result = ReviewResult(
            review_status=ReviewStatus.COMPLETE,
            intent_coverage=IntentCoverage.COVERED,
            findings=[finding],
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.CONCERNS,
                rationale="1 medium finding in auth module",
            ),
            reviewer=ReviewerMeta(
                model="claude-sonnet-4-20250514",
                raw_analysis="The diff shows...",
                latency_sec=3.2,
                input_tokens=1500,
                output_tokens=800,
            ),
            budget=ResultBudget(
                status=BudgetStatus.COMPLETE,
                files_reviewed=3,
                files_total=3,
                chars_consumed=12000,
                chars_limit=50000,
            ),
        )
        assert len(result.findings) == 1
        assert result.reviewer.model == "claude-sonnet-4-20250514"
        assert result.budget.files_reviewed == 3

    def test_failed_result(self):
        """Simulate a failed review — reviewer error path."""
        result = ReviewResult(
            review_status=ReviewStatus.FAILED,
            reviewer=ReviewerMeta(
                model="claude-sonnet-4-20250514",
                failure_reason=ReviewerFailureReason.TIMEOUT,
            ),
            advisory_verdict=AdvisoryVerdict(
                verdict=Verdict.INCONCLUSIVE,
                rationale="Reviewer timed out",
            ),
        )
        assert result.review_status == ReviewStatus.FAILED
        assert result.reviewer.failure_reason == ReviewerFailureReason.TIMEOUT


# ===== ReviewResult Validation =====

class TestReviewResultValidation:
    """1A.3 — Required-field validation for ReviewResult."""

    def test_default_result_fails_validation(self):
        """Default-constructed result has empty fingerprints and model → violations."""
        result = ReviewResult()
        violations = validate_review_result(result)
        assert "artifact_fingerprint_required" in violations
        assert "pack_fingerprint_required" in violations
        assert "reviewer_model_required" in violations

    def test_valid_result_passes(self):
        """Result with required fields populated → no violations."""
        result = ReviewResult(
            artifact_fingerprint="abc123",
            pack_fingerprint="def456",
            reviewer=ReviewerMeta(model="claude-sonnet-4-20250514"),
        )
        assert validate_review_result(result) == []

    def test_missing_model_only(self):
        """Fingerprints present but model empty → only reviewer_model_required."""
        result = ReviewResult(
            artifact_fingerprint="abc",
            pack_fingerprint="def",
        )
        violations = validate_review_result(result)
        assert violations == ["reviewer_model_required"]

    def test_eval_contract_requires_explicit_runtime_fields(self):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "artifact_fingerprint": "abc123",
            "pack_fingerprint": "def456",
            "review_status": "complete",
            "advisory_verdict": {
                "verdict": "concerns",
                "rationale": "found issue",
            },
            "raw_findings": [],
            "findings": [],
            "quality_metrics": {
                "pack_completeness": 0.8,
                "noise_count": 0,
                "raw_findings_count": 0,
                "emitted_findings_count": 0,
                "locatability_distribution": {
                    "exact_pct": 0.0,
                    "file_only_pct": 0.0,
                    "none_pct": 0.0,
                },
                "speculative_ratio": 0.0,
            },
            "reviewer": {
                "type": "fresh_llm",
                "model": "claude-sonnet-4-20250514",
                "session_isolated": True,
            },
            "budget": {
                "status": "complete",
                "files_reviewed": 0,
                "files_total": 0,
                "chars_consumed": 0,
                "chars_limit": None,
            },
        }
        assert validate_eval_review_result_contract(payload) == []

    def test_eval_contract_rejects_raw_findings_count_mismatch(self):
        payload = {
            "review_status": "complete",
            "advisory_verdict": {"verdict": "concerns"},
            "raw_findings": [{"id": "f-001"}],
            "findings": [],
            "quality_metrics": {
                "raw_findings_count": 0,
                "emitted_findings_count": 0,
                "noise_count": 0,
                "speculative_ratio": 0.0,
            },
            "reviewer": {"model": "claude-sonnet-4-20250514"},
        }
        violations = validate_eval_review_result_contract(payload)
        assert "raw_findings_count_mismatch" in violations

    def test_eval_contract_requires_advisory_verdict_verdict(self):
        payload = {
            "review_status": "complete",
            "advisory_verdict": {},
            "raw_findings": [],
            "findings": [],
            "quality_metrics": {
                "raw_findings_count": 0,
                "emitted_findings_count": 0,
                "noise_count": 0,
                "speculative_ratio": 0.0,
            },
            "reviewer": {"model": "claude-sonnet-4-20250514"},
        }
        violations = validate_eval_review_result_contract(payload)
        assert "advisory_verdict_verdict_required" in violations

    def test_findings_from_data_rejects_missing_required_keys(self):
        """Parser-level guard: a finding missing required keys (e.g. severity)
        raises ValueError, which load_fixture() wraps into EvalContractError."""
        from crossreview.schema import review_result_from_dict

        base = {
            "review_status": "complete",
            "advisory_verdict": {"verdict": "pass_candidate", "rationale": "ok"},
            "reviewer": {"model": "test"},
            "quality_metrics": {
                "raw_findings_count": 1,
                "emitted_findings_count": 1,
                "noise_count": 0,
                "speculative_ratio": 0.0,
            },
            "raw_findings": [{"id": "f-001"}],
            "findings": [{"id": "f-001"}],
        }
        try:
            review_result_from_dict(base)
        except ValueError as exc:
            assert "missing required keys" in str(exc)
            assert "severity" in str(exc)
        else:
            raise AssertionError("expected ValueError for finding missing required keys")


# ===== Enum Coverage =====

class TestEnumCompleteness:
    """Verify all v0-scope.md enum values are represented."""

    def test_severity_values(self):
        assert set(s.value for s in Severity) == {"high", "medium", "low", "note"}

    def test_locatability_values(self):
        assert set(loc.value for loc in Locatability) == {"exact", "file_only", "none"}

    def test_confidence_values(self):
        assert set(c.value for c in Confidence) == {"plausible", "speculative"}

    def test_verdict_values(self):
        assert set(v.value for v in Verdict) == {
            "pass_candidate", "concerns", "needs_human_triage", "inconclusive"
        }

    def test_review_status_values(self):
        assert set(s.value for s in ReviewStatus) == {
            "complete", "truncated", "rejected", "failed"
        }

    def test_evidence_status_values(self):
        assert set(s.value for s in EvidenceStatus) == {
            "pass", "fail", "error", "skipped"
        }

    def test_reviewer_failure_reason_values(self):
        expected = {
            "timeout", "budget_exceeded", "model_error", "output_malformed",
            "context_too_large", "input_invalid", "rate_limited",
        }
        assert set(r.value for r in ReviewerFailureReason) == expected


# ===== Fingerprint =====

class TestFingerprint:
    def test_compute_fingerprint_deterministic(self):
        fp1 = compute_fingerprint("hello")
        fp2 = compute_fingerprint("hello")
        assert fp1 == fp2

    def test_compute_fingerprint_different_content(self):
        fp1 = compute_fingerprint("hello")
        fp2 = compute_fingerprint("world")
        assert fp1 != fp2

    def test_fingerprint_is_hex(self):
        fp = compute_fingerprint("test")
        assert all(c in "0123456789abcdef" for c in fp)
        assert len(fp) == 64  # SHA-256


# ===== ReviewerConfig =====

class TestReviewerConfig:
    """1A.4 — ReviewerConfig structure."""

    def test_construction(self):
        cfg = ReviewerConfig(
            provider="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env="ANTHROPIC_API_KEY",
        )
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.api_key_env == "ANTHROPIC_API_KEY"

    def test_openai_config(self):
        cfg = ReviewerConfig(
            provider="openai",
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
        )
        assert cfg.provider == "openai"


# ===== Sub-structures =====

class TestSubStructures:
    def test_file_meta(self):
        fm = FileMeta(path="src/auth.py", language="python")
        assert fm.path == "src/auth.py"
        assert fm.language == "python"

    def test_file_meta_no_language(self):
        fm = FileMeta(path="README.md")
        assert fm.language is None

    def test_context_file(self):
        cf = ContextFile(path="plan.md", content="...", role="plan")
        assert cf.path == "plan.md"
        assert cf.role == "plan"

    def test_evidence(self):
        ev = Evidence(
            source="pytest",
            status=EvidenceStatus.FAIL,
            summary="2 tests failed",
            command="pytest tests/",
            detail="FAILED test_auth.py::test_login",
        )
        assert ev.status == EvidenceStatus.FAIL

    def test_pack_budget(self):
        b = PackBudget(max_files=5, max_chars_total=10000, timeout_sec=60)
        assert b.max_files == 5

    def test_advisory_verdict(self):
        from crossreview.schema import AdvisoryVerdict
        av = AdvisoryVerdict(verdict=Verdict.CONCERNS, rationale="found issues")
        assert av.verdict == Verdict.CONCERNS
