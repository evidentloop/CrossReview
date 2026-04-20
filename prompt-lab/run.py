#!/usr/bin/env python3
"""
Prompt Lab runner — minimal script for testing CrossReview reviewer prompt.

Usage:
    python run.py cases/001-auth-refresh              # Call LLM directly
    python run.py --render-only cases/001-auth-refresh # Render prompt to file for manual paste

Reads pack.json + prompt-template.md → calls LLM (or renders prompt) → saves output
"""

import json
import sys
import time
from pathlib import Path


def load_prompt_template() -> str:
    template_path = Path(__file__).parent / "prompt-template.md"
    return template_path.read_text(encoding="utf-8")


def load_pack(case_dir: Path) -> dict:
    pack_path = case_dir / "pack.json"
    if not pack_path.exists():
        print(f"Error: {pack_path} not found")
        sys.exit(1)
    return json.loads(pack_path.read_text(encoding="utf-8"))


def _normalize_list(val) -> list[str]:
    """Normalize a list that may contain strings or dicts (e.g. FileMeta)."""
    if not isinstance(val, list):
        return []
    return [item if isinstance(item, str) else str(item) for item in val]


def build_prompt(template: str, pack: dict) -> str:
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


def call_reviewer(prompt: str, model: str = None) -> dict:
    """
    Call LLM with the reviewer prompt. Returns dict with content, model, tokens, latency.

    Currently a placeholder — implement with your preferred LLM client.
    """
    # TODO: Implement with anthropic / openai client
    # Example with anthropic:
    #
    # import anthropic
    # client = anthropic.Anthropic()
    # start = time.time()
    # response = client.messages.create(
    #     model=model or "claude-sonnet-4-20250514",
    #     max_tokens=4096,
    #     system="You are an independent code reviewer.",
    #     messages=[{"role": "user", "content": prompt}],
    # )
    # latency = time.time() - start
    # return {
    #     "content": response.content[0].text,
    #     "model": response.model,
    #     "input_tokens": response.usage.input_tokens,
    #     "output_tokens": response.usage.output_tokens,
    #     "latency_sec": round(latency, 2),
    # }

    raise NotImplementedError(
        "Implement call_reviewer() with your LLM client. "
        "See TODO comments above for an anthropic example."
    )


def save_output(case_dir: Path, result: dict):
    output_path = case_dir / "raw-output.md"
    meta = (
        f"<!-- model: {result.get('model', 'unknown')} | "
        f"latency: {result.get('latency_sec', '?')}s | "
        f"input_tokens: {result.get('input_tokens', '?')} | "
        f"output_tokens: {result.get('output_tokens', '?')} -->\n\n"
    )
    output_path.write_text(meta + result["content"], encoding="utf-8")
    print(f"Saved: {output_path}")


def main():
    render_only = "--render-only" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--render-only"]

    if not args:
        print("Usage: python run.py [--render-only] <case_dir>")
        print("  --render-only  Render prompt to file, skip LLM call")
        print("Example: python run.py cases/001-auth-refresh")
        print("Example: python run.py --render-only cases/001-auth-refresh")
        sys.exit(1)

    case_dir = Path(args[0])
    if not case_dir.is_dir():
        print(f"Error: {case_dir} is not a directory")
        sys.exit(1)

    template = load_prompt_template()
    pack = load_pack(case_dir)
    prompt = build_prompt(template, pack)

    print(f"Case: {case_dir.name}")
    print(f"Diff size: {len(pack.get('diff', ''))} chars")
    print(f"Intent: {pack.get('intent', '(none)')}")

    if render_only:
        rendered_path = case_dir / "rendered-prompt.md"
        rendered_path.write_text(prompt, encoding="utf-8")
        print(f"Rendered prompt saved: {rendered_path}")
        print(f"Paste this into your LLM session, then save output to {case_dir / 'raw-output.md'}")
        return

    print("Calling reviewer...")

    result = call_reviewer(prompt)
    save_output(case_dir, result)

    print(f"Model: {result.get('model')}")
    print(f"Latency: {result.get('latency_sec')}s")
    print(f"Tokens: {result.get('input_tokens')} in / {result.get('output_tokens')} out")


if __name__ == "__main__":
    main()
