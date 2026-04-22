"""Deterministic extraction of Findings from reviewer raw analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .pack import compute_pack_completeness
from .schema import (
    Confidence,
    Finding,
    Locatability,
    QualityMetrics,
    ReviewPack,
    Severity,
    LocalizabilityDistribution,
)


DEFAULT_MAX_FINDINGS = 7
_SECTION_RE = re.compile(
    r"(?ms)^#+\s*Section 1:\s*Findings\s*(.*?)(?:^#+\s*Section 2:|^---\s*$|\Z)"
)
_BLOCK_START_RE = re.compile(r"(?m)^(?:\*\*(f-\d{3})\*\*|###\s+(f-\d{3}))\s*$")
_HEDGE_RE = re.compile(
    r"\b(might|maybe|perhaps|possibly|likely|appears|seems|if\b|could|may)\b",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")
_SEVERITY_PRIORITY = {
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.NOTE: 0,
}


@dataclass
class NormalizationResult:
    """Structured findings plus runtime diagnostic metrics."""

    raw_findings: list[Finding]
    findings: list[Finding]
    quality_metrics: QualityMetrics
    raw_findings_count: int
    emitted_findings_count: int
    noise_count: int


def _section_findings(text: str) -> str:
    match = _SECTION_RE.search(text)
    return match.group(1) if match else ""


def _split_finding_blocks(text: str) -> list[tuple[str, str]]:
    section = _section_findings(text)
    if not section:
        return []

    matches = list(_BLOCK_START_RE.finditer(section))
    blocks: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        finding_id = match.group(1) or match.group(2) or ""
        blocks.append((finding_id, section[start:end].strip()))
    return blocks


def _extract_field(block: str, label: str) -> str | None:
    pattern = re.compile(
        rf"(?ms)^- \*\*{re.escape(label)}\*\*: (.*?)(?=^- \*\*[^*]+\*\*:|\Z)"
    )
    match = pattern.search(block)
    if not match:
        return None
    return match.group(1).strip()


def _normalize_category(value: str | None) -> str:
    if not value:
        return "other"
    lowered = value.strip().lower()
    normalized = _NON_WORD_RE.sub("_", lowered).strip("_")
    return normalized or "other"


def _parse_where(where: str | None) -> tuple[str | None, int | None, str | None]:
    if not where:
        return None, None, None
    file_match = re.search(r"`([^`]+)`", where)
    line_match = re.search(r"line\s+(\d+)", where, flags=re.IGNORECASE)
    hunk_match = re.search(r"(@@.*?@@)", where)
    return (
        file_match.group(1) if file_match else None,
        int(line_match.group(1)) if line_match else None,
        hunk_match.group(1) if hunk_match else None,
    )


def _infer_confidence(summary: str, detail: str, category: str) -> Confidence:
    combined = f"{summary}\n{detail}"
    if _HEDGE_RE.search(combined):
        return Confidence.SPECULATIVE
    if len(summary.strip()) < 10 or len(summary.strip()) > 200:
        return Confidence.SPECULATIVE
    if category in {"suggestion", "style"}:
        return Confidence.SPECULATIVE
    return Confidence.PLAUSIBLE


def _infer_locatability(file: str | None, line: int | None, diff_hunk: str | None) -> Locatability:
    if file and (line is not None or diff_hunk is not None):
        return Locatability.EXACT
    if file:
        return Locatability.FILE_ONLY
    return Locatability.NONE


def _evidence_related_file(pack: ReviewPack, file: str | None) -> bool:
    if not file or not pack.evidence:
        return False
    # Match on exact filename or path segment to avoid substring false positives
    # (e.g., "a.py" should not match "data.py").
    basename = file.rsplit("/", 1)[-1]
    for evidence in pack.evidence:
        if evidence.status.value != "fail":
            continue
        haystacks = [evidence.summary or "", evidence.detail or ""]
        for haystack in haystacks:
            if file in haystack:
                # Verify it's a path-segment boundary, not a substring.
                idx = haystack.find(file)
                before_ok = idx == 0 or haystack[idx - 1] in " \t/\\:\"'"
                after_end = idx + len(file)
                after_ok = after_end >= len(haystack) or haystack[after_end] in " \t/\\:\"'.,;)"
                if before_ok and after_ok:
                    return True
            # Also try matching just the basename for resilience.
            if basename != file and basename in haystack:
                idx = haystack.find(basename)
                before_ok = idx == 0 or haystack[idx - 1] in " \t/\\:\"'"
                after_end = idx + len(basename)
                after_ok = after_end >= len(haystack) or haystack[after_end] in " \t/\\:\"'.,;)"
                if before_ok and after_ok:
                    return True
    return False


def _coerce_severity(value: str | None) -> Severity:
    if not value:
        return Severity.LOW
    normalized = value.strip().lower()
    if normalized == "high":
        return Severity.HIGH
    if normalized == "medium":
        return Severity.MEDIUM
    if normalized == "note":
        return Severity.NOTE
    return Severity.LOW


def _enforce_constraints(finding: Finding) -> Finding:
    if finding.confidence == Confidence.SPECULATIVE:
        finding.actionable = False

    if finding.confidence == Confidence.SPECULATIVE and finding.locatability == Locatability.NONE:
        finding.severity = Severity.NOTE
        return finding

    if finding.locatability == Locatability.NONE and finding.severity in {
        Severity.HIGH,
        Severity.MEDIUM,
    }:
        finding.severity = Severity.LOW

    if finding.confidence == Confidence.SPECULATIVE and finding.severity == Severity.HIGH:
        finding.severity = Severity.MEDIUM

    if finding.severity == Severity.HIGH and (
        finding.locatability != Locatability.EXACT
        or finding.confidence != Confidence.PLAUSIBLE
    ):
        finding.severity = Severity.MEDIUM

    return finding


def _sort_emitted_findings(findings: list[Finding]) -> list[Finding]:
    """Order emitted findings by severity, then evidence tie-breaker.

    raw_findings preserve reviewer order for eval/audit purposes. Only the
    emitted subset is reordered before noise-cap truncation.
    """
    return sorted(
        findings,
        key=lambda finding: (
            -_SEVERITY_PRIORITY[finding.severity],
            not finding.evidence_related_file,
        ),
    )


def normalize_review_output(
    raw_analysis: str,
    pack: ReviewPack,
    *,
    max_findings: int = DEFAULT_MAX_FINDINGS,
    pack_completeness: float | None = None,
) -> NormalizationResult:
    """Parse reviewer output into Findings plus quality metrics.

    ``pack_completeness`` may be provided by the caller; if omitted it is
    computed from the pack for standalone correctness.
    """
    if pack_completeness is None:
        pack_completeness = compute_pack_completeness(pack)

    parsed_findings: list[Finding] = []
    for finding_id, block in _split_finding_blocks(raw_analysis):
        summary = _extract_field(block, "What") or "Reviewer reported an issue."
        detail = _extract_field(block, "Why") or summary
        category = _normalize_category(_extract_field(block, "Category"))
        file, line, diff_hunk = _parse_where(_extract_field(block, "Where"))
        confidence = _infer_confidence(summary, detail, category)
        finding = Finding(
            id=finding_id,
            severity=_coerce_severity(_extract_field(block, "Severity estimate")),
            summary=summary,
            detail=detail,
            category=category,
            locatability=_infer_locatability(file, line, diff_hunk),
            confidence=confidence,
            evidence_related_file=_evidence_related_file(pack, file),
            actionable=(confidence == Confidence.PLAUSIBLE),
            file=file,
            line=line,
            diff_hunk=diff_hunk,
        )
        parsed_findings.append(_enforce_constraints(finding))

    raw_findings_count = len(parsed_findings)
    emitted_candidates = _sort_emitted_findings(list(parsed_findings))
    emitted_findings = emitted_candidates[:max_findings]
    truncated_count = max(raw_findings_count - len(emitted_findings), 0)

    exact = sum(1 for finding in emitted_findings if finding.locatability == Locatability.EXACT)
    file_only = sum(
        1 for finding in emitted_findings if finding.locatability == Locatability.FILE_ONLY
    )
    none = sum(1 for finding in emitted_findings if finding.locatability == Locatability.NONE)
    total = len(emitted_findings)

    speculative = sum(
        1 for finding in emitted_findings if finding.confidence == Confidence.SPECULATIVE
    )
    noisy_ids = {
        finding.id
        for finding in emitted_findings
        if (finding.severity == Severity.NOTE and not finding.actionable)
        or (
            finding.confidence == Confidence.SPECULATIVE
            and finding.locatability == Locatability.NONE
        )
    }
    noise_count = truncated_count + len(noisy_ids)

    # These runtime diagnostics intentionally describe the findings that the
    # product actually emits after noise-cap truncation, not the full raw set.
    quality_metrics = QualityMetrics(
        pack_completeness=pack_completeness,
        noise_count=noise_count,
        raw_findings_count=raw_findings_count,
        emitted_findings_count=len(emitted_findings),
        locatability_distribution=LocalizabilityDistribution(
            exact_pct=round(exact / total, 2) if total else 0.0,
            file_only_pct=round(file_only / total, 2) if total else 0.0,
            none_pct=round(none / total, 2) if total else 0.0,
        ),
        speculative_ratio=round(speculative / total, 2) if total else 0.0,
    )

    return NormalizationResult(
        raw_findings=parsed_findings,
        findings=emitted_findings,
        quality_metrics=quality_metrics,
        raw_findings_count=raw_findings_count,
        emitted_findings_count=len(emitted_findings),
        noise_count=noise_count,
    )
