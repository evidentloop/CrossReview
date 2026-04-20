# CrossReview v0 Prompt Lab + Phase 1 — 任务清单

## Source-of-Truth

实现只认 [docs/v0-scope.md](../../../docs/v0-scope.md)（Status: Confirmed）+ 本文件。

---

## Phase 0.5 — Prompt Lab（当前）

> 目标：验证核心假设——fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding。
> 如果 prompt lab 结果很差，后续 schema / adjudicator / formatter 都是在包装失败。

- [ ] 0.5.1 准备 3-5 个真实 diff fixture
  - 来源：近期开发的真实 diff（非玩具示例）
  - 每个包含：diff + intent（可选）+ 手工 cross-review 的 expected findings
- [ ] 0.5.2 手写/半手写 ReviewPack
  - 不需要 CLI 工具，手工组装 diff + intent + focus + context
  - 保存为 JSON
- [ ] 0.5.3 固定 reviewer prompt 模板
  - 关键约束：intent/focus/task 是待验证背景声明，不是真相；raw diff 是优先证据
  - reviewer 先做自由分析，不强制输出 Finding JSON schema
- [ ] 0.5.4 运行 prompt → 保存 raw model output
  - 单脚本实现（prompt-lab/run.py），不搭框架
  - 记录：model, latency_sec, input_tokens, output_tokens
- [ ] 0.5.5 人工 adjudication + 记录
  - 回答三个问题：
    1. 模型是否能稳定给出真问题？
    2. 需要哪些 context 才能给出真问题？
    3. 主要噪音来自 prompt 还是 pack 缺失？

> **Gate**: 只有 prompt lab 证明 raw finding 质量可接受，才进入 Phase 1。

---

## Phase 1A — Schema & Config

- [ ] 1A.1 实现 ReviewPack schema（v0-scope.md §7）
  - artifact_type: "code_diff" only
  - 必填: artifact, changed_files
  - 可选: intent, focus, context_files, evidence
- [ ] 1A.2 实现 Finding schema（v0-scope.md §7）
  - 包含: locatability / confidence(plausible|speculative) / evidence_related_file / actionable
  - severity 约束规则（locatability × confidence 矩阵）
- [ ] 1A.3 实现 ReviewResult schema（v0-scope.md §7）
  - 包含: review_status, findings, advisory_verdict, quality_metrics
- [ ] 1A.4 实现配置结构
  - model resolution: --model > crossreview.yaml > ~/.crossreview/config.yaml > env > fail

## Phase 1B — Core Pipeline

- [ ] 1B.1 实现 Pack 阶段
  - `crossreview pack --diff HEAD~1 --intent "..." --focus auth --context ./plan.md`
- [ ] 1B.2 实现 Evidence Collector（deterministic_evidence）
  - 安全边界：只从 CLI --evidence-cmd 或 crossreview.yaml 读取命令
- [ ] 1B.3 实现 Budget Gate
  - 三状态: complete / truncated / rejected
- [ ] 1B.4 实现 fresh_llm_reviewer
  - 全新 session，无 producer 上下文
  - 输出自由分析文本（鼓励半结构化 markdown）
  - prompt 声明：intent/focus/task 是待验证背景声明
  - 保留 raw analysis 文本作为审计证据
  - 记录 latency_sec / input_tokens / output_tokens
- [ ] 1B.5 实现 FindingNormalizer
  - 从 reviewer raw analysis 提取结构化 Finding（regex/heuristic + LLM fallback）
  - LLM fallback 只做 extraction，不做新审查判断
- [ ] 1B.6 实现 Adjudicator（确定性，非 LLM）
  - verdict: pass_candidate / concerns / needs_human_triage / inconclusive
  - v0 只做 advisory
- [ ] 1B.7 实现 Output Formatter
  - 支持 --format json/human

## Phase 1C — CLI

- [ ] 1C.1 实现 `crossreview pack` 命令
- [ ] 1C.2 实现 `crossreview verify` 命令

## Phase 1D — Fixture & Validation

- [ ] 1D.1 实现 eval harness（dev-only）
- [ ] 1D.2 建立 fixture 格式（diff + context + manual baseline）
- [ ] 1D.3 收集 ≥ 20 个真实 fixture
- [ ] 1D.4 达成 v0 release gates（v0-scope.md §12）
  - manual_recall ≥ 0.80, precision ≥ 0.70
  - invalid_findings_per_run ≤ 2, unclear_rate ≤ 0.15
  - context_fidelity ≥ 0.80, actionability ≥ 0.90
  - failure_rate ≤ 0.10, fixture_count ≥ 20
