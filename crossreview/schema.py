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
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


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


# ---------------------------------------------------------------------------
# Fingerprint helpers
# ---------------------------------------------------------------------------

def compute_fingerprint(content: str) -> str:
    """SHA-256 hex digest of content — used for artifact_fingerprint and pack_fingerprint."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
