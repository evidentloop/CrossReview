"""Tests for deterministic finding normalization."""

from __future__ import annotations

from crossreview.normalizer import normalize_review_output
from crossreview.schema import (
    Confidence,
    ContextFile,
    Evidence,
    EvidenceStatus,
    FileMeta,
    Locatability,
    ReviewPack,
    Severity,
)


PACK = ReviewPack(
    diff="diff --git a/src/auth.py b/src/auth.py\n@@ -1 +1 @@\n-print('a')\n+print('b')\n",
    changed_files=[FileMeta(path="src/auth.py", language="python")],
    artifact_fingerprint="artifact",
    pack_fingerprint="pack",
    evidence=[
        Evidence(
            source="pytest",
            status=EvidenceStatus.FAIL,
            summary="src/auth.py failed",
            detail="src/auth.py::test_auth failed",
        )
    ],
    context_files=[ContextFile(path="plan.md", content="context")],
)


RAW_OUTPUT = """\
## Section 1: Findings

**f-001**
- **Where**: `src/auth.py`, line 42
- **What**: Missing null guard causes a crash in the new code path.
- **Why**: The diff removes the only None check before the value is dereferenced.
- **Severity estimate**: HIGH
- **Category**: logic_error

**f-002**
- **Where**: `src/auth.py`
- **What**: This might break callers in edge cases.
- **Why**: Possibly depends on behavior outside the diff.
- **Severity estimate**: MEDIUM
- **Category**: suggestion

## Section 2: Observations

**o-001**
- **Where**: `src/auth.py`
- **What**: observation only
- **Why**: not diff-verifiable
"""


class TestNormalizer:
    def test_parses_findings_and_ignores_observations(self):
        result = normalize_review_output(RAW_OUTPUT, PACK)
        assert result.raw_findings_count == 2
        assert len(result.raw_findings) == 2
        assert len(result.findings) == 2
        assert result.findings[0].id == "f-001"
        assert result.findings[0].locatability == Locatability.EXACT

    def test_confidence_and_constraints_are_applied(self):
        result = normalize_review_output(RAW_OUTPUT, PACK)
        first, second = result.findings
        assert first.severity == Severity.HIGH
        assert first.confidence == Confidence.PLAUSIBLE
        assert first.evidence_related_file is True
        assert second.confidence == Confidence.SPECULATIVE
        assert second.severity == Severity.MEDIUM
        assert second.actionable is False

    def test_noise_cap_truncates(self):
        result = normalize_review_output(RAW_OUTPUT, PACK, max_findings=1)
        assert result.raw_findings_count == 2
        assert len(result.raw_findings) == 2
        assert result.emitted_findings_count == 1
        assert len(result.findings) == 1
        assert result.findings[0].id == "f-001"
        assert result.noise_count >= 1

    def test_noise_cap_sorts_by_constrained_severity_before_truncation(self):
        raw = """\
## Section 1: Findings

**f-001**
- **Where**: `src/auth.py`
- **What**: Minor style issue in the new code path.
- **Why**: Style only.
- **Severity estimate**: LOW
- **Category**: style

**f-002**
- **Where**: `src/auth.py`, line 8
- **What**: Missing authorization check allows unintended access.
- **Why**: The new branch returns before the auth guard runs.
- **Severity estimate**: HIGH
- **Category**: logic_error
"""
        result = normalize_review_output(raw, PACK, max_findings=1)
        assert [finding.id for finding in result.raw_findings] == ["f-001", "f-002"]
        assert [finding.id for finding in result.findings] == ["f-002"]

    def test_noise_cap_prefers_evidence_related_file_on_severity_tie(self):
        raw = """\
## Section 1: Findings

**f-001**
- **Where**: `src/other.py`, line 5
- **What**: Missing validation in the new branch causes a crash.
- **Why**: The diff removed the guard before dereferencing the value.
- **Severity estimate**: MEDIUM
- **Category**: logic_error

**f-002**
- **Where**: `src/auth.py`, line 7
- **What**: Missing validation in the auth branch causes a crash.
- **Why**: The diff removed the guard before dereferencing the value.
- **Severity estimate**: MEDIUM
- **Category**: logic_error
"""
        pack = ReviewPack(
            diff=PACK.diff,
            changed_files=[
                FileMeta(path="src/auth.py", language="python"),
                FileMeta(path="src/other.py", language="python"),
            ],
            artifact_fingerprint="artifact",
            pack_fingerprint="pack",
            evidence=[
                Evidence(
                    source="pytest",
                    status=EvidenceStatus.FAIL,
                    summary="src/auth.py failed",
                    detail="src/auth.py::test_auth failed",
                )
            ],
        )
        result = normalize_review_output(raw, pack, max_findings=1)
        assert [finding.id for finding in result.raw_findings] == ["f-001", "f-002"]
        assert [finding.id for finding in result.findings] == ["f-002"]

    def test_supports_heading_style_ids(self):
        raw = """\
## Section 1: Findings

### f-001
- **Where**: `src/auth.py`, line 3
- **What**: Missing validation on the new branch.
- **Why**: The guard was removed from the diff.
- **Severity estimate**: MEDIUM
- **Category**: missing_validation
"""
        result = normalize_review_output(raw, PACK)
        assert len(result.findings) == 1
        assert result.findings[0].category == "missing_validation"

    def test_evidence_related_file_does_not_match_substring(self):
        pack = ReviewPack(
            diff=PACK.diff,
            changed_files=[FileMeta(path="a.py", language="python")],
            artifact_fingerprint="artifact",
            pack_fingerprint="pack",
            evidence=[
                Evidence(
                    source="pytest",
                    status=EvidenceStatus.FAIL,
                    summary="data.py failed",
                    detail="data.py::test_case failed",
                )
            ],
        )
        raw = """\
## Section 1: Findings

**f-001**
- **Where**: `a.py`, line 2
- **What**: Missing validation in the new path.
- **Why**: The check was removed in the diff.
- **Severity estimate**: LOW
- **Category**: missing_validation
"""
        result = normalize_review_output(raw, pack)
        assert result.findings[0].evidence_related_file is False

    def test_pack_completeness_is_computed_inside_normalizer(self):
        result = normalize_review_output(RAW_OUTPUT, PACK)
        assert result.quality_metrics.pack_completeness > 0.0
