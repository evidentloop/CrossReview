# Changelog

## 0.1.0a1 — 2026-04-27

First public alpha release. Core thesis validated: context-isolated review via
`ReviewPack → fresh LLM session → ReviewResult` produces actionable findings
with measurable quality.

### Release Gate

9/9 blocking metrics pass (`blocking_pass: true`):

| Metric | Value | Gate |
|--------|-------|------|
| manual_recall | 0.929 | ≥ 0.80 |
| precision | 0.885 | ≥ 0.70 |
| invalid_findings_per_run | 0.158 | ≤ 2 |
| max_invalid_single_run | 1 | ≤ 5 |
| unclear_rate | 0.133 | ≤ 0.15 |
| context_fidelity | 1.000 | ≥ 0.80 |
| actionability | 1.000 | ≥ 0.90 |
| failure_rate | 0.000 | ≤ 0.10 |
| fixture_count | 33 | ≥ 20 |

Evaluated on 33 fixtures (30 external + 3 self-hosting), claude-opus-4.6.

### CLI

- `crossreview pack --diff REF` — assemble ReviewPack from git diff
- `crossreview verify --diff REF` — one-stop pack + review + output (default: human-readable)
- `crossreview verify --pack FILE` — verify from pre-built ReviewPack (default: JSON)
- `crossreview render-prompt --pack FILE` — emit reviewer prompt (for host-integrated mode)
- `crossreview ingest --raw-analysis FILE --pack FILE --model MODEL` — normalize host-side review output
- `--format {json,human}` on verify and ingest

### Architecture

- ReviewPack / ReviewResult / Finding schema (v0.1-alpha)
- BudgetGate: focus-priority + soft/hard token truncation
- ReviewerBackend protocol + Anthropic standalone implementation
- Deterministic normalizer (rule-based finding extraction)
- Deterministic adjudicator (rule-based advisory verdict)
- Human-readable formatter

### Supported

- `code_diff` artifact only
- Advisory verdict (`pass_candidate` / `concerns` / `needs_human_triage` / `inconclusive`)
- Single `fresh_llm` reviewer (Anthropic)
- Deterministic adjudicator and normalizer (no LLM fallback)

### Out of Scope (v0)

- Python SDK (internal APIs not stable)
- MCP Server / CI/CD Action
- Agent Skill runtime mode (advisory SKILL.md provided; runtime bridge deferred)
- Cross-model reviewer
- Verdict = block
- Evidence Collector (`--evidence-cmd`, planned for v0.5+)
