#!/usr/bin/env python3
"""
Prompt Lab runner — minimal script for testing CrossReview reviewer prompt.

Usage:
    python run.py --render-only cases/001-auth-refresh # Render prompt to file for manual paste

Reads pack.json + prompt-template.md → renders prompt for manual paste → saves output
"""

import json
import sys
import time
from pathlib import Path

# Shared core — single renderer for Prompt Lab and crossreview verify
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crossreview.core.prompt import load_reviewer_template, render_reviewer_prompt


def load_pack(case_dir: Path) -> dict:
    pack_path = case_dir / "pack.json"
    if not pack_path.exists():
        print(f"Error: {pack_path} not found")
        sys.exit(1)
    pack = json.loads(pack_path.read_text(encoding="utf-8"))

    if pack.get("artifact_type") != "code_diff":
        print(f"Error: artifact_type must be 'code_diff', got '{pack.get('artifact_type')}'")
        sys.exit(1)
    if not pack.get("diff", "").strip():
        print("Error: pack.json 'diff' is empty")
        sys.exit(1)
    if not pack.get("changed_files"):
        print("Error: pack.json 'changed_files' is empty")
        sys.exit(1)

    return pack


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

    if not args or not render_only:
        print("Usage: python run.py --render-only <case_dir>")
        print("  --render-only  Render prompt to file for manual paste")
        print("Example: python run.py --render-only cases/001-auth-refresh")
        sys.exit(1)

    case_dir = Path(args[0])
    if not case_dir.is_dir():
        print(f"Error: {case_dir} is not a directory")
        sys.exit(1)

    template = load_reviewer_template()
    pack = load_pack(case_dir)
    prompt = render_reviewer_prompt(template, pack)

    print(f"Case: {case_dir.name}")
    print(f"Diff size: {len(pack.get('diff', ''))} chars")
    print(f"Intent: {pack.get('intent', '(none)')}")

    if render_only:
        rendered_path = case_dir / "rendered-prompt.md"
        rendered_path.write_text(prompt, encoding="utf-8")
        print(f"Rendered prompt saved: {rendered_path}")
        print(f"Paste this into your LLM session, then save output to {case_dir / 'raw-output.md'}")
        return

    print("Error: Prompt Lab currently supports render-only mode only.")
    print(f"Paste the rendered prompt into your LLM session, then save output to {case_dir / 'raw-output.md'}")
    sys.exit(1)


if __name__ == "__main__":
    main()
