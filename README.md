# CrossReview

[![CI](https://github.com/evidentloop/cross-review/actions/workflows/ci.yml/badge.svg)](https://github.com/evidentloop/cross-review/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/crossreview)](https://pypi.org/project/crossreview/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://pypi.org/project/crossreview/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

English | [简体中文](README.zh-CN.md)

> Automated cross-review for AI coding — same model, clean session, independent second pass on your output.

## What is Cross-Review?

In human code review, a change is typically inspected by **someone who did not directly implement it**, which reduces author bias. CrossReview applies the same principle to AI-generated code by separating generation and review into two isolated contexts.

An AI coding assistant (Claude, Copilot, Cursor, etc.) first produces the change in its original session. CrossReview then packages the diff, stated intent, focus areas, and optional context into a `ReviewPack` and hands it to a **separate reviewer session** for verification. That reviewer does not inherit the original conversation, reasoning trace, or tool history; it evaluates the change only from the minimum necessary inputs.

The key insight: **you don't need a different model, just a different context.** Same model, clean session, real findings.

## Why It Works

The mechanism is not model diversity; it is **input isolation**.

The author session accumulates local assumptions, discarded alternatives, retries, and tool-side trial-and-error. If the review step reuses that context, the reviewer is likely to preserve the author's framing instead of independently re-deriving whether the change is correct.

CrossReview avoids that by constraining reviewer input to the review artifact itself:

| Reviewer receives | Reviewer does not receive |
|-------------------|---------------------------|
| Diff / changed files | Original conversation |
| Stated intent | Planning or reasoning trace |
| Focus areas | Tool call history |
| Optional context files | Retries, failed attempts, intermediate drafts |

This separation has two practical effects:

- It increases reviewer independence, because the second pass must justify findings from the artifact rather than from inherited session state.
- It improves auditability, because reviewer claims can be checked against `ReviewPack` contents, emitted findings, and deterministic normalization rules.

## Eval Results

Full evaluation across 33 fixtures (claude-opus-4.6, external_only scope):

| Metric | Value | Gate |
|--------|-------|------|
| Precision | 0.885 | ≥ 0.70 ✅ |
| Recall | 0.929 | ≥ 0.80 ✅ |
| Unclear rate | 0.133 | ≤ 0.150 ✅ |
| Invalid findings / run | 1 | ≤ 2 ✅ |

**All 9 release gate metrics pass** — `blocking_pass: true`. See [v0-scope.md §12](docs/v0-scope.md) for the full gate definition.

## Quick Start

```bash
pip install crossreview              # from PyPI (v0.1.0a3+)
pip install -e .                     # local dev (pack + verify commands)
pip install -e '.[anthropic]'        # + Anthropic standalone reviewer backend
pip install -e '.[dev]'              # dev dependencies (pytest + ruff)

# configure standalone verify via flags, crossreview.yaml, or env vars
# example:
#   export CROSSREVIEW_PROVIDER=anthropic
#   export CROSSREVIEW_MODEL=claude-sonnet-4-20250514
#   export CROSSREVIEW_API_KEY_ENV=ANTHROPIC_API_KEY
#   export ANTHROPIC_API_KEY=...

crossreview pack --diff HEAD~1 --intent "fix auth token refresh" > pack.json
crossreview pack --staged --intent "fix auth token refresh" > pack.json
crossreview verify --pack pack.json
```

Or in one step:

```bash
crossreview verify --diff HEAD~1 --intent "fix auth token refresh"
crossreview verify --staged --intent "fix auth token refresh"
```

`crossreview verify --diff`, `--staged`, and `--unstaged` output human-readable text by default. `crossreview verify --pack` outputs `ReviewResult` JSON (default), or human-readable text with `--format human`:

```jsonc
{
  "schema_version": "0.1-alpha",
  "artifact_fingerprint": "diff:abc123",
  "pack_fingerprint": "pack:def456",
  "review_status": "complete",
  "intent_coverage": "covered",
  "findings": [
    {
      "id": "f-001",
      "severity": "high",
      "summary": "Token refresh silently succeeds when refresh_token is expired",
      "detail": "The try/except on line 42 catches TokenExpiredError but returns the old token instead of raising.",
      "category": "logic_error",
      "locatability": "exact",
      "confidence": "plausible",
      "evidence_related_file": false,
      "actionable": true,
      "file": "src/auth.py",
      "line": 42
    }
  ],
  "advisory_verdict": {
    "verdict": "concerns",
    "rationale": "review found medium/high-severity issues"
  },
  "quality_metrics": {
    "pack_completeness": 0.85,
    "noise_count": 0,
    "raw_findings_count": 1,
    "emitted_findings_count": 1,
    "locatability_distribution": {
      "exact_pct": 1.0,
      "file_only_pct": 0.0,
      "none_pct": 0.0
    },
    "speculative_ratio": 0.0
  },
  "reviewer": {
    "type": "fresh_llm",
    "model": "claude-sonnet-4-20250514",
    "session_isolated": true,
    "failure_reason": null,
    "prompt_source": "product",
    "prompt_version": "v0.1"
  },
  "budget": {
    "status": "complete",
    "files_reviewed": 1,
    "files_total": 1,
    "chars_consumed": 842,
    "chars_limit": 12000
  }
}
```

## Architecture

```
         git diff + intent + focus + context
                      │
                      ▼
              ┌────────────────┐
              │      Pack      │  Assemble ReviewPack
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Budget Gate   │  Focus-priority, size cap
              └───────┬────────┘
                      │
   ╔══════════════════╪═══════════════════════════╗
   ║                  ▼  Isolation Boundary       ║
   ║          ┌────────────────┐                  ║
   ║          │ Reviewer (LLM) │  Fresh session,  ║
   ║          │                │  zero shared ctx ║
   ║          └───────┬────────┘                  ║
   ╚══════════════════╪═══════════════════════════╝
                      │
                      ▼
              ┌────────────────┐
              │  Normalizer    │  Extract findings from text
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Adjudicator   │  Apply rules → verdict
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │ ReviewResult   │  Findings + verdict
              │ (JSON)         │  + quality metrics
              └────────────────┘
```

Only the Reviewer calls an LLM. Everything else is rule-based — no AI in the loop.

Two reviewer backend modes:

| Mode | Description | Dependency |
|------|-------------|------------|
| **Host-integrated** *(CLI implemented)* | The host renders the reviewer prompt in an isolated context (fresh session / sub-agent), then feeds raw analysis back to CrossReview's normalizer + adjudicator through the `render-prompt + ingest` CLI commands | No extra SDK on the CrossReview side |
| **Standalone** *(implemented)* | CLI calls the LLM API directly | `crossreview[anthropic]` + reviewer config + API key |

Host-integrated is the planned default product path. The host does NOT need to implement a Python `ReviewerBackend`; the integration path is `render-prompt + ingest`, with the host responsible for executing the canonical prompt in a fresh context and feeding raw analysis back.

## Commands

### `crossreview pack`

```bash
crossreview pack --diff HEAD~1 > pack.json
crossreview pack --diff main..feat --intent "add caching" --focus cache --context ./plan.md > pack.json
```

| Flag | Description |
|------|-------------|
| `--diff REF` | Git ref (`HEAD~1`) or range (`main..feat`) |
| `--intent TEXT` | Task intent (background claim, not ground truth) |
| `--task FILE` | Full task description file |
| `--focus TERM` | Focus review area (repeatable) |
| `--context FILE` | Extra context file (repeatable) |

### `crossreview verify`

Two modes: `--pack` (verify a pre-built ReviewPack) or `--diff` (one-stop: pack + verify).

```bash
# one-stop: pack + verify, human output by default
crossreview verify --diff HEAD~1
crossreview verify --diff HEAD~1 --intent "fix auth" --focus auth

# verify a pre-built pack, JSON output by default
crossreview verify --pack pack.json
crossreview verify --pack pack.json --model claude-sonnet-4-20250514 --provider anthropic
```

`crossreview verify` requires reviewer configuration to resolve successfully:

- `--model / --provider / --api-key-env`
- or `crossreview.yaml`
- or `~/.crossreview/config.yaml`
- or `CROSSREVIEW_MODEL / CROSSREVIEW_PROVIDER / CROSSREVIEW_API_KEY_ENV`

| Flag | Description |
|------|-------------|
| `--diff REF` | Git ref for diff (e.g. `HEAD~1`, `main..feat`). Assembles ReviewPack inline. Mutually exclusive with `--pack` |
| `--pack FILE` | Path to ReviewPack JSON. Mutually exclusive with `--diff` |
| `--intent TEXT` | Task intent string (--diff mode) |
| `--task FILE` | Task description file (--diff mode) |
| `--focus TERM` | Focus area, repeatable (--diff mode) |
| `--context FILE` | Extra context file, repeatable (--diff mode) |
| `--format FORMAT` | Output format. Defaults to `human` with `--diff`, `json` with `--pack` |
| `--model TEXT` | Override reviewer model |
| `--provider TEXT` | Override provider (currently `anthropic` only) |
| `--api-key-env VAR` | Override API key env variable name |

### `crossreview render-prompt`

```bash
crossreview render-prompt --pack pack.json > prompt.md
crossreview render-prompt --pack pack.json --template custom-template.md > prompt.md
```

Renders a ReviewPack into the full canonical reviewer prompt for the host to execute in an isolated context. No LLM call, no API key needed.

| Flag | Description |
|------|-------------|
| `--pack FILE` | Path to ReviewPack JSON |
| `--template FILE` | Custom prompt template (default: built-in product/v0.1) |

### `crossreview ingest`

```bash
crossreview ingest --raw-analysis raw.md --pack pack.json --model claude-sonnet-4-20250514
crossreview ingest --raw-analysis - --pack pack.json --model host_unknown --prompt-source product --prompt-version v0.1
```

Takes raw analysis text from a host-integrated review session and produces a standard ReviewResult via normalizer + adjudicator. No LLM call, no API key needed. Outputs JSON by default; use `--format human` for terminal-friendly output.

| Flag | Description |
|------|-------------|
| `--raw-analysis FILE` | Raw analysis file path; `-` for stdin |
| `--pack FILE` | Original ReviewPack JSON |
| `--model TEXT` | Host model name (`host_unknown` if unknown) |
| `--format FORMAT` | Output format: `json` (default) or `human` |
| `--prompt-source TEXT` | Prompt source identifier (optional) |
| `--prompt-version TEXT` | Prompt version identifier (optional) |
| `--latency-sec FLOAT` | Host-measured LLM latency (optional) |
| `--input-tokens INT` | Host-reported input token count (optional) |
| `--output-tokens INT` | Host-reported output token count (optional) |

### Exit Codes

All commands return **0** when a `ReviewResult` is successfully produced, regardless of `review_status` or `advisory_verdict`. A non-zero exit code means the command failed to produce output (invalid input, missing API key, empty diff, etc.).

For automation, check `review_status` and `advisory_verdict` in the JSON output instead of relying on the exit code:

```bash
crossreview verify --diff HEAD~1 --format json | jq -e '.advisory_verdict.verdict == "pass_candidate"'
```

## Status

| Component | Status | Notes |
|-----------|--------|-------|
| Schema | ✅ Done | ReviewPack / Finding / ReviewResult / Config |
| Pack CLI | ✅ Done | `crossreview pack` |
| Budget Gate | ✅ Done | Focus priority + soft/hard truncation |
| Reviewer | ✅ Done | ReviewerBackend protocol + Anthropic standalone |
| Normalizer | ✅ Done | Rule-based finding extraction |
| Adjudicator | ✅ Done | Rule-based advisory verdict |
| Verify CLI | ✅ Done | `crossreview verify --pack` |
| Render Prompt CLI | ✅ Done | `crossreview render-prompt --pack` (host-integrated front half) |
| Ingest CLI | ✅ Done | `crossreview ingest --raw-analysis --pack --model` (host-integrated back half) |
| Evidence Collector | 🔜 Next | ReviewPack.evidence path exists, empty evidence works |
| Eval Harness | ✅ Done | 33 fixtures, 9/9 gate metrics pass, `blocking_pass: true` |
| Human-readable Output | ✅ Done | `--format human` on verify/ingest |
| One-stop Verify | ✅ Done | `crossreview verify --diff` (pack + review in one step, default `--format human`) |

## v0 Scope

**Supported**: `code_diff` artifact only · advisory verdict · single `fresh_llm` reviewer · deterministic adjudicator and normalizer (no LLM fallback)

**Out of scope (v0)**: Python SDK · MCP Server · CI/CD Action · Agent Skill runtime mode (advisory SKILL.md provided; runtime bridge deferred) · cross-model reviewer · verdict = block

**Release gate**: v0 must pass [9 blocking metrics](docs/v0-scope.md) (§12), including manual_recall ≥ 0.80, precision ≥ 0.70, fixture_count ≥ 20, invalid_findings_per_run ≤ 2, and 5 others. All 9 currently pass (`blocking_pass: true`).

## License

MIT
