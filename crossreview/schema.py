"""CrossReview v0-alpha schema definitions.

All types mirror v0-scope.md §7 exactly.
tasks.md is the task index; this file follows v0-scope.md as the field truth.

Design decisions:
  - Finding.category is str (not enum) — defer enum decision until normalizer
    runs across 10+ fixtures and a stable category set emerges.
  - ReviewResult builds the full v0-scope shell; nullable fields use None defaults
    so 1B components (reviewer, budget gate, adjudicator) plug in without schema changes.
  - Severity constraints (locatability × confidence matrix) are enforced via
    validate_finding_constraints() — not in the dataclass __post_init__ — so callers
    can construct Findings freely then validate before emission.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields as dc_fields
from enum import Enum
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArtifactType(str, Enum):
    """v0 only supports code_diff. Plan/design/custom are schema placeholders."""
    CODE_DIFF = "code_diff"


class ReviewStatus(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    REJECTED = "rejected"
    FAILED = "failed"


class IntentCoverage(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    UNKNOWN = "unknown"  # no intent provided


class Verdict(str, Enum):
    PASS_CANDIDATE = "pass_candidate"
    CONCERNS = "concerns"
    NEEDS_HUMAN_TRIAGE = "needs_human_triage"
    INCONCLUSIVE = "inconclusive"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOTE = "note"


class Locatability(str, Enum):
    EXACT = "exact"        # file + (line OR diff_hunk) within changed_files/diff
    FILE_ONLY = "file_only"  # file present, no line or diff_hunk
    NONE = "none"          # no file reference


class Confidence(str, Enum):
    PLAUSIBLE = "plausible"
    SPECULATIVE = "speculative"


class EvidenceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class BudgetStatus(str, Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    REJECTED = "rejected"


class ReviewerFailureReason(str, Enum):
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    MODEL_ERROR = "model_error"
    OUTPUT_MALFORMED = "output_malformed"
    CONTEXT_TOO_LARGE = "context_too_large"
    INPUT_INVALID = "input_invalid"
    RATE_LIMITED = "rate_limited"


# ---------------------------------------------------------------------------
# Sub-structures
# ---------------------------------------------------------------------------

@dataclass
class FileMeta:
    """Metadata for a changed file. v0-scope.md uses list[FileMeta] in ReviewPack."""
    path: str
    language: str | None = None


@dataclass
class ContextFile:
    """Extra context file provided by the host. v0-scope.md §7 ReviewPack."""
    path: str
    content: str
    role: str | None = None  # e.g. "plan", "design", "related_source"


@dataclass
class Evidence:
    """Deterministic evidence item. v0-scope.md §7 Evidence."""
    source: str              # "npm test", "eslint", "pytest", ...
    status: EvidenceStatus
    summary: str
    command: str | None = None
    detail: str | None = None


@dataclass
class PackBudget:
    """Budget limits for pack/review. v0-scope.md §7 ReviewPack.budget."""
    max_files: int | None = None
    max_chars_total: int | None = None
    timeout_sec: int | None = None


@dataclass
class ResultBudget:
    """Budget consumption in ReviewResult. v0-scope.md §7 ReviewResult.budget."""
    status: BudgetStatus
    files_reviewed: int
    files_total: int
    chars_consumed: int
    chars_limit: int | None = None


@dataclass
class AdvisoryVerdict:
    """Advisory verdict — v0 is advisory only, never blocks.
    v0-scope.md §7 ReviewResult.advisory_verdict."""
    verdict: Verdict
    rationale: str


@dataclass
class LocalizabilityDistribution:
    """Finding locatability distribution. v0-scope.md §7 ReviewResult.quality_metrics."""
    exact_pct: float
    file_only_pct: float
    none_pct: float


@dataclass
class QualityMetrics:
    """Runtime diagnostic metrics. Blocking release gates use eval-layer metrics,
    not these. v0-scope.md §7 ReviewResult.quality_metrics."""
    pack_completeness: float       # [0, 1] — runtime heuristic
    noise_count: int               # runtime heuristic noise count (excludes eval-layer unclear)
    raw_findings_count: int        # pre-noise_cap finding count
    emitted_findings_count: int    # post-noise_cap finding count
    locatability_distribution: LocalizabilityDistribution
    speculative_ratio: float       # speculative finding ratio


@dataclass
class ReviewerMeta:
    """Reviewer metadata. v0-scope.md §7 ReviewResult.reviewer."""
    type: Literal["fresh_llm"] = "fresh_llm"
    model: str = ""
    session_isolated: bool = True
    failure_reason: ReviewerFailureReason | None = None
    raw_analysis: str | None = None    # audit trail — reviewer's free-form analysis text
    latency_sec: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


# ---------------------------------------------------------------------------
# Core schemas
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "0.1-alpha"


@dataclass
class Finding:
    """A single review finding. v0-scope.md §7 Finding.

    category is str (not enum) — the set is not frozen yet.
    Constraint validation is done by validate_finding_constraints(), not here.
    """
    id: str                            # f-001, f-002, ...
    severity: Severity
    summary: str
    detail: str
    category: str                      # str, not enum — see module docstring
    locatability: Locatability
    confidence: Confidence
    evidence_related_file: bool = False
    actionable: bool = True
    file: str | None = None
    line: int | None = None
    diff_hunk: str | None = None
    requirement_ref: str | None = None


@dataclass
class ReviewPack:
    """Input pack for a review session. v0-scope.md §7 ReviewPack v0-alpha.

    Fields follow v0-scope.md:474 exactly.
    context_files and evidence are retained as optional fields with null/empty defaults;
    auto-selection logic is deferred, but the plumbing is ready for 1B.2 Evidence Collector.
    """
    schema_version: str = SCHEMA_VERSION
    artifact_type: ArtifactType = ArtifactType.CODE_DIFF

    # Core content — required for a valid pack
    diff: str = ""
    changed_files: list[FileMeta] = field(default_factory=list)

    # Fingerprints — computed or provided
    artifact_fingerprint: str = ""     # diff hash / commit ref
    pack_fingerprint: str = ""         # hash of pack content

    # Context (host-provided, all optional)
    intent: str | None = None
    task_file: str | None = None       # --task CLI flag → task_file
    focus: list[str] | None = None     # --focus CLI flag
    context_files: list[ContextFile] | None = None  # --context (repeatable) → context_files
    evidence: list[Evidence] | None = None

    # Budget
    budget: PackBudget = field(default_factory=PackBudget)


@dataclass
class ReviewResult:
    """Output of a complete review pipeline run. v0-scope.md §7 ReviewResult v0-alpha.

    Full shell built per v0-scope.md:503 — no custom "smaller subset".
    Nullable fields use None/defaults so 1B components plug in without schema changes.
    """
    schema_version: str = SCHEMA_VERSION
    artifact_fingerprint: str = ""
    pack_fingerprint: str = ""

    review_status: ReviewStatus = ReviewStatus.COMPLETE
    intent_coverage: IntentCoverage = IntentCoverage.UNKNOWN

    raw_findings: list[Finding] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    advisory_verdict: AdvisoryVerdict = field(
        default_factory=lambda: AdvisoryVerdict(
            verdict=Verdict.INCONCLUSIVE,
            rationale="not yet adjudicated",
        )
    )

    quality_metrics: QualityMetrics = field(
        default_factory=lambda: QualityMetrics(
            pack_completeness=0.0,
            noise_count=0,
            raw_findings_count=0,
            emitted_findings_count=0,
            locatability_distribution=LocalizabilityDistribution(0.0, 0.0, 0.0),
            speculative_ratio=0.0,
        )
    )

    reviewer: ReviewerMeta = field(default_factory=ReviewerMeta)
    budget: ResultBudget = field(
        default_factory=lambda: ResultBudget(
            status=BudgetStatus.COMPLETE,
            files_reviewed=0,
            files_total=0,
            chars_consumed=0,
        )
    )


# ---------------------------------------------------------------------------
# ReviewerConfig — adapter-layer config, not the core schema.
# Core receives a resolved config; it does not choose defaults.
# v0-scope.md §8 Model Resolution.
# ---------------------------------------------------------------------------

@dataclass
class ReviewerConfig:
    """Resolved reviewer configuration passed from adapter layer to core.

    Core does not pick defaults — that's the adapter's job (CLI or host).
    Fields: provider + model + api_key_env (points to env var name, never stores key directly).
    """
    provider: str              # "anthropic" | "openai" | ...
    model: str                 # e.g. "claude-sonnet-4-20250514"
    api_key_env: str           # env var name holding the API key, e.g. "ANTHROPIC_API_KEY"


# ---------------------------------------------------------------------------
# Constraint validation
# ---------------------------------------------------------------------------

# v0-scope.md §7 Finding Constraints — 5 rules
_FINDING_ID_RE = re.compile(r"^f-\d{3}$")
_CATEGORY_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


class ConstraintViolation(Exception):
    """Raised when a Finding violates v0 severity/locatability/confidence constraints."""


def validate_finding_constraints(f: Finding) -> list[str]:
    """Check a Finding against v0-scope.md §7 constraint rules.

    Returns a list of violated rule names (empty = all good).
    Does NOT raise — caller decides whether violations are fatal.
    """
    violations: list[str] = []

    # Rule 1: high severity requires exact locatability AND plausible confidence
    if f.severity == Severity.HIGH:
        if f.locatability != Locatability.EXACT or f.confidence != Confidence.PLAUSIBLE:
            violations.append("high_requires_exact_and_plausible")

    # Rule 2: speculative findings capped at medium
    if f.confidence == Confidence.SPECULATIVE and f.severity in (Severity.HIGH,):
        violations.append("speculative_severity_cap")

    # Rule 3: locatability=none capped at low
    if f.locatability == Locatability.NONE and f.severity in (Severity.HIGH, Severity.MEDIUM):
        violations.append("no_location_severity_cap")

    # Rule 4: speculative + none → must be note
    if (f.confidence == Confidence.SPECULATIVE
            and f.locatability == Locatability.NONE
            and f.severity != Severity.NOTE):
        violations.append("speculative_none_is_note")

    # Rule 5: speculative findings default not actionable
    if f.confidence == Confidence.SPECULATIVE and f.actionable:
        violations.append("speculative_not_actionable")

    return violations


def validate_finding_id(finding_id: str) -> bool:
    """Check that finding ID follows the f-NNN pattern."""
    return bool(_FINDING_ID_RE.match(finding_id))


def validate_category(category: str) -> bool:
    """Check that category is non-empty and follows snake_case naming convention."""
    return bool(_CATEGORY_RE.match(category))


# ---------------------------------------------------------------------------
# Pack / Result validation — "construct freely, validate before emission"
# Same pattern as validate_finding_constraints: returns violation list, doesn't raise.
# ---------------------------------------------------------------------------

def validate_review_pack(pack: ReviewPack) -> list[str]:
    """Check a ReviewPack against v0-scope.md §7 required-field rules.

    Returns a list of violated rule names (empty = valid).
    Checks required fields that must be non-empty for a pack to be usable.
    """
    violations: list[str] = []

    if not pack.diff:
        violations.append("diff_required")

    if not pack.changed_files:
        violations.append("changed_files_required")

    if pack.artifact_type != ArtifactType.CODE_DIFF:
        violations.append("artifact_type_must_be_code_diff")

    if not pack.schema_version:
        violations.append("schema_version_required")

    if not pack.artifact_fingerprint:
        violations.append("artifact_fingerprint_required")

    if not pack.pack_fingerprint:
        violations.append("pack_fingerprint_required")

    return violations


def validate_review_result(result: ReviewResult) -> list[str]:
    """Check a ReviewResult against v0-scope.md §7 required-field rules.

    Returns a list of violated rule names (empty = valid).
    Checks structural invariants; does NOT re-validate individual findings.
    """
    violations: list[str] = []

    if not result.schema_version:
        violations.append("schema_version_required")

    if not result.artifact_fingerprint:
        violations.append("artifact_fingerprint_required")

    if not result.pack_fingerprint:
        violations.append("pack_fingerprint_required")

    # reviewer.model must be set for a real result
    if not result.reviewer.model:
        violations.append("reviewer_model_required")

    return violations


def validate_eval_review_result_contract(data: dict[str, Any]) -> list[str]:
    """Check the eval-facing ReviewResult JSON contract.

    This is intentionally stricter than validate_review_result():
    - It validates the JSON shape expected by the offline eval harness.
    - It requires explicit runtime fields instead of allowing schema defaults.
    - It enforces raw/emitted finding count consistency for noise-cap analysis.
    """
    violations: list[str] = []

    review_status = data.get("review_status")
    if not isinstance(review_status, str) or not review_status:
        violations.append("review_status_required")

    advisory_verdict_data = data.get("advisory_verdict")
    if not isinstance(advisory_verdict_data, dict):
        violations.append("advisory_verdict_required")
    else:
        advisory_verdict = advisory_verdict_data.get("verdict")
        if not isinstance(advisory_verdict, str) or not advisory_verdict:
            violations.append("advisory_verdict_verdict_required")

    reviewer_data = data.get("reviewer")
    if not isinstance(reviewer_data, dict):
        violations.append("reviewer_required")
    else:
        reviewer_model = reviewer_data.get("model")
        if not isinstance(reviewer_model, str) or not reviewer_model:
            violations.append("reviewer_model_required")

    findings_data = data.get("findings")
    if not isinstance(findings_data, list):
        violations.append("findings_required")
        findings_data = None

    raw_findings_data = data.get("raw_findings")
    if not isinstance(raw_findings_data, list):
        violations.append("raw_findings_required")
        raw_findings_data = None

    quality_data = data.get("quality_metrics")
    if not isinstance(quality_data, dict):
        violations.append("quality_metrics_required")
        quality_data = None

    raw_count: int | None = None
    emitted_count: int | None = None
    if quality_data is not None:
        raw_count = quality_data.get("raw_findings_count")
        if not isinstance(raw_count, int) or raw_count < 0:
            violations.append("quality_metrics_raw_findings_count_required")
            raw_count = None

        emitted_count = quality_data.get("emitted_findings_count")
        if not isinstance(emitted_count, int) or emitted_count < 0:
            violations.append("quality_metrics_emitted_findings_count_required")
            emitted_count = None

        noise_count = quality_data.get("noise_count")
        if not isinstance(noise_count, int) or noise_count < 0:
            violations.append("quality_metrics_noise_count_required")

        speculative_ratio = quality_data.get("speculative_ratio")
        if (
            not isinstance(speculative_ratio, (int, float))
            or speculative_ratio < 0
            or speculative_ratio > 1
        ):
            violations.append("quality_metrics_speculative_ratio_required")

    if raw_findings_data is not None and raw_count is not None:
        if len(raw_findings_data) != raw_count:
            violations.append("raw_findings_count_mismatch")

    if findings_data is not None and emitted_count is not None:
        if len(findings_data) != emitted_count:
            violations.append("emitted_findings_count_mismatch")

    if raw_count is not None and emitted_count is not None and raw_count < emitted_count:
        violations.append("raw_findings_count_lt_emitted_findings_count")

    if raw_findings_data is not None and findings_data is not None:
        raw_ids = {
            item.get("id")
            for item in raw_findings_data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        emitted_ids = {
            item.get("id")
            for item in findings_data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if len(emitted_ids) != len(findings_data):
            violations.append("emitted_finding_ids_required")
        if len(raw_ids) != len(raw_findings_data):
            violations.append("raw_finding_ids_required")
        if not emitted_ids.issubset(raw_ids):
            violations.append("emitted_findings_not_subset_of_raw_findings")

    return violations


# ---------------------------------------------------------------------------
# Fingerprint helpers
# ---------------------------------------------------------------------------

def compute_fingerprint(content: str) -> str:
    """SHA-256 hex digest of content — used for artifact_fingerprint and pack_fingerprint."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses / enums to JSON-native types."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {
            f.name: to_serializable(getattr(obj, f.name))
            for f in dc_fields(obj)
        }
    if isinstance(obj, dict):
        return {
            key: to_serializable(value)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    return obj


def review_result_to_json(result: ReviewResult, *, indent: int = 2) -> str:
    """Serialize a ReviewResult to JSON."""
    return json.dumps(to_serializable(result), indent=indent, ensure_ascii=False)


def _findings_from_data(items: list[dict[str, Any]]) -> list[Finding]:
    REQUIRED_KEYS = ("id", "severity", "summary", "detail", "category", "locatability", "confidence")
    results: list[Finding] = []
    for idx, item in enumerate(items):
        missing = [k for k in REQUIRED_KEYS if k not in item]
        if missing:
            raise ValueError(f"finding[{idx}] missing required keys: {', '.join(missing)}")
        results.append(
            Finding(
                id=item["id"],
                severity=Severity(item["severity"]),
                summary=item["summary"],
                detail=item["detail"],
                category=item["category"],
                locatability=Locatability(item["locatability"]),
                confidence=Confidence(item["confidence"]),
                evidence_related_file=item.get("evidence_related_file", False),
                actionable=item.get("actionable", True),
                file=item.get("file"),
                line=item.get("line"),
                diff_hunk=item.get("diff_hunk"),
                requirement_ref=item.get("requirement_ref"),
            )
        )
    return results


def review_pack_from_dict(data: dict[str, Any]) -> ReviewPack:
    """Construct a ReviewPack from parsed JSON data."""
    artifact_type = ArtifactType(data.get("artifact_type", ArtifactType.CODE_DIFF.value))

    changed_files = [
        FileMeta(
            path=item["path"],
            language=item.get("language"),
        )
        for item in data.get("changed_files", [])
    ]

    context_files_data = data.get("context_files")
    context_files = None
    if context_files_data is not None:
        context_files = [
            ContextFile(
                path=item["path"],
                content=item["content"],
                role=item.get("role"),
            )
            for item in context_files_data
        ]

    evidence_data = data.get("evidence")
    evidence = None
    if evidence_data is not None:
        evidence = [
            Evidence(
                source=item["source"],
                status=EvidenceStatus(item["status"]),
                summary=item["summary"],
                command=item.get("command"),
                detail=item.get("detail"),
            )
            for item in evidence_data
        ]

    budget_data = data.get("budget") or {}
    budget = PackBudget(
        max_files=budget_data.get("max_files"),
        max_chars_total=budget_data.get("max_chars_total"),
        timeout_sec=budget_data.get("timeout_sec"),
    )

    return ReviewPack(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        artifact_type=artifact_type,
        diff=data.get("diff", ""),
        changed_files=changed_files,
        artifact_fingerprint=data.get("artifact_fingerprint", ""),
        pack_fingerprint=data.get("pack_fingerprint", ""),
        intent=data.get("intent"),
        task_file=data.get("task_file"),
        focus=data.get("focus"),
        context_files=context_files,
        evidence=evidence,
        budget=budget,
    )


def review_result_from_dict(data: dict[str, Any]) -> ReviewResult:
    """Construct a ReviewResult from parsed JSON data.

    Eval harness consumes saved runtime outputs through the same schema layer as
    the product pipeline. This keeps the aggregation logic from re-implementing
    runtime field semantics ad hoc.
    """
    findings = _findings_from_data(data.get("findings", []))
    raw_findings = _findings_from_data(data.get("raw_findings", []))

    evidence = [
        Evidence(
            source=item["source"],
            status=EvidenceStatus(item["status"]),
            summary=item["summary"],
            command=item.get("command"),
            detail=item.get("detail"),
        )
        for item in data.get("evidence", [])
    ]

    verdict_data = data.get("advisory_verdict") or {}
    advisory_verdict = AdvisoryVerdict(
        verdict=Verdict(verdict_data.get("verdict", Verdict.INCONCLUSIVE.value)),
        rationale=verdict_data.get("rationale", ""),
    )

    loc_data = (data.get("quality_metrics") or {}).get("locatability_distribution") or {}
    quality_data = data.get("quality_metrics") or {}
    quality_metrics = QualityMetrics(
        pack_completeness=quality_data.get("pack_completeness", 0.0),
        noise_count=quality_data.get("noise_count", 0),
        raw_findings_count=quality_data.get("raw_findings_count", 0),
        emitted_findings_count=quality_data.get("emitted_findings_count", 0),
        locatability_distribution=LocalizabilityDistribution(
            exact_pct=loc_data.get("exact_pct", 0.0),
            file_only_pct=loc_data.get("file_only_pct", 0.0),
            none_pct=loc_data.get("none_pct", 0.0),
        ),
        speculative_ratio=quality_data.get("speculative_ratio", 0.0),
    )

    reviewer_data = data.get("reviewer") or {}
    reviewer = ReviewerMeta(
        type=reviewer_data.get("type", "fresh_llm"),
        model=reviewer_data.get("model", ""),
        session_isolated=reviewer_data.get("session_isolated", True),
        failure_reason=(
            ReviewerFailureReason(reviewer_data["failure_reason"])
            if reviewer_data.get("failure_reason")
            else None
        ),
        raw_analysis=reviewer_data.get("raw_analysis"),
        latency_sec=reviewer_data.get("latency_sec"),
        input_tokens=reviewer_data.get("input_tokens"),
        output_tokens=reviewer_data.get("output_tokens"),
    )

    budget_data = data.get("budget") or {}
    budget = ResultBudget(
        status=BudgetStatus(budget_data.get("status", BudgetStatus.COMPLETE.value)),
        files_reviewed=budget_data.get("files_reviewed", 0),
        files_total=budget_data.get("files_total", 0),
        chars_consumed=budget_data.get("chars_consumed", 0),
        chars_limit=budget_data.get("chars_limit"),
    )

    return ReviewResult(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        artifact_fingerprint=data.get("artifact_fingerprint", ""),
        pack_fingerprint=data.get("pack_fingerprint", ""),
        review_status=ReviewStatus(data.get("review_status", ReviewStatus.COMPLETE.value)),
        intent_coverage=IntentCoverage(
            data.get("intent_coverage", IntentCoverage.UNKNOWN.value)
        ),
        raw_findings=raw_findings,
        findings=findings,
        evidence=evidence,
        advisory_verdict=advisory_verdict,
        quality_metrics=quality_metrics,
        reviewer=reviewer,
        budget=budget,
    )
