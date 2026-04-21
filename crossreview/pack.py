"""Pack assembly: git diff → ReviewPack.

Implements 1B.1 (pack assembly) and supports 1C.1 (pack CLI).
Core responsibility: construct a valid ReviewPack from git diff + optional context.

Design decisions:
  - ``--diff REF`` → ``git diff REF HEAD`` (committed changes; no unstaged).
  - ``--diff A..B`` → passed directly to git (explicit range).
  - changed_files via ``git diff --name-only -z`` (NUL-delimited, handles special-char paths).
    Regex fallback available for standalone diff text via ``extract_changed_files()``.
  - Language detected from file extension (simple mapping).
  - Fingerprints: artifact_fp = sha256(diff), pack_fp = sha256(pack-sans-fp).
  - pack_completeness computed per v0-scope.md §10.2 (returned, not stored on pack).
  - validate_review_pack() called before emission; violations → ValueError.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import fields as dc_fields
from enum import Enum
from pathlib import Path
from typing import Any

from .schema import (
    ArtifactType,
    ContextFile,
    Evidence,
    FileMeta,
    PackBudget,
    ReviewPack,
    compute_fingerprint,
    validate_review_pack,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".php": "php",
    ".pl": "perl",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".scala": "scala",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
}


def detect_language(path: str) -> str | None:
    """Detect programming language from file extension."""
    suffix = Path(path).suffix
    return _LANG_MAP.get(suffix) or _LANG_MAP.get(suffix.lower())


# ---------------------------------------------------------------------------
# Git diff
# ---------------------------------------------------------------------------

class GitDiffError(Exception):
    """Raised when git diff fails."""


def diff_from_git(ref: str, repo_root: Path | None = None) -> str:
    """Run ``git diff REF HEAD`` and return the unified diff string.

    If *ref* contains ``..``, it is passed directly as a range
    (e.g. ``abc..def``). Otherwise ``HEAD`` is appended as the target.

    Raises :class:`GitDiffError` on non-zero git exit.
    """
    cmd = ["git", "--no-pager", "diff"]
    if ".." in ref:
        cmd.append(ref)
    else:
        cmd.extend([ref, "HEAD"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise GitDiffError(
            f"git diff failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc

    return result.stdout


# ---------------------------------------------------------------------------
# Changed-file extraction
# ---------------------------------------------------------------------------

def changed_files_from_git(ref: str, repo_root: Path | None = None) -> list[FileMeta]:
    """Get changed file list via ``git diff --name-only -z``.

    Uses NUL-delimited output (``-z``) to correctly handle paths with
    special characters (spaces, tabs, quotes). Preferred over regex parsing.

    Raises :class:`GitDiffError` on non-zero git exit.
    """
    cmd = ["git", "--no-pager", "diff", "--name-only", "-z"]
    if ".." in ref:
        cmd.append(ref)
    else:
        cmd.extend([ref, "HEAD"])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise GitDiffError(
            f"git diff --name-only failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc

    # -z output: NUL-separated paths, trailing NUL
    paths = [p for p in result.stdout.split("\0") if p]
    seen: dict[str, FileMeta] = {}
    for p in paths:
        if p not in seen:
            seen[p] = FileMeta(path=p, language=detect_language(p))
    return list(seen.values())


# Regex fallback for extract_changed_files (used when only diff text is available,
# e.g. piped input). Known limitation: fails on quoted paths and paths containing " b/".
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$", re.MULTILINE)


def extract_changed_files(diff: str) -> list[FileMeta]:
    """Parse a unified diff to extract the list of changed files.

    This is a **regex fallback** — prefer :func:`changed_files_from_git` when
    a git repo is available. Known limitations:

    - Paths with special characters (tabs, quotes) are quoted by git and
      won't match the regex.
    - Paths containing the literal substring `` b/`` will be mis-split.

    Handles normal changes, additions, deletions, and renames.
    Deduplicates by path.
    """
    seen: dict[str, FileMeta] = {}
    for m in _DIFF_HEADER_RE.finditer(diff):
        old_path, new_path = m.group(1), m.group(2)
        # Deletions: +++ /dev/null → use old path
        path = new_path if new_path != "/dev/null" else old_path
        if path not in seen:
            seen[path] = FileMeta(path=path, language=detect_language(path))
    return list(seen.values())


# ---------------------------------------------------------------------------
# Pack completeness — v0-scope.md §10.2
# ---------------------------------------------------------------------------

def compute_pack_completeness(pack: ReviewPack) -> float:
    """Calculate pack completeness score per v0-scope.md §10.2.

    Returns a float in [0, 1]. Breakdown::

        diff non-empty          → +0.30
        changed_files populated → +0.10
        intent or task_file     → +0.25
        focus                   → +0.10
        context_files           → +0.15
        evidence                → +0.10
        ────────────────────────────────
        max                       1.00
    """
    score = 0.0
    if pack.diff:
        score += 0.30
    if pack.changed_files:
        score += 0.10
    if pack.intent or pack.task_file:
        score += 0.25
    if pack.focus:
        score += 0.10
    if pack.context_files:
        score += 0.15
    if pack.evidence:
        score += 0.10
    return round(score, 2)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def read_task_file(path: str) -> str:
    """Read a task-description file from disk."""
    return Path(path).read_text(encoding="utf-8")


def read_context_files(paths: list[str]) -> list[ContextFile]:
    """Read context files from disk into ContextFile objects."""
    result: list[ContextFile] = []
    for p in paths:
        content = Path(p).read_text(encoding="utf-8")
        result.append(ContextFile(path=p, content=content))
    return result


# ---------------------------------------------------------------------------
# Serialization — ReviewPack → dict / JSON
# ---------------------------------------------------------------------------

def _to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses / enums to JSON-native types."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {
            f.name: _to_serializable(getattr(obj, f.name))
            for f in dc_fields(obj)
        }
    if isinstance(obj, list):
        return [_to_serializable(item) for item in obj]
    return obj


def pack_to_dict(pack: ReviewPack) -> dict:
    """Convert a ReviewPack to a JSON-serializable dict."""
    return _to_serializable(pack)


def pack_to_json(pack: ReviewPack, *, indent: int = 2, exclude_pack_fp: bool = False) -> str:
    """Serialize a ReviewPack to a JSON string.

    If *exclude_pack_fp* is True, ``pack_fingerprint`` is set to ``""`` in
    the output — used when computing the fingerprint itself.
    """
    d = pack_to_dict(pack)
    if exclude_pack_fp:
        d["pack_fingerprint"] = ""
    return json.dumps(d, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_pack(
    diff: str,
    *,
    changed_files: list[FileMeta] | None = None,
    intent: str | None = None,
    task_file: str | None = None,
    focus: list[str] | None = None,
    context_files: list[ContextFile] | None = None,
    evidence: list[Evidence] | None = None,
    budget: PackBudget | None = None,
) -> ReviewPack:
    """Construct a validated ReviewPack from components.

    * If *changed_files* is ``None``, they are extracted from *diff*.
    * Fingerprints are computed automatically.
    * ``validate_review_pack()`` is called; violations raise ``ValueError``.
    """
    if changed_files is None:
        changed_files = extract_changed_files(diff)

    artifact_fp = compute_fingerprint(diff)

    pack = ReviewPack(
        schema_version=SCHEMA_VERSION,
        artifact_type=ArtifactType.CODE_DIFF,
        diff=diff,
        changed_files=changed_files,
        artifact_fingerprint=artifact_fp,
        intent=intent,
        task_file=task_file,
        focus=focus,
        context_files=context_files,
        evidence=evidence,
        budget=budget or PackBudget(),
    )

    # pack_fingerprint = hash of pack content with pack_fp excluded
    pack.pack_fingerprint = compute_fingerprint(
        pack_to_json(pack, exclude_pack_fp=True)
    )

    violations = validate_review_pack(pack)
    if violations:
        raise ValueError(f"Invalid ReviewPack: {', '.join(violations)}")

    return pack
