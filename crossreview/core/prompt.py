"""Shared reviewer prompt renderer.

Used by both Prompt Lab (dev/eval) and crossreview verify (product).
Renderer is deterministic assembly only — no prompt strategy or finding schema logic.
"""

import json
from pathlib import Path

# Canonical template location — single source of truth for both entry points.
_DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "prompt-lab" / "prompt-template.md"


def load_reviewer_template(template_path: Path | None = None) -> str:
    """Load the reviewer prompt template from disk.

    Args:
        template_path: Override path. Defaults to prompt-lab/prompt-template.md.

    Returns:
        Template string with {intent}, {focus}, {diff}, {changed_files}, {evidence} placeholders.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    path = template_path or _DEFAULT_TEMPLATE_PATH
    return path.read_text(encoding="utf-8")


def _normalize_list(val) -> list[str]:
    """Normalize a list that may contain strings or dicts (e.g. FileMeta)."""
    if not isinstance(val, list):
        return []
    return [item if isinstance(item, str) else str(item) for item in val]


def render_reviewer_prompt(template: str, pack: dict) -> str:
    """Render a reviewer prompt by substituting pack fields into template placeholders.

    This function performs deterministic assembly only:
    - Normalize pack fields (lists may contain strings or dicts)
    - Substitute {intent}, {focus}, {diff}, {changed_files}, {evidence}

    It does NOT interpret finding schema, observation rules, or prompt strategy.

    Args:
        template: Template string with placeholders.
        pack: ReviewPack dict with intent, focus, diff, changed_files, evidence fields.

    Returns:
        Fully rendered prompt string ready to send to a reviewer model.
    """
    focus = _normalize_list(pack.get("focus", []))
    changed_files = _normalize_list(pack.get("changed_files", []))
    return (
        template
        .replace("{intent}", pack.get("intent", "(no intent provided)"))
        .replace("{focus}", ", ".join(focus) or "(no focus specified)")
        .replace("{diff}", pack.get("diff", ""))
        .replace("{changed_files}", ", ".join(changed_files))
        .replace("{evidence}", json.dumps(pack.get("evidence", []), indent=2))
    )
