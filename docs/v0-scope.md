# CrossReview v0 Scope: Context-Isolated Verification Harness

> **Status**: Confirmed — v0 范围已锁定，可进入 prompt lab → Phase 1 实现
> **前置文档**: background.md, design.md, cross-project-insights.md, product-form-analysis.md
> **定位**: 本文档取代 product-form-analysis.md 中的宽泛 MVP 定义，定义 v0 的精确范围
> **Source-of-truth**: v0 执行只认本文档 + tasks.md。其余方案包文档（product-form-analysis.md, hermes-insights.md, cross-project-insights.md）降级为背景参考，不参与 Phase 1 执行判断。

---

## §1 Core Thesis

### 待验证假设

> Given a **code diff** and its task intent,
> an automated ReviewPack + single-round fresh-session review can reproduce
> manual cross-review quality with acceptable loss —
> measured by the blocking release gates defined in §12.
>
> v0 scope: code_diff only. Plan/design/custom artifact 是 schema 预留，v0 不实现不验收。

### 关键洞察

- **价值来源是 context isolation，不是 model diversity。** 同一模型新开 session 就能发现问题，因为它没有生产过程的锚定和路径依赖。
- 跨模型是增强手段（v1+），不是核心价值。
- CrossReview 不发明"交叉审查"——它把一个**已验证有效的手工模式**协议化和自动化。
- **Context isolation 不是银弹。** fresh session 消除了生产 session 的上下文污染，但 ReviewPack 本身可能携带 producer bias——intent、focus、task 描述都来自 producer，如果描述有误导，reviewer 仍会被锚定。因此 reviewer prompt 必须明确：intent/focus/task 是待验证背景声明，不是真相；raw diff 是优先证据。否则只是把 bias 从 session 迁移到了 pack。

### Artifact 边界

CrossReview 的长期对象不是只有 code diff，而是**任意可审查 artifact**：例如 code diff、analysis、plan、design、review-result、final audit note 等。只要一个 artifact 可以被独立 session 消费并产出验证结论，它就属于 CrossReview 的概念边界。

但为保证 v0 可验证、可收敛，当前范围**明确收窄到 `code_diff`**：

- v0 的 ReviewPack schema、Prompt Lab、release gate、CLI examples 只按 `code_diff` 设计和验收
- analysis / plan / design / review-result 的交叉验证，属于真实 workflow 使用场景，或未来 artifact type 扩展
- 这类非 diff artifact 的结果可以单独记录为 workflow 模式收益，但**不计入**当前 Prompt Lab / v0 release gate 的 single-pass 指标

### 产品主张

```
Independent verification through context isolation, not model diversity.
```

---

## §2 Problem & Value Proposition

### 当前手工流程

```
1. 在宿主 agent（如 Sopify）中完成代码/方案
2. 手动开一个新 session（如 Claude 5.4x-high）
3. 手动挑选 context：diff、intent、plan、关键文件
4. 描述背景，标记重点区域
5. 让新 session 审查
6. 人工判断哪些 finding 有效
7. 回到原 session 修改
```

**手工流程的问题：**
- 每次 ~5 分钟的 copy-paste 操作
- context 选择依赖个人判断，不可复现
- 无结构化输出，finding 散落在对话中
- 无 fingerprint，无法追踪"哪个 diff 被审查过"
- 无质量度量，不知道 review 质量是否在提升

### CrossReview 解决的问题

> 把高质量手工 fresh-session cross-review 流程，变成可重复、可检查、可度量的 ReviewPack 管道。

**核心价值：**
1. **上下文打包（ReviewPack）** — 自动组装 diff + intent + focus + evidence，替代手工 copy-paste
2. **协议标准化** — ReviewPack / ReviewResult 是稳定契约，任何 agent 可发出、任何 reviewer 可消费
3. **可重复性** — 同一输入 → 可比较的输出 → 随时间可追踪
4. **可检查性** — `pack` 命令让你看见自动打包的结果，判断是否和手工一致

---

## §3 Product Boundaries

### CrossReview 负责的（纯能力层）

| 能力 | 说明 |
|------|------|
| 把 code diff 打包成 ReviewPack | v0 只支持 code_diff；plan/design 是 schema 预留 |
| 在隔离环境中执行 review | 无共享 context 的独立审查 |
| 输出结构化 Finding | 带 file:line / diff hunk / requirement ref |
| 提供 pack / verify CLI，以及内部 Python core | v0 不承诺 public stable SDK |
| 输出 advisory verdict | 建议性判定，不做强制决策 |
| 追踪 artifact fingerprint | diff hash / commit ref |

### CrossReview 不负责的（宿主决策）

| 决策 | 归属 |
|------|------|
| 在什么阶段触发 review | 宿主 |
| 选哪个模型执行 review | CLI adapter（用户配置）/ 宿主 adapter |
| verdict 后的 policy action（continue / block / require human） | 宿主 |
| workflow 编排 | 宿主 |
| 追问 reviewer 以细化 finding | v0 不做，v1+ 考虑 |
| 基于反馈自动调优 | v0 不做 |

---

## §4 Evaluation Protocol

### 评估理念

v0 的评估不是学术实验，而是**与手工流程的 parity 测试**：

> 自动化结果 vs 你手工做的结果，覆盖率和精度差多少？

### 评估基准

以手工 fresh-session cross-review 作为 gold-ish baseline。**不做 generic prompt baseline 对照**（你已经知道 cross-review 有效，不需要再证明它比"不 review"好）。

### 单次评审与交叉验证的边界

v0 评估中需要区分两个对象：

1. **单次评审（single-pass review）**
   给 reviewer 一个 ReviewPack，让它在独立 fresh session 中输出第一轮 raw findings。Prompt Lab 与 release gate 中的 precision / manual_recall / invalid_findings_per_run，默认都按这个口径计算。

2. **交叉验证（cross-validated review workflow）**
   reviewer 先输出 findings，再由另一个独立 session / agent 对 findings 做实现核查、剔除幻觉、补充遗漏，并可把验证结果回喂给原 reviewer 再复核。这评估的是 workflow 级质量，不等同于 reviewer prompt 的 first-pass 质量。

规则：

- Prompt Lab 默认只统计 **单次评审** 的原始输出。
- 第二模型批判、人工验证、回喂复核，不计入 Prompt Lab 的 reviewer 原始能力指标。
- 如果需要验证 cross-review workflow 的整体收益，应单独记录为 workflow 模式结果，不与 single-pass 指标混算。
- 如果 review target 不是 `code_diff`（例如 analysis / plan / review-result），同样按 workflow 模式单独记录；它属于 CrossReview 的使用场景，但不属于 v0 Prompt Lab / release gate 的评测对象。

### 指标定义

| 指标 | 定义 | v0 目标 |
|------|------|---------|
| `manual_recall` | 自动化 finding 覆盖手工 cross-review 有效 finding 的比例 | ≥ 80% |
| `precision` | valid / (valid + invalid)，unclear 不计入分母 | ≥ 70% |
| `invalid_findings_per_run` | 每次运行中 judgment == invalid 的 finding 数量 | ≤ 2 条/run |
| `unclear_rate` | 每次运行中 judgment == unclear 的 finding 占比 | ≤ 15% |
| `triage_time` | 含人工筛选的端到端时间（baseline ~5min） | ≤ 2min |
| `context_fidelity` | manual baseline 中 required context items 被 pack 包含的比例 | ≥ 80% |
| `actionability` | 有效 finding 中可直接指导修改的比例 | ≥ 90% |
| `failure_rate` | 超 budget / 模型失败 / 输出 malformed 的比例 | ≤ 10% |

### 指标计算规则

- **有效问题** = 人工 adjudication 后标记为 `valid` 的 finding
- **dedupe**: 语义重复的 finding 合并后计算，避免啰嗦模型虚增命中率
- **无 intent 的 case**: 不计入 spec mismatch 能力，`intent_coverage` 标记为 `unknown`
- **unclear finding**: 不算 valid，不算 invalid；eval 层计入 unclear_rate（不进入 runtime noise_count）
- **precision 公式**: `valid / (valid + invalid)`，unclear 不计入分母（由 unclear_rate 单独约束）
- **新发现 finding**: auto finding 判定 valid 但 `matched_manual_id == null`，计入 precision 分子，不计入 recall 分子
- **无 manual finding 的 fixture**: 不参与 manual_recall 计算，但参与 precision / invalid_findings_per_run / failure_rate

### Fixture 集合

- 至少 20 个 diff fixture，目标 50 个
- 每个 fixture 包含：diff + intent（可选） + 人工 expected issue notes
- 来源：真实开发产出的 diff；Prompt Lab 第一批固定使用真实 commit，不使用纯合成 case
- 每个 fixture 运行后进行人工 adjudication

**分阶段达标路径**（不降低 release gate，分里程碑验证）：

| 阶段 | Fixture 数量 | 目的 |
|------|-------------|------|
| Prompt Lab | 3-5 个 | 验证 reviewer prompt 质量，确认核心假设成立 |
| Dev Milestone | 10 个 | 跑通 eval harness，验证管道端到端 |
| Release Gate | ≥ 20 个 | 正式 v0 发布门槛 |

### Manual Baseline 落盘格式

manual_recall 和 precision 的计算依赖两个不同的落盘结构：

```yaml
# 结构 1: manual_findings — recall 的 denominator
# 手工 cross-review 发现的问题列表（gold-ish baseline）
manual_findings:
  fixture_id: string
  source: manual_fresh_session
  reviewer_model: string             # 手工 review 使用的模型
  reviewed_at: ISO 8601 timestamp
  context_items:                     # 手工粘贴的 context（用于 context_fidelity 计算）
    - type: diff | file | intent | test_output | plan
      path_or_desc: string
      required: bool                 # 是否为必需 context
      covered_by_pack: bool | null   # eval 时人工标记；null = 未评估
  findings:
    - id: string                     # mf-001, mf-002, ...
      summary: string
      file: string | null
      severity_estimate: high | medium | low

# 结构 2: auto_adjudications — precision 的分子
# 对自动 finding 的人工判定（每次 eval run 产出）
auto_adjudications:
  fixture_id: string
  run_id: string                     # 对应的 eval run
  adjudicated_at: ISO 8601 timestamp
  findings:
    - auto_finding_id: string        # 自动产出的 finding id (f-001, ...)
      judgment: valid | invalid | unclear
      matched_manual_id: string | null  # 匹配的 manual finding id（用于 recall 计算）
      actionability_judgment: actionable | not_actionable | unclear  # 人工判定是否可直接指导修改
```

**指标计算依据：**
- `manual_recall` = 被至少一个 valid auto_finding matched 的 manual_findings / 总 manual_findings（无 manual_finding 的 fixture 不参与 recall）
- `precision` = valid / (valid + invalid)，unclear 不计入分母
- `invalid_findings_per_run` = total_invalid_findings / successful_eval_runs（均值口径）；另加保护：max_invalid_single_run ≤ 5
- `unclear_rate` = total_unclear_findings / total_auto_findings（均值口径）
- `actionability` = actionability_judgment == actionable 的 valid findings / 总 valid findings（基于人工 adjudication，不用 runtime Finding.actionable）
- `failure_rate` = failed_eval_runs / total_eval_runs；failure 定义 = review_status ∈ {rejected, failed} 或 output malformed 或 model error/timeout（truncated 不算 failure，truncated 有自己的 verdict cap）
- `context_fidelity` = manual_findings.context_items 中 required == true 且 covered_by_pack == true 的 / required 且 covered_by_pack is not null 的 context_items（covered_by_pack == null 视为未评估，不计入分子也不计入分母）
- `context_fidelity` v0 匹配规则：**人工标记 covered_by_pack: true/false**，不做自动匹配

> **设计理由**：如果 baseline 不落盘，manual_recall ≥ 0.80 和 precision ≥ 0.70 会变成主观感觉。
> 两个结构分开存，避免回忆偏差和计算混淆。

### Release Gate

```yaml
必须全部满足才允许发布 v0 (详见 §12):
  - manual_recall >= 0.80
  - precision >= 0.70 (valid / (valid + invalid))
  - invalid_findings_per_run <= 2 (均值; max single run <= 5)
  - unclear_rate <= 0.15
  - context_fidelity >= 0.80 (人工标记)
  - actionability >= 0.90 (基于人工 adjudication)
  - failure_rate <= 0.10 (truncated ≠ failure)
  - fixture_count >= 20

不满足时:
  - 退回为 prompt pattern / agent skill
  - 不做独立产品化
```

---

## §5 Implementation Scope

### 包含（v0-alpha）

```yaml
CLI (v0 public):
  - crossreview pack    # 打包 artifact → ReviewPack JSON
  - crossreview verify  # pack + review + output（一站式）

Core (Python, 内部实现，不承诺稳定 SDK):
  - ReviewPack / ReviewResult v0-alpha schema
  - fresh_llm_reviewer (context-isolated LLM review)
  - deterministic_evidence (lint/test 结果 → ReviewPack evidence)
  - deterministic adjudicator
  - artifact_fingerprint (diff hash / commit ref)
  - pack_budget (complete / truncated / rejected)
  - ReviewerFailureReason 枚举

输出:
  - JSON (机器消费)
  - human-readable (终端消费)

Dev-only tools (不是 v0 public CLI):
  - python -m crossreview_eval    # fixture 评估（release gate 验证用）
  - fixture runner
  - human adjudication 标记工具
```

### 不包含（明确 v0 不做）

```yaml
产品通道:
  ❌ MCP Server
  ❌ Agent Skill
  ❌ CI/CD GitHub Action
  ❌ SARIF 输出

Reviewer 类型:
  ❌ cross_model_reviewer (v1+)
  ❌ skill_guided_reviewer (v2+)

高级功能:
  ❌ public stable SDK (v1)
  ❌ profiles/ 目录
  ❌ policy expression 语言
  ❌ review.md plan 资产
  ❌ Sopify adapter（内部 dogfood，不公开）
  ❌ graphify 集成
  ❌ design review / plan review / final audit (宿主决定 artifact 类型)
  ❌ 自动追问 reviewer
  ❌ 基于反馈的自动调优
  ❌ verdict = block (v0 只做 advisory)
```

---

## §6 CLI Interface Design

### `crossreview pack` — 打包 artifact 为 ReviewPack

```bash
# 基本用法
crossreview pack --diff HEAD~1 > pack.json

# 带 intent
crossreview pack --diff HEAD~1 --intent "修复 token refresh 过期判断" > pack.json

# 带 intent 文件
crossreview pack --diff HEAD~1 --task ./task.md > pack.json

# 带 focus 区域
crossreview pack --diff HEAD~1 --intent "修复 auth 逻辑" --focus auth > pack.json

# 带额外 context
crossreview pack --diff HEAD~1 --intent "实现缓存层" --context ./plan.md > pack.json

# 带 deterministic evidence（lint/test 输出）
crossreview pack --diff HEAD~1 --evidence-cmd "npm test" --evidence-cmd "npm run lint" > pack.json
```

**pack 是 v0 一等能力，不是调试手段。** 它让用户可以检查自动打包的内容是否和手工 copy-paste 一致。

### `crossreview verify` — 一站式 pack + review + output

```bash
# 最简用法
crossreview verify --diff HEAD~1

# 带 intent
crossreview verify --diff HEAD~1 --intent "修复 token refresh 过期判断"

# 带 task 文件
crossreview verify --diff HEAD~1 --task ./task.md

# 带 focus + context
crossreview verify --diff HEAD~1 --intent "修复 auth" --focus auth --context ./plan.md

# 从已有 pack 验证
crossreview verify --pack pack.json

# 指定输出格式
crossreview verify --diff HEAD~1 --format json
crossreview verify --diff HEAD~1 --format human  # 默认

# 带 evidence
crossreview verify --diff HEAD~1 --evidence-cmd "npm test" --intent "修复登录流程"
```

### 输出示例（human-readable）

```
CrossReview v0-alpha | artifact: a3f2b1c | review_status: complete

Intent: 修复 token refresh 过期判断
Intent Coverage: covered
Pack Completeness: 0.85

Findings (3):
  [HIGH]  src/auth/refresh.ts:42 — Token expiry off-by-one
          exact | plausible | actionable | evidence: related_file
          Diff hunk: @@ -40,3 +40,3 @@

  [MED]   src/auth/refresh.ts:67 — Missing network timeout handling
          exact | plausible | actionable
          Diff hunk: @@ -65,5 +65,8 @@

  [LOW]   src/auth/types.ts:15 — No unit documentation for refreshInterval
          file_only | plausible | actionable
          Diff hunk: @@ -14,2 +14,3 @@

Evidence:
  npm test: 47 passed, 0 failed
  npm run lint: 2 warnings (unrelated)

Diagnostics:
  Speculative: 0% | Noise: 0

Advisory Verdict: concerns
  Rationale: 1 high-severity off-by-one in core auth logic

Fingerprint: diff:a3f2b1c | pack:e7d4a2f | reviewer:fresh_llm_v0
```

### 输出示例（JSON）

```json
{
  "schema_version": "0.1-alpha",
  "artifact_fingerprint": "a3f2b1c",
  "pack_fingerprint": "e7d4a2f",
  "review_status": "complete",
  "intent_coverage": "covered",
  "raw_findings": [
    {
      "id": "f-001",
      "severity": "high",
      "file": "src/auth/refresh.ts",
      "line": 42,
      "diff_hunk": "@@ -40,3 +40,3 @@",
      "summary": "Token expiry comparison uses `<` instead of `<=`",
      "detail": "Off-by-one causes premature refresh failure",
      "category": "logic_error",
      "locatability": "exact",
      "confidence": "plausible",
      "evidence_related_file": true,
      "actionable": true
    }
  ],
  "findings": [
    {
      "id": "f-001",
      "severity": "high",
      "file": "src/auth/refresh.ts",
      "line": 42,
      "diff_hunk": "@@ -40,3 +40,3 @@",
      "summary": "Token expiry comparison uses `<` instead of `<=`",
      "detail": "Off-by-one causes premature refresh failure",
      "category": "logic_error",
      "locatability": "exact",
      "confidence": "plausible",
      "evidence_related_file": true,
      "actionable": true
    }
  ],
  "evidence": [
    {
      "source": "npm test",
      "status": "pass",
      "summary": "47 passed, 0 failed"
    }
  ],
  "quality_metrics": {
    "pack_completeness": 0.85,
    "noise_count": 0,
    "raw_findings_count": 1,
    "emitted_findings_count": 1,
    "speculative_ratio": 0.00,
    "locatability_distribution": {
      "exact_pct": 1.00,
      "file_only_pct": 0.00,
      "none_pct": 0.00
    }
  },
  "advisory_verdict": {
    "verdict": "concerns",
    "rationale": "1 high-severity off-by-one in core auth logic"
  },
  "reviewer": {
    "type": "fresh_llm",
    "model": "claude-sonnet-4-20250514",
    "session_isolated": true,
    "failure_reason": null
  },
  "budget": {
    "status": "complete",
    "files_reviewed": 3,
    "files_total": 3,
    "chars_consumed": 8420,
    "chars_limit": 12000
  }
}
```

---

## §7 Schema Design (v0-alpha)

> `schema_version: "0.1-alpha"` — 在 20-50 个 fixture 验证后再升 `1.0`。
> 冻结最小 envelope（顶层字段名和类型），不冻结全部内部字段。
>
> **eval contract 字段**（v0 eval harness 依赖，视为 v0-alpha 内稳定）：
>
> *ReviewResult 侧*（eval 从运行产出读取）：
> `Finding.locatability`, `Finding.confidence`, `Finding.evidence_related_file`,
> `ReviewResult.review_status`, `ReviewResult.advisory_verdict.verdict`, `ReviewResult.raw_findings`,
> `quality_metrics.raw_findings_count`, `quality_metrics.emitted_findings_count`,
> `quality_metrics.noise_count`, `quality_metrics.speculative_ratio`。
>
> *Fixture 侧*（eval 从人工标注读取）：
> `auto_adjudications.findings[].judgment`, `auto_adjudications.findings[].actionability_judgment`,
> `auto_adjudications.findings[].matched_manual_id`,
> `manual_findings.context_items[].covered_by_pack`。
>
> `Finding.actionable` 为运行时展示/诊断字段，adjudicator 内部使用但 eval harness 不依赖它计算任何 release gate。
> 其余内部字段为展示/诊断用途，可在 v0-alpha 内调整。

### ReviewPack v0-alpha

```yaml
ReviewPack:
  schema_version: "0.1-alpha"
  artifact_fingerprint: string      # diff hash / commit ref
  pack_fingerprint: string          # pack 内容的 hash
  artifact_type: "code_diff"            # v0 only; "plan" | "design" | "custom" 是 schema 预留
  
  # 核心内容
  diff: string                      # unified diff
  changed_files: list[FileMeta]     # 变更文件列表
  
  # 上下文（宿主提供，全部可选）
  intent: string | null             # 任务意图
  task_file: string | null          # 完整 task 描述文件内容
  focus: list[string] | null        # 重点审查区域
  context_files: list[ContextFile] | null  # 额外 context
  
  # 证据（deterministic_evidence 收集）
  evidence: list[Evidence] | null
  
  # 预算
  budget:
    max_files: int | null
    max_chars_total: int | null
    timeout_sec: int | null
```

### ReviewResult v0-alpha

```yaml
ReviewResult:
  schema_version: "0.1-alpha"
  artifact_fingerprint: string
  pack_fingerprint: string
  
  # 审查状态
  review_status: "complete" | "truncated" | "rejected" | "failed"
  intent_coverage: "covered" | "partial" | "unknown"  # unknown = 无 intent 输入
  
  # 原始 finding（noise_cap 截断前，eval 使用这一层）
  raw_findings: list[Finding]

  # 发现
  findings: list[Finding]          # emitted findings（noise_cap 截断后，产品输出使用）
  
  # 证据（透传 + reviewer 可补充）
  evidence: list[Evidence]
  
  # 建议性判定（不做 block）
  advisory_verdict:
    verdict: "pass_candidate" | "concerns" | "needs_human_triage" | "inconclusive"
    rationale: string
  
  # v0 最小质量度量（blocking release gates 只看外部评估指标，这些是 diagnostic）
  quality_metrics:
    pack_completeness: float       # pack 完整度 [0, 1]（runtime 启发式，非 manual baseline 对比）
    noise_count: int               # runtime 启发式噪音计数（不含 eval 层 unclear）
    raw_findings_count: int        # noise_cap 截断前的原始 finding 数
    emitted_findings_count: int    # noise_cap 截断后的输出 finding 数
    locatability_distribution:     # finding 定位精度分布
      exact_pct: float
      file_only_pct: float
      none_pct: float
    speculative_ratio: float       # speculative finding 占比
  
  # Reviewer 元信息
  reviewer:
    type: "fresh_llm"
    model: string
    session_isolated: bool
    failure_reason: ReviewerFailureReason | null
    raw_analysis: string | null     # reviewer 原始自由分析文本（审计证据）
    latency_sec: float | null       # 模型调用耗时（秒）
    input_tokens: int | null        # LLM 输入 token 数
    output_tokens: int | null       # LLM 输出 token 数
  
  # 预算消耗
  budget:
    status: "complete" | "truncated" | "rejected"
    files_reviewed: int
    files_total: int
    chars_consumed: int
    chars_limit: int | null
```

### Finding

```yaml
Finding:
  id: string                        # f-001, f-002, ...
  severity: "high" | "medium" | "low" | "note"
  file: string | null               # 文件路径
  line: int | null                  # 行号
  diff_hunk: string | null          # diff hunk 引用
  requirement_ref: string | null    # 需求引用（如 intent 中的关键点）
  summary: string                   # 一句话描述
  detail: string                    # 详细说明
  category: string                  # logic_error, missing_test, spec_mismatch, security, performance, ...
  
  # 质量字段（v0 最小集）
  locatability: "exact" | "file_only" | "none"
  confidence: "plausible" | "speculative"
  evidence_related_file: bool         # evidence failure 在同一文件，但不升级 confidence
  actionable: bool                    # 是否可直接指导修改
```

#### locatability vs confidence 分离原则

> 关键设计决策：**locatability ≠ confidence**。
>
> LLM 很容易编造精确的 `file:42`，但推理完全是错的。
> "定位精确" 只说明 finding 指向了哪里，不说明 finding 说的对不对。

| 字段 | 度量的东西 | 确定方式 |
|------|-----------|---------|
| `locatability` | finding 指向了哪里 | 解析 LLM 输出的结构化字段（file/line/diff_hunk 是否存在） |
| `confidence` | finding 说的对不对 | hedging 检测 / category 分析 / intent 关联（v0 只有 plausible/speculative） |
| `evidence_related_file` | evidence failure 是否在同一文件 | file-level exact match（不升级 confidence，只做 diagnostic 标记） |

**合法组合示例：**
- `exact` + `plausible` + `evidence_related_file: true` — 精确定位 + evidence 在同文件，最可信（v0 最强信号）
- `exact` + `speculative` — 精确指向了位置但推理可能是错的（LLM 编造了合理看起来的分析）
- `none` + `plausible` — 没有精确定位但观点合理
- `none` + `speculative` — 最不可信，降级为 note

#### locatability 判定

```yaml
exact:    file + (line OR diff_hunk) 且指向 changed_files/diff 范围内
file_only: file 存在，line 和 diff_hunk 均缺失
none:     file 不存在
```

#### confidence 判定（v0 只有 plausible / speculative）

> **注意**：这是 deterministic heuristic（基于文本特征的机械判定），不代表统计意义上的真置信度。
> v0 接受这个精度限制；v1 可引入更丰富的 evidence-based 信号。

```yaml
plausible:
  # finding 论述合理，无 speculative 信号
  - 有明确的技术分析（不含假设性词汇）
  - 或 category 属于可验证类型（logic_error, missing_test, security）
  - 且非模糊表述

speculative:
  # 以下任一条件命中即为 speculative
  - finding 包含假设性词汇（"可能", "如果", "perhaps", "might", "似乎"）
  - finding 表述过于宽泛（summary 长度 < 10 chars 或 > 200 chars）
  - category == "suggestion" 或 "style"
  - finding 与 intent 完全无关联（当 intent 存在时）
```

#### evidence_related_file 判定

```yaml
evidence_related_file:
  - evidence.status == "fail" 且 evidence 错误文件 == finding.file → true
  - evidence.status == "fail" 且 evidence 无文件信息 → false
  - evidence.status == "pass" → false（pass 不关联具体 finding）
  - 默认: false

重要: evidence_related_file 是 diagnostic 标记，不升级 confidence。
  - file-level match 可能是巧合（同文件不同问题）
  - v1 可引入 line/hunk/error-text match → 恢复 corroborated confidence 等级
```

### Finding 约束（v0）

```yaml
constraints:
  # high severity 必须同时满足 locatability 和 confidence 条件
  - rule: "high_requires_exact_and_plausible"
    description: "high severity 要求 locatability == exact 且 confidence == plausible"
  
  # speculative finding 的 severity 上限
  - rule: "speculative_severity_cap"
    description: "confidence == speculative 的 finding 最高只能 medium"
  
  # none locatability 的 severity 上限
  - rule: "no_location_severity_cap"
    description: "locatability == none 的 finding 最高只能 low"
  
  # speculative + none 降级为 note
  - rule: "speculative_none_is_note"
    description: "confidence == speculative 且 locatability == none → 降级为 note"
  
  # speculative finding 默认不可行动
  - rule: "speculative_not_actionable"
    description: "speculative finding 默认 actionable=false，除非有明确修复建议"
  
  # 每次默认最多 7 条 finding（可配置）
  - rule: "noise_cap"
    default_max_findings: 7
    description: "CLI 输出截断；超出的按 severity 排序截断（同 severity 时 evidence_related_file=true 优先）"
    eval_note: "eval 必须使用顶层 raw_findings（截断前），不受 noise_cap 影响；ReviewResult 同时记录 raw_findings_count 和 emitted_findings_count"
```

### ReviewerFailureReason

```yaml
ReviewerFailureReason:
  - "timeout"              # 超时
  - "budget_exceeded"      # 输入超预算
  - "model_error"          # 模型 API 错误
  - "output_malformed"     # 输出解析失败
  - "context_too_large"    # context 超限
  - "input_invalid"        # ReviewPack 格式无效
  - "rate_limited"         # API 限流
```

### Evidence

```yaml
Evidence:
  source: string           # "npm test", "eslint", "pytest", ...
  command: string | null   # 实际执行的命令
  status: "pass" | "fail" | "error" | "skipped"
  summary: string          # 一句话结果
  detail: string | null    # 完整输出（可选）
```

### Budget 三态语义

```yaml
complete:
  - 全部文件已审查
  - verdict 无限制

truncated:
  - 部分文件已审查（超 budget 的文件跳过）
  - advisory_verdict 最高只能到 "concerns"，不能给强 "pass_candidate"
  - review_status 标记为 "truncated"

rejected:
  - 输入太大或结构无效，无法开始审查
  - advisory_verdict 固定为 "inconclusive"
  - review_status 标记为 "rejected"
```

---

## §8 Architecture Overview

### 管道流程

```
宿主调用
    ↓
crossreview pack (或 verify 内部调用)
    ↓
┌─────────────────────┐
│  Evidence Collector  │  ← deterministic_evidence (lint/test)
│  → 丰富 ReviewPack   │
└─────────────────────┘
    ↓
┌─────────────────────┐
│   Budget Gate        │  ← 检查 pack 大小 vs budget
│   → complete/truncated/rejected │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  fresh_llm_reviewer  │  ← context-isolated session
│  → raw analysis text │     reviewer 先自由分析，不强制 JSON schema
└─────────────────────┘
    ↓
┌─────────────────────┐
│  Finding Normalizer  │  ← 从 raw analysis 提取结构化 finding
│  → list[Finding]     │     deterministic parser（regex/heuristic）
└─────────────────────┘
    ↓
┌─────────────────────┐
│  Adjudicator         │  ← deterministic rules + evidence 交叉
│  → advisory_verdict  │
└─────────────────────┘
    ↓
┌─────────────────────┐
│  Output Formatter    │  ← JSON / human-readable
│  → ReviewResult      │
└─────────────────────┘
    ↓
宿主消费 ReviewResult
```

### 关键设计原则

1. **Evidence collector ≠ Reviewer** — lint/test 结果是证据，不是审查意见。它们丰富 ReviewPack，不产出 Finding。
2. **Reviewer 只有一种（v0）** — `fresh_llm_reviewer`，在隔离 session 中执行。输出为自由分析文本（鼓励半结构化 markdown），不强制输出 Finding JSON schema。
3. **两段式审查** — reviewer 先做自由分析（raw analysis），Finding Normalizer 再以 deterministic parser 从中提取结构化 Finding。对外仍输出结构化 JSON，但不强迫模型一开始只吐严格 schema。原始分析文本保留为审计证据。
4. **Adjudicator 是确定性的** — 基于 evidence status + finding severity + budget status 的规则引擎，不涉及 LLM。
5. **Advisory only** — v0 的 verdict 只是建议，不做 block。
6. **code_diff only (v0)** — v0 只接受 code_diff artifact。Plan/design/custom 是 schema 预留，v0 不实现不验收。
7. **Core 不选择模型** — core 接收 resolved `ReviewerConfig`，不内置默认供应商或模型。
8. **Pack bias 意识** — reviewer prompt 必须将 intent/focus/task 视为"待验证的背景声明"，raw diff 为优先证据。
9. **Normalizer 保持确定性（v0）** — v0 只实现 regex/heuristic parser，不引入 LLM fallback；若 raw output 无法稳定解析，应视为 reviewer/prompt 质量信号，而不是用第二次 LLM 调用兜底。

### Model Resolution

core 不关心模型从哪来。模型解析是 adapter 层的职责。

```yaml
core:
  input: ReviewerConfig (provider, model, api_key)
  responsibility: 执行 review
  不做: 选择默认模型、猜测供应商、内置 API key

cli_adapter:
  resolution_order:
    1. --model / --provider flag     # 显式覆盖
    2. ./crossreview.yaml            # 项目级配置
    3. ~/.crossreview/config.yaml    # 用户级配置（设一次永远生效）
    4. CROSSREVIEW_MODEL env         # 环境变量
    5. fail: MODEL_NOT_CONFIGURED    # 首次使用前需要初始化

  reviewer_config 格式:
    provider: anthropic              # anthropic | openai | ...
    model: claude-sonnet-4-20250514
    api_key_env: ANTHROPIC_API_KEY   # 指向环境变量名，不直接存 key

host_adapter (如 Sopify):
  默认传宿主当前在用的模型 → same-model fresh session
  语义: context isolation 是价值来源，不需要换模型
  用户没有显式指定跨模型 → 自动传当前模型
```

> **设计理由**：CrossReview 的核心假设是 context isolation 提供价值，不是 model diversity。
> 默认行为是"用和你一样的模型，但开全新 session"——和手工 cross-review 完全一致。

---

## §9 Deterministic Evidence

### 定位

deterministic_evidence 不是 reviewer，而是 **evidence collector**。它运行用户显式配置的命令（lint / test / type-check），将结果注入 ReviewPack.evidence。

### 执行规则

```yaml
- 只运行用户通过 --evidence-cmd 显式指定的命令，或 crossreview.yaml 受信配置中的命令
- 不自动发现或推断 lint/test 命令
- 不从 ReviewPack JSON 文件中读取或执行 evidence 命令（防止外部 pack 诱导执行任意命令）
- 每个命令有独立 timeout（默认 30s）
- 命令失败不阻止 review，只标记 evidence.status = "fail" 或 "error"
- evidence 进入 ReviewPack 后，reviewer 和 adjudicator 都可以消费
```

### Adjudicator 使用 Evidence 的规则（v0）

```yaml
基础规则:
  - evidence 全部 pass + findings 为空 → pass_candidate
  - evidence 有 fail + findings 非空 → concerns
  - evidence 有 fail + findings 为空 → needs_human_triage
  - evidence 有 error/skipped → verdict 最高 concerns + 输出中附加强 warning
  - 无 evidence → 不影响 verdict（用户未配置 --evidence-cmd）

质量门控规则（与 §10.5 同步）:
  - review_status == "truncated" → verdict 最高 concerns
  - speculative_ratio > 50% → verdict 最高 concerns
  - 所有 high severity findings 都是 speculative → needs_human_triage
  - pass_candidate 要求 pack_completeness >= 0.7
```

---


## §10 Quality Metrics Framework

> 设计参考：Graphify 三级置信度模型 + HelloAgents 多维验证体系 + Hermes MoA 聚合质量控制。
> 核心原则：**locatability ≠ confidence；置信度由结构化信号确定，不由 LLM 自评。**

### 10.1 v0 最小质量字段

v0 只实现三个核心字段 + 四个 diagnostic 字段。不做五层质量平台。

**Finding 级（核心，进入约束规则）：**
- `locatability`: exact / file_only / none
- `confidence`: plausible / speculative
- `evidence_related_file`: bool
- `actionable`: bool

**ReviewResult 级（diagnostic，不进 release gate）：**
- `pack_completeness`: float [0, 1]
- `noise_count`: int
- `raw_findings_count`: int（noise_cap 截断前）
- `emitted_findings_count`: int（noise_cap 截断后）
- `speculative_ratio`: float（speculative finding 占比）
- `locatability_distribution`: exact/file_only/none 占比

### 10.2 Pack Completeness（runtime diagnostic，参考 Graphify corpus health gate）

> **pack_completeness ≠ context_fidelity**：
> - `pack_completeness` 是 runtime diagnostic（运行时启发式加权分），不和 manual baseline 比较
> - `context_fidelity` 是 eval parity metric（与 manual baseline 的 required context items 覆盖率对比）
> - 两者不可互替

Graphify 根据语料库大小判定是否需要图谱分析（太小不需要，太大成本警告）。
CrossReview 用类似思路在运行时评估 pack 结构完整度：

```yaml
pack_completeness 计算:

基础分:
  - diff 存在且非空 → +0.30
  - changed_files 列表完整 → +0.10

上下文分:
  - intent 或 task_file 存在 → +0.25
  - focus 存在 → +0.10
  - context_files 存在 → +0.15
  - evidence 存在 → +0.10

总分范围 [0, 1]

用途:
  - pack_completeness >= 0.7 → pass_candidate verdict 可信
  - pack_completeness < 0.4 → 输出中附加建议
  - v0 不阻止低 completeness 的 review，只做提示
```

### 10.3 Noise Count

```yaml
noise_count = 被 noise_cap 截断的 finding 数
            + emitted findings 中 severity == "note" 且 actionable == false 的 finding 数
            + emitted findings 中 speculative 且 locatability == none 的 finding 数

用途:
  - noise_count > 2 → 在输出中标记
  - 进入 diagnostic_metrics
```

### 10.4 Evidence File Correlation（参考 Graphify EXTRACTED 理念）

Graphify 的关键设计：`EXTRACTED`（AST 解析的）= 高置信度，因为有确定性来源。
CrossReview v0 的 `evidence_related_file` 仅做文件级标记，不升级 confidence：

```yaml
v0 evidence_related_file 规则 (仅文件级 match):
  - evidence.status == "fail" 且 evidence 错误文件 == finding.file → evidence_related_file: true
  - evidence.status == "fail" 且 evidence 无文件信息 → evidence_related_file: false
  - evidence.status == "pass" → evidence_related_file: false（pass 不关联具体 finding）

重要: file-level match 不升级 confidence（可能是同文件不同问题）

v1 演进:
  - 引入 evidence 输出解析器（Jest/pytest/tsc error format parsing）
  - 支持 line/hunk/error-text match → 恢复 corroborated confidence 等级
```

### 10.5 Adjudicator 质量门控

```yaml
pass_candidate requires:
  - review_status == complete
  - no high/medium findings
  - pack_completeness >= 0.7
  - evidence 全部 pass 或无 evidence（error/skipped 不允许 pass_candidate）

concerns 上限:
  - review_status == "truncated" → verdict 最高 concerns
  - speculative_ratio > 50% → verdict 最高 concerns + 附加警告

needs_human_triage 触发:
  - evidence 有 fail 但 reviewer 未发现相关 finding
  - 所有 high severity findings 都是 speculative
```

### 10.6 History Log（v0 opt-in，默认关闭）

```yaml
v0 可选记录每次 review 到 ~/.crossreview/history.jsonl:

开启方式: --record-history 或 crossreview.yaml 中 history.enabled: true
默认: 关闭（v0 核心价值是 pack + review + eval gate，不是 history）

字段: review_id, timestamp, artifact_fp, pack_fp, findings_count,
      verdict, pack_completeness, speculative_ratio, review_status

用途: v1 可基于历史数据做趋势分析和 circuit breaker
v0 不消费此数据
```

### 10.7 质量度量在输出中的呈现

#### Human-readable 输出

```
CrossReview v0-alpha | artifact: a3f2b1c | review_status: complete

Intent: 修复 token refresh 过期判断
Intent Coverage: covered
Pack Completeness: 0.85

Findings (3):
  [HIGH]  src/auth/refresh.ts:42 — Token expiry off-by-one
          exact | plausible | actionable | evidence: related_file
          Diff hunk: @@ -40,3 +40,3 @@

  [MED]   src/auth/refresh.ts:67 — Missing network timeout handling
          exact | plausible | actionable
          Diff hunk: @@ -65,5 +65,8 @@

  [LOW]   src/auth/types.ts:15 — No unit documentation for refreshInterval
          file_only | plausible | actionable
          Diff hunk: @@ -14,2 +14,3 @@

Evidence:
  npm test: 47 passed, 0 failed

Diagnostics:
  Speculative: 0% | Noise: 0

Advisory Verdict: concerns
  Rationale: 1 high-severity off-by-one in core auth logic

Fingerprint: diff:a3f2b1c | pack:e7d4a2f | reviewer:fresh_llm_v0
```

### 10.8 维度总览

| # | 维度 | v0 状态 | 用途 |
|---|------|---------|------|
| 1 | `finding.locatability` | ✅ 核心 | severity 约束、输出显示 |
| 2 | `finding.confidence` | ✅ 核心 | plausible/speculative 二级，severity 约束 |
| 3 | `finding.evidence_related_file` | ✅ 核心 | file-level evidence 关联标记（不升级 confidence） |
| 4 | `finding.actionable` | ✅ 核心 | 可行动性标记 |
| 5 | `pack_completeness` | ✅ diagnostic | pack 质量评估、pass_candidate 条件 |
| 6 | `noise_count` | ✅ diagnostic | 噪音追踪 |
| 7 | `speculative_ratio` | ✅ diagnostic | reviewer 质量指示 |
| 8 | `locatability_distribution` | ✅ diagnostic | 定位精度统计 |
| 9 | `history_log` | ✅ opt-in | v1 趋势分析数据采集（v0 默认关闭） |
| 10 | `corroborated` confidence | ❌ v1 | 需 line/text evidence match 支撑 |
| 11 | `verdict_confidence` | ❌ v1 | 多因子加权 |
| 12 | `circuit_breaker` | ❌ v1 | 连续低质量触发策略调整 |

> **设计来源索引**：Graphify 三级置信度 → locatability/confidence 分离；Graphify corpus gate → pack_completeness；
> Graphify edge distribution → speculative_ratio；HelloAgents ralph-loop → noise_count + history_log + circuit_breaker (v1)。

---

## §11 手工流程中的隐性知识显式化

### v0 可协议化的部分

| 手工行为 | v0 协议化方式 |
|----------|-------------|
| 选什么 context 贴 | `--diff`, `--context`, `--task` 参数 |
| 描述任务意图 | `--intent` 参数 |
| 标记重点区域 | `--focus` 参数 |
| 贴 lint/test 结果 | `--evidence-cmd` 参数 |
| 控制审查范围 | budget 配置 |

### v0 承认做不到的部分

| 手工行为 | v0 限制 | 计划版本 |
|----------|---------|---------|
| 追问模型细化 finding | 单轮审查，不追问 | v1 |
| 过滤明显胡说的 finding | 靠 noise_cap + severity 规则 | v1 |
| 根据经验调整 prompt | 固定 review prompt 模板 | v1 |
| 跨 finding 关联分析 | 每个 finding 独立 | v2 |
| 消除 pack 携带的 producer bias | prompt 层声明 intent/focus 为"待验证声明"；但 pack 内容仍由 producer 构造，结构性偏置无法完全消除 | v1（反馈闭环） |

---

## §12 Success Criteria & Release Gate

### Blocking Release Gates（全部必须达标）

```yaml
blocking_release_gates:
  manual_recall: ≥ 0.80          # 覆盖手工 cross-review 发现的有效问题
  precision: ≥ 0.70              # valid / (valid + invalid)，unclear 不计入分母
  invalid_findings_per_run: ≤ 2  # total_invalid / successful_runs（均值）；另加 max_invalid_single_run ≤ 5
  unclear_rate: ≤ 0.15           # total_unclear / total_auto_findings
  context_fidelity: ≥ 0.80       # required context_items covered_by_pack == true 的比例（人工标记）
  actionability: ≥ 0.90          # 人工 adjudication 后 valid findings 中 actionability_judgment == actionable 的比例
  failure_rate: ≤ 0.10           # failed_runs / total_runs；failure = review_status ∈ {rejected, failed} / output malformed / model error/timeout（truncated ≠ failure）
  fixture_count: ≥ 20            # 目标 50
```

#### Fixture Pool 组成约束

```yaml
pool_definitions:
  self_hosting_pool:
    definition: cross-review 仓库自身的提交（reviewer 审查自己的代码变更）
    用途: pack fidelity 回归、normalizer 鲁棒性、boundary regression
    归属: dogfooding / self-hosting signal，单列，不作为主报指标
    上限: release gate fixture_count 中 ≤ 25%
  external_eval_pool:
    definition: 非 cross-review 的目标代码库提交（hermes / helloagents / graphify 等）
    用途: precision / manual_recall / invalid_per_run / 泛化能力
    归属: release gate 主报

reporting_rule:
  primary: external-only        # 决定是否有泛化能力的主指标
  supplementary: overall        # 含 self-hosting，用于回归与全局稳定性观察
```

> **注意**：self_hosting_pool 的 25% 上限只约束 release gate fixture_count，
> 不约束内部回归集。内部 regression suite 可以有更多 self-hosting case，
> 用于 1B.1-fidelity、normalizer golden test、pipeline 自动化验证等。
>
> **Gate 判定范围**：
> - `fixture_count >= 20` 按 **overall**（含 self-hosting）计数
> - `precision / manual_recall / invalid_findings_per_run` 的主报 pass/fail 以 **external-only** 为准
> - overall 值作为补充观察指标，不阻 release

### Diagnostic Metrics（观察不阻 release，评估时关注）

```yaml
diagnostic_metrics:
  pack_completeness              # 运行时启发式结构完整度（不和 manual baseline 对比）
  locatability_distribution      # exact / file_only / none 占比
  speculative_ratio              # speculative finding 占比
  evidence_related_file_rate     # evidence_related_file == true 的 finding 占比
  triage_time                    # 端到端时间（含人工筛选）
  model_latency_sec              # 模型调用耗时（秒），不含 evidence 收集和 pack 构建
  input_tokens                   # reviewer LLM 输入 token 数
  output_tokens                  # reviewer LLM 输出 token 数
  # 注：不在 v0 计算 estimated_cost；不同 provider 计价方式不同，用户可根据 token 数自行估算
```

### 指标收集方式

```bash
# 运行评估（dev-only，不是 v0 public CLI）
python -m crossreview_eval --fixtures ./fixtures/ --output eval-report.json

# 评估报告包含:
# - 每个 fixture 的 finding 列表
# - 人工 adjudication 结果（valid / invalid / unclear）
# - blocking gates 达标状态
# - diagnostic metrics 统计
# - 与手工 baseline 的对比
```

---

## §13 Exit Strategy

### 假设不成立时

如果 v0 评估跑不过 release gate：

```yaml
退路 1 (指标接近但未达标):
  - 调优 review prompt 模板
  - 优化 pack 策略（context 选择、排序）
  - 重跑评估

退路 2 (指标差距较大):
  - CrossReview 退回为 prompt pattern
  - 发布为 "cross-review best practices" 文档
  - 不做独立产品化

退路 3 (根本性问题):
  - 如果自动 pack 质量无法接近手工质量
  - 或者单轮审查的 precision 根本不可接受
  - 存档方案，等待模型能力提升后重新评估
```

### 不做沉没成本决策

> 如果实验数据说明自动化质量不够，就停。不要因为"已经写了代码"而勉强产品化。

---

## §14 v0 → v1 演进信号

以下信号出现时，考虑进入 v1：

```yaml
v1 触发条件 (需全部满足):
  - v0 release gate 已通过
  - 日常使用 > 2 周
  - 用户手工 cross-review 频率显著下降
  - 积累了 "希望能追问 / 希望能跨模型 / 希望能集成 CI" 的需求

v1 可能包含:
  - 稳定 public SDK
  - cross_model_reviewer
  - MCP Server
  - 多轮 review（自动追问）
  - 反馈闭环（标记误报 → 调优）
```

---

## Appendix A: Naming Decisions (继承自 background.md)

| 项目 | 决策 |
|------|------|
| 产品品牌 | CrossReview（独立产品，无 sopify- 前缀） |
| 能力名 | cross-review |
| 配置 key | cross_review |
| schema 版本 | 0.1-alpha |
| CLI 命令 | crossreview |
| Reviewer 名 | fresh_llm_reviewer（独立产品视角，无 same_model 限定） |
| Evidence collector 名 | deterministic_evidence（不是 reviewer） |

## Appendix B: 与现有文档的关系

| 文档 | 状态 | 说明 |
|------|------|------|
| background.md | 有效 | 问题定义和命名决策仍然适用 |
| design.md | 部分有效 | 核心抽象和 schema 继续参考，但 MVP scope 以本文档为准 |
| tasks.md | 需更新 | Phase 1 定义需按本文档收窄 |
| cross-project-insights.md | 有效 | 12 个外部项目洞察，v0 只采纳 P1 优先级的部分 |
| product-form-analysis.md | 被取代 | 宽泛 MVP 定义被本文档替代 |
| hermes-insights.md | 有效 | SkillGuidedReviewer 等留给 v1+ |
