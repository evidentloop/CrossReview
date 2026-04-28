# CrossReview 产品总纲

> **Status**: Active — v0.1.0a1 已发布，v0.5 dogfood 准备中
> **创建日期**: 2026-04-25
> **定位**: 产品级总纲文档，覆盖 v0→v2 全生命周期规划
> **前置**: v0-scope.md（v0 精确范围）、20260424_lightweight_pluggable_architecture（Sopify 方案总纲）
> **最近同步**: 2026-04-28 — 同步 README / CHANGELOG / PyPI 0.1.0a1 发布事实

---

## §1 产品定位

### 一句话定位

> **CrossReview 是 AI 编程时代的独立审查基础设施** — 通过 context isolation 协议，为 AI 生成的任意制品（代码、设计、方案、分析）提供可量化、可审计、可复现的独立验证。

### 核心洞察

1. **价值来源是 context isolation，不是 model diversity。** 同一模型在 fresh session 中审查，等价于"另一个人看你的代码"。跨模型是增强手段（v1+），不是核心价值。

2. **审计的核心是独立性。** 内置 agent 天然缺乏独立性 — 它共享开发 session 的全部上下文（reasoning trace、重试历史、工具调用记录），本质是"自己审自己"。CrossReview 通过 isolation boundary 提供结构性独立保证。

3. **不止代码，是全制品。** CrossReview 的协议层（ReviewPack → Reviewer → ReviewResult）对任意可审查 artifact 成立。v0 聚焦 `code_diff` 验证核心假设，但架构已为 `design_doc` / `plan` / `analysis` 预留扩展路径。

4. **确定性判定是差异化护城河。** 只有 Reviewer 调用 LLM，Normalizer 和 Adjudicator 完全规则化 — 这意味着判定可测试、可复现、可解释。所有竞品都是全 LLM 判定。

---

## §2 竞争格局

### 与 LLM 内置 Code Review Agent 的关系

#### 总览对比

| 维度 | Copilot Code Review | Codex 内置 | Claude Code（/review + /ultrareview） | CrossReview |
|------|---------------------|-----------|---------------------------------------|-------------|
| **上下文边界** | 共享 PR session | 共享 Codex session | /review 共享 session；/ultrareview 隔离 | 隔离：reviewer 只看 ReviewPack |
| **审查本质** | 自检 | 自检 | /review = 自检；/ultrareview = 远程隔离 | 独立审计 |
| **判定层** | LLM 全程 | LLM 全程 | LLM 全程 | Normalizer + Adjudicator **规则化** |
| **Finding 约束** | 无 | 无 | 无 | 5 条约束规则 |
| **噪音控制** | prompt tuning | prompt tuning | /security-review 有 confidence≥8 过滤 | 推测语言检测 + 约束降级 + 硬上限 |
| **可审计性** | 无 | 无 | 无 fingerprint | SHA-256 双指纹 + raw_analysis |
| **质量度量** | 不透明 | 不透明 | 不透明 | 9 指标 release gate + eval fixture |
| **集成方式** | GitHub 锁定 | OpenAI 锁定 | Anthropic 锁定 | CLI-first + 多模式开放接入 |
| **多 agent** | 单 agent | 单 agent | /ultrareview: 5-20 Bughunter fleet | 单 reviewer（v1 扩展多模型） |

#### Claude Code 深度分析（基于源码）

Claude Code 有**三层 review 能力**（源码路径：`src/commands/review.ts`、`src/commands/review/reviewRemote.ts`、`src/commands/security-review.ts`）：

**第 1 层：`/review`（本地 review）**
```typescript
// review.ts:9-31 — 纯 prompt 驱动，共享当前 session
const LOCAL_REVIEW_PROMPT = (args) => `
  You are an expert code reviewer. Follow these steps:
  1. Run gh pr list / gh pr view / gh pr diff
  2. Analyze: code quality, style, performance, test coverage, security
`
```
- **无隔离**：在当前开发 session 中执行，继承全部对话历史
- **无结构化输出**：LLM 自由格式输出
- **无判定规则**：LLM 自行判断严重性

**第 2 层：`/ultrareview`（远程 Bughunter）**
```typescript
// reviewRemote.ts:167-203 — 远程隔离执行
const CODE_REVIEW_ENV_ID = 'env_011111111111111111111113'
BUGHUNTER_FLEET_SIZE: 5-20        // 5-20 个 agent 并行
BUGHUNTER_MAX_DURATION: 10-25     // 分钟
BUGHUNTER_TOTAL_WALLCLOCK: 22-27  // 含 finalization
```
- **有隔离**：通过 `teleportToRemote()` 在云端创建 fresh session，clone PR head ref 或 bundle 工作树
- **多 agent**：5-20 个 Bughunter agent 并行寻找 bug
- **但无确定性判定**：找到的 bug 由 LLM 验证（`finding → verifying → synthesizing`），无规则引擎
- **付费功能**：Team/Enterprise 无限制，个人有免费额度
- **平台锁定**：只在 Claude Code 内可用

**第 3 层：`/security-review`（安全审查）**
```typescript
// security-review.ts:42-43 — 3 阶段异步验证
// 1. 子任务识别漏洞
// 2. 并行子任务过滤误报（confidence ≥ 8）
// 3. 最终报告只包含 HIGH/MEDIUM
```
- **有噪音控制**：confidence scoring (1-10) + 17 条硬排除规则 + precedent 规则
- **子任务并行验证**：每个 finding 独立子任务验证
- **但仍全 LLM**：验证由子任务 LLM 执行，不是规则引擎

#### CrossReview vs Claude Code /ultrareview — 关键差异

| 维度 | /ultrareview | CrossReview |
|------|-------------|-------------|
| **隔离方式** | 云端 clone PR → fresh session | ReviewPack 协议 → fresh session |
| **隔离粒度** | 整个仓库 clone | 只传 diff + minimal context（更少 bias） |
| **判定层** | LLM 验证 | **规则引擎**（确定性、可测试） |
| **Finding 格式** | LLM 自由输出 | 结构化 Finding（severity/locatability/confidence 三维） |
| **审计链** | 无 fingerprint | SHA-256 双指纹 + raw_analysis |
| **开放性** | Anthropic 锁定 | CLI + MCP + API 开放接入 |
| **成本** | 5-20 agent × 10-25 min = 高成本 | 1 reviewer × 1 次调用 = 低成本 |
| **可移植性** | 不可移植 | 任何 AI 工具可接入 |
| **质量度量** | 无公开 eval | 9 指标 release gate |

**核心洞察**：Claude Code 的 /ultrareview 在**隔离性**上做了正确的事（remote fresh session），但在**判定可靠性**上仍然是全 LLM —— 5-20 个 agent 的 finding 最终由 LLM synthesize，没有确定性规则保证。CrossReview 用 1 个 reviewer + 确定性 Normalizer/Adjudicator，达到同等或更高的判定可靠性，且成本低一个量级。

**互补关系**：CrossReview 可以作为 /ultrareview 的**后处理层** — 接收 Bughunter 的 raw output，通过 Normalizer + Adjudicator 做确定性质量保证。这不是替代，是增强。

**核心结论**：即使 Claude Code 有了 /ultrareview 的 context isolation，CrossReview 仍然有不可替代的价值 — **确定性判定层 + 结构化 Finding 约束 + 可审计指纹 + 开放接入**。内置 agent 越强，CrossReview 作为独立验证基础设施的价值越大。

#### GitHub Copilot Code Review 架构分析

2026 年 3 月，GitHub Copilot Code Review 升级为 **agentic architecture**：

**执行方式**：
- 在 GitHub Actions 隔离容器中运行
- 可读取整个仓库结构、跨文件依赖、相关文件（不只看 diff）
- 支持 MCP 集成（企业用户可接入私有模型）

**Review 流程**：
```
PR 触发
  ↓
Context Gathering（读 diff + 整个文件 + 跨文件依赖 + 测试覆盖）
  ↓
LLM Analysis（模式识别 + 架构偏移检测 + 安全分析）
  ↓
Inline Comment + Summary（直接发到 PR）
  ↓
开发者可回复 → Agent 可重新 review
```

**优势**：
- 架构级理解（不只看变更行，看整个文件）
- GitHub 原生集成（无需安装额外工具）
- 支持迭代 review（开发者回复后可重新审查）

**局限**（vs CrossReview）：
- **无显式隔离边界** — agent 在 PR context 中运行，但不保证与 author session 隔离
- **全 LLM 判定** — 无确定性规则引擎
- **无结构化 Finding 约束** — LLM 说 HIGH 就是 HIGH
- **无审计指纹** — 无法追溯"审查了哪个版本"
- **平台锁定** — 只在 GitHub 内可用
- **质量不透明** — 无公开 eval 数据

#### OpenAI Codex Code Review 架构分析

Codex（基于 GPT-5.5）的 review 采用 **多 agent 并行**架构：

**执行方式**：
- Cloud sandbox（clone 仓库到隔离容器）或 CLI 本地模式
- 可运行测试、lint、静态分析（不只看代码）
- 支持 AGENTS.md 自定义行为

**Review 流程**：
```
PR/任务触发
  ↓
Clone 仓库到 sandbox
  ↓
多 agent 并行：
  ├── Agent A: 读 diff + 分析代码质量
  ├── Agent B: 运行测试
  ├── Agent C: 静态分析
  └── Agent D: 安全扫描
  ↓
合并结果 → 生成 commit/comment + 证据链（diff, logs, test results）
```

**优势**：
- 多 agent 并行（类似 Claude /ultrareview 的 Bughunter fleet）
- 可执行工具（测试、lint），不只读代码
- AGENTS.md 自定义（项目级配置）
- CLI suggest / auto-edit / full-auto 模式

**局限**（vs CrossReview）：
- **sandbox isolation ≠ context isolation** — sandbox 隔离的是执行环境，不是审查者的认知上下文
- **全 LLM 合并** — 多 agent 结果由 LLM 合并，无确定性后处理
- **无 Finding 约束** — 无 severity/locatability/confidence 三维验证
- **平台绑定** — OpenAI 生态内
- **质量不可量化** — 无 eval 体系

#### 四方对比总结

| 维度 | Copilot Review | Codex Review | Claude /ultrareview | **CrossReview** |
|------|---------------|-------------|--------------------|-|
| **隔离类型** | Actions 容器隔离 | Sandbox 环境隔离 | 云端 session 隔离 | **认知 context 隔离** |
| **隔离目标** | 安全（不泄漏 secrets） | 安全（sandbox） | 审查独立性 | **审查独立性** |
| **判定层** | 全 LLM | 全 LLM | 全 LLM | **规则引擎** |
| **Finding 结构** | 自由文本 | 自由文本 + diff | 自由文本 | **结构化 Finding** |
| **约束规则** | 无 | 无 | 无 | **5 条** |
| **审计指纹** | 无 | 有 evidence trail | 无 | **SHA-256 双指纹** |
| **质量度量** | 不透明 | 不透明 | 不透明 | **9 指标 release gate** |
| **成本** | 包含在订阅中 | 包含在订阅中 | 免费额度 + 付费 | **1 次 LLM 调用** |
| **开放性** | GitHub only | OpenAI only | Anthropic only | **MIT 开源 + 任意接入** |
| **多 agent** | 单 agent | 多 agent 并行 | 5-20 Bughunter | **单 reviewer（v1 扩展）** |
| **执行工具** | 无 | 测试 + lint | 测试 + lint | **Evidence Collector（v0.5）** |
| **全制品审查** | ❌ 只看代码 | ❌ 只看代码 | ❌ 只看代码 | **✅ 协议层支持全制品** |

**关键洞察**：

1. **隔离类型不同**。Copilot/Codex 的隔离是**安全隔离**（sandbox/container），防止代码泄漏。Claude /ultrareview 和 CrossReview 的隔离是**认知隔离**（fresh context），防止 author bias。前者解决安全问题，后者解决审查质量问题。

2. **CrossReview 是唯一有确定性判定层的**。其他三个全部依赖 LLM 做最终判断 — LLM 说这个 finding 是 HIGH 就是 HIGH，没有规则校验。

3. **CrossReview 是唯一可量化质量的**。其他三个的 precision/recall 是黑盒。CrossReview 有 33 fixture + 9 指标 release gate，可以公开说"precision ≥ 0.70"。

4. **CrossReview 是唯一支持全制品的**。协议层（ReviewPack → ReviewResult）不限于 code_diff，可扩展到 design/plan/analysis。其他三个只看代码。

### 与独立 AI Code Review 工具的关系

| 竞品 | 定价 | 核心能力 | CrossReview 差异 |
|------|------|---------|-----------------|
| **CodeRabbit** | $0-$48/user/mo | PR 级 AI review，inline comment | 无隔离边界，全 LLM 判定，无公开 eval |
| **Qodo** | $19-30/user/mo | 多仓库上下文，合规检查 | 无 isolation 概念，侧重规则检查非独立审查 |
| **Sourcery** | $12-24/user/mo | Python 专精，refactoring | diff-only，语言限制，无结构化判定 |
| **Greptile** | $30/user/mo | 大仓库深度分析 | 依赖图分析，但无 isolation + 确定性裁决 |
| **Codacy** | $15/user/mo | 多语言静态分析 | SAST 为主，AI 为辅，定位不同 |

**所有竞品共同缺失的能力**：
1. Context isolation（隔离边界）
2. 确定性判定层（规则化 Normalizer + Adjudicator）
3. 公开可验证的 eval 体系（fixture + release gate metrics）
4. 全制品审查愿景（所有竞品只做 code review）

### 蓝海机会

**在软件工程领域，目前没有专门的 AI 全制品审查工具。** 所有竞品都只覆盖代码。CrossReview 扩展到 design/plan 审查时，进入的是一个无直接竞品的市场。

---

## §3 技术架构分析

### 核心管线

```
Artifact（diff / design / plan / analysis）
    ↓
┌─────────────────────┐
│   Pack（组装 ReviewPack）│  确定性：输入打包 + SHA-256 指纹
└────────┬────────────┘
         ↓
┌─────────────────────┐
│   Budget Gate       │  确定性：focus-priority 排序 + 软硬截断
└────────┬────────────┘
         ↓
╔══════════════════════╗
║   Isolation Boundary ║
║   ┌───────────────┐  ║
║   │ Reviewer (LLM)│  ║  AI 层：fresh session，零共享上下文
║   └───────┬───────┘  ║
╚═══════════╪══════════╝
            ↓
┌─────────────────────┐
│   Normalizer        │  确定性：regex 提取 + 约束降级
└────────┬────────────┘
         ↓
┌─────────────────────┐
│   Adjudicator       │  确定性：10 条规则链 → advisory verdict
└────────┬────────────┘
         ↓
┌─────────────────────┐
│   ReviewResult      │  Findings + Verdict + QualityMetrics
└─────────────────────┘
```

**关键设计原则**：只有 Reviewer 一处调用 LLM，其余全部确定性。这保证了：
- **可测试**：Normalizer + Adjudicator 可完全单元测试
- **可复现**：同样的 raw analysis → 同样的 findings → 同样的 verdict
- **可解释**：每条 finding 有 severity/locatability/confidence 三维标注，verdict 有 rationale

### 双模式架构

| 模式 | 执行路径 | 依赖 | 适用场景 |
|------|---------|------|---------|
| **Standalone** | `crossreview verify --pack` | anthropic SDK + API key | 独立使用 |
| **Host-integrated** | `render-prompt` → 宿主执行 → `ingest` | 无额外 SDK | 任何 AI 工具接入 |

Host-integrated 模式是开放接入的核心：宿主用自己的 LLM context window 执行 canonical prompt，CrossReview 只负责输入组装（pack）和输出质量保证（normalizer + adjudicator）。

### 全制品扩展架构

```python
# 扩展 artifact_type 不需要架构变更
class ArtifactType(str, Enum):
    CODE_DIFF = "code_diff"      # v0 ✅
    DESIGN_DOC = "design_doc"    # v1+ 📋
    PLAN = "plan"                # v1+ 📋
    ANALYSIS = "analysis"        # v2+ 📋
    REVIEW_RESULT = "review_result"  # v2+ 📋（review 的 review）
```

**扩展增量**（每种新 artifact type 需要）：
1. 对应的 prompt 模板（替换 code-specific 指令）
2. Finding 约束参数适配（如 plan 审查无 file:line，改用段落定位）
3. 对应的 eval baseline（fixture + 人工标注）

**不需要改的**：ReviewPack schema、Normalizer 核心逻辑、Adjudicator 规则链、Budget Gate、CLI 接口

---

## §4 评审体系设计

### 设计原则

评审体系是 CrossReview 的质量基石和竞争壁垒。它必须：
1. **独立迭代** — 不依赖产品形态，可以在 CLI/MCP/Action 之前就验证质量
2. **按 artifact type 分隔** — 每种制品有独立的 eval baseline 和 release gate
3. **可增量扩展** — 新 artifact type 加入时只需新建 fixture set，不影响已有验证

### 评审体系架构

```
eval/
├── code_diff/                    # v0
│   ├── fixtures/                 # 20+ 真实 diff + 人工标注
│   │   ├── 001-hermes-subshell-leak/
│   │   │   ├── pack.json
│   │   │   ├── review-result.json
│   │   │   ├── manual-findings.yaml
│   │   │   └── auto-adjudications.yaml
│   │   └── ...
│   ├── release-gate.yaml         # 9 指标阈值
│   └── eval-harness.py
├── design_doc/                   # v1+
│   ├── fixtures/
│   ├── release-gate.yaml         # 独立阈值（可能不同于 code_diff）
│   └── eval-harness.py
├── plan/                         # v1+
│   ├── fixtures/
│   ├── release-gate.yaml
│   └── eval-harness.py
└── shared/
    └── metrics.py                # 共享指标计算逻辑
```

### v0 Release Gate（code_diff）

| 指标 | 定义 | 阈值 |
|------|------|------|
| `manual_recall` | 自动 finding 覆盖人工 baseline 的比例 | ≥ 0.80 |
| `precision` | valid / (valid + invalid) | ≥ 0.70 |
| `invalid_findings_per_run` | 每次运行的无效 finding 数 | ≤ 2 |
| `max_invalid_single_run` | 单次运行最大无效 finding 数 | ≤ 5 |
| `unclear_rate` | unclear finding 占比 | ≤ 0.15 |
| `context_fidelity` | required context 被 pack 包含的比例 | ≥ 0.80 |
| `actionability` | 有效 finding 中可直接指导修改的比例 | ≥ 0.90 |
| `failure_rate` | 运行失败比例 | ≤ 0.10 |
| `fixture_count` | fixture 数量 | ≥ 20 |

此外，`self_hosting_pool_limit_ok`（self_hosting fixture 比例 ≤ 25%）作为 fixture 池组成约束参与 `blocking_pass` 判定，但不计入 9 指标。

**不满足时的退出策略**：退回为 prompt pattern / agent skill，不做独立产品化。

### v0 Release Gate 当前实测结果（33 fixtures, 2026-04-27）

> 以下数据与 `CHANGELOG.md` 0.1.0a1、README 当前 release gate 摘要一致。

| 指标 | 阈值 | 实测 | 通过 |
|------|:---:|:---:|:---:|
| `manual_recall` | ≥ 0.80 | **0.929** | ✅ |
| `precision` | ≥ 0.70 | **0.885** | ✅ |
| `invalid_findings_per_run` | ≤ 2 | **0.158** | ✅ |
| `max_invalid_single_run` | ≤ 5 | **1** | ✅ |
| `unclear_rate` | ≤ 0.15 | **0.133** | ✅ |
| `context_fidelity` | ≥ 0.80 | **1.000** | ✅ |
| `actionability` | ≥ 0.90 | **1.000** | ✅ |
| `failure_rate` | ≤ 0.10 | **0.000** | ✅ |
| `fixture_count` | ≥ 20 | **33** | ✅ |

**Release Gate 结果**：`blocking_pass: true` — 9/9 blocking metrics 通过，self_hosting_pool_limit_ok 通过。评测池为 30 external + 3 self-hosting fixtures。

**关键观察**：
- recall (0.929) 远超阈值，说明审查覆盖度优秀
- precision (0.885) 健康，false positive 率低
- unclear_rate (0.133 ≤ 0.150) 已解除 v0-04a 阻塞
- v0-05 human-readable output 与 v0-06 one-stop `verify --diff` 已随 0.1.0a1 发布

### 全制品 Release Gate 设计思路

| Artifact Type | 定位特殊性 | Recall 预期 | Precision 预期 |
|---------------|-----------|-------------|---------------|
| `code_diff` | file:line EXACT 定位 | ≥ 0.80 | ≥ 0.70 |
| `design_doc` | 段落/章节定位 | ≥ 0.70（初期）| ≥ 0.65（初期）|
| `plan` | 任务项/步骤定位 | ≥ 0.70（初期）| ≥ 0.65（初期）|

**design/plan 的阈值初期可以低于 code_diff**：因为架构审查本身更主观，perfect recall/precision 不现实。但必须有明确阈值，否则质量声明无法建立。

---

## §5 产品形态迭代路线

### 迭代优先级矩阵

| 形态 | 目标用户 | 摩擦度 | 价值密度 | 实现复杂度 | 优先级 |
|------|---------|--------|---------|-----------|--------|
| **CLI** | 开发者 | 低 | 中 | 低（已完成） | **v0 ✅** |
| **Sopify 插件** | Sopify 用户 | 低 | 高 | 中 | **v0.5 / advisory 已起草** |
| **PyPI 发布** | Python 社区 | 极低 | 中 | 低 | **v0.1.0a1 ✅** |
| **GitHub Action** | GitHub 用户 | 极低 | 高 | 中 | **v1** |
| **MCP Server** | AI 工具生态 | 中 | 高 | 中 | **v1** |
| **Stable Python SDK** | 集成开发者 | 中 | 中 | 低 | **v1** |
| **Hosted API** | 企业/平台 | 低 | 极高 | 高 | **v1.5** |
| **VS Code Extension** | IDE 用户 | 低 | 中 | 中 | **v2** |

### 版本路线图

#### v0 — 验证核心假设（已完成 → 0.1.0a1）

```yaml
目标: 证明"context isolation + 确定性判定"在 code_diff 上可行
产品形态: CLI (crossreview pack / verify / render-prompt / ingest)
许可: MIT
分发: GitHub + PyPI 0.1.0a1

里程碑:
  1. 33 fixture eval 全量通过 9 指标 release gate
  2. human-readable output (--format human)
  3. one-stop verify (crossreview verify --diff)
  4. render-prompt + ingest host-integrated 模式

v0 的退出条件:
  已满足，进入 v0.5 dogfood / integration 阶段
  不通过 → 退回 prompt pattern / agent skill，不做独立产品化
```

#### v0.5 — 生态集成 + dogfood

```yaml
目标: 验证独立产品身份 + Sopify 生态集成
产品形态: CLI + PyPI 包 + Sopify advisory 插件 (对标 Graphify 模式)

里程碑:
  1. PyPI 0.1.0a1 已发布，后续只做发布 smoke 与必要补丁
  2. Sopify advisory 模式集成（方案总纲 Phase 4a，不依赖 Phase 3）
     - 纯 SKILL.md + skill.yaml，无 bridge.py
     - LLM 读 SKILL.md 后自行调用 crossreview CLI
     - 在 develop 完成后审查 code_diff
  3. 3 项目 dogfood：验证 LLM 是否可靠遵循 advisory SKILL.md
  4. 至少 2 篇技术文章（技术影响力建设）
  5. 50 fixture 目标（持续扩充 eval 体系）

关键产出:
  - crossreview 0.1.0a1 on PyPI
  - Sopify .agents/skills/cross-review/ 目录（SKILL.md + skill.yaml，advisory mode）
  - 技术博客："为什么 AI 编程需要独立审查"

注意: Sopify 完整 runtime 集成（bridge.py + pipeline_hooks）属于 Phase 4b 冻结项，
      不进入 0-6 个月承诺；需 Phase 3 就绪、Phase 4a 价值验证和 v0 release gate 通过后重新评审。
```

#### v1 — 多通道 + 全制品启动

```yaml
目标: 从"CLI 工具"升级为"AI 审查基础设施"
产品形态: CLI + GitHub Action + MCP Server + Stable SDK

新增能力:
  核心:
    1. cross-model reviewer（多模型审查）
    2. design_doc artifact type（方案审查）
    3. plan artifact type（任务方案审查）

  通道:
    4. GitHub Action（PR 触发自动 review → inline comment）
    5. MCP Server（任意 AI 助手可调用）
    6. Public stable Python SDK

  质量:
    7. design_doc eval baseline（fixture + release gate）
    8. plan eval baseline
    9. Eval dashboard（质量趋势可视化）

里程碑:
  1. GitHub Action v1 发布到 Marketplace
  2. MCP Server 可被 Claude / Copilot / Cursor 调用
  3. design_doc 通过独立 release gate
  4. 100 fixture 总量（code_diff + design_doc + plan）
```

#### v1.5 — 商业化启动（待定）

> **状态**：商业化路径待定。在用户采纳和企业需求明确前，不做具体定价和基础设施投入。

```yaml
目标: 建立可持续商业模式
产品形态: 上述全部 + Hosted API
状态: 待定 — 触发条件:
  - v0 release gate 通过
  - GitHub Action 上线并有自然采纳
  - 收到第一个企业询盘
  触发前: 保持 MIT 全免费，精力聚焦 v0-v1

可能路径（不做承诺）:
  A. 纯开源 + 咨询定制（最低风险）
  B. Open Core: 免费 CLI/Action + 付费 Hosted API/Enterprise（最常见）
  C. 协议标准 + 认证生态（最高上限，最不确定）

v1.5 如果启动，新增:
  1. Hosted Review API（pay-per-review）
  2. 企业 policy engine（自定义判定规则）
  3. 团队 review quality dashboard
  4. SSO / RBAC（企业需求）

定价策略: 待定（需要用户数据支撑）
```

#### v2 — 质量基础设施

```yaml
目标: 成为 AI 编程时代的质量标准
产品形态: 全通道 + 知识库 + 合规

新增:
  1. analysis / review_result artifact type（review 的 review）
  2. 全链路审查（code → design → plan 联动）
  3. review 知识库累积 → 项目级风险画像
  4. 合规报告生成（SOC2 / ISO 27001 审计证据）
  5. Eval-as-a-Service（企业量化自己的 review 质量）
  6. ReviewPack / ReviewResult 协议标准化提案

愿景:
  CrossReview 协议（ReviewPack → Reviewer → ReviewResult）
  成为 AI 编程时代的"独立审查标准"
  — 就像 SARIF 是静态分析的标准，CrossReview 是 AI 审查的标准
```

---

## §6 开放接入策略

### 核心原则

> **CrossReview 是能力层（protocol + engine），不是平台。任何产品都可以接入。**

### 接入方式矩阵

| 接入方式 | 描述 | 适用场景 | 版本 |
|---------|------|---------|------|
| **CLI** | `crossreview pack + verify` | 手工使用、脚本集成 | v0 ✅ |
| **render-prompt + ingest** | 宿主控制 LLM 调用 | 任何 AI 工具 | v0 ✅ |
| **Sopify 插件** | Phase 4a advisory；Phase 4b runtime 冻结 | Sopify 用户 | v0.5 (advisory) / 🧊 冻结 |
| **GitHub Action** | PR 触发自动 review | GitHub 用户 | v1 |
| **MCP Server** | MCP 协议暴露 | AI 助手生态 | v1 |
| **Python SDK** | `import crossreview` | 集成开发者 | v1 |
| **Hosted API** | HTTP REST API | 企业/平台 | v1.5 |

### `render-prompt + ingest` 是最关键的开放接入点

```
任何 AI 编程工具（Cursor / Windsurf / JetBrains AI / Trae / …）
    ↓
crossreview render-prompt --pack pack.json > prompt.md
    ↓
工具在自己的隔离 context 中执行 prompt
    ↓
crossreview ingest --raw-analysis output.md --pack pack.json
    ↓
标准化 ReviewResult JSON
```

**接入者无需**：CrossReview 的 API key / 额外 LLM 调用成本 / 理解内部实现
**CrossReview 只负责**：输入组装（pack）+ 输出质量保证（normalizer + adjudicator）

---

## §7 关键风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| v0 release gate 不通过 | 产品化失败 | 退回 prompt pattern，保留核心 IP |
| design/plan eval baseline 建立困难 | 全制品扩展受阻 | 先用 Sopify dogfood 积累 fixture |
| 竞品复制 isolation 概念 | 差异化被稀释 | eval 体系 + 规则引擎是劳动密集型壁垒 |
| LLM 调用成本过高 | 用户采纳受阻 | host-integrated 模式用宿主自己的 LLM |
| 多 artifact type 质量不一致 | 品牌信任受损 | 每种 artifact 独立 release gate，不达标不发布 |

---

## §8 总结

### 产品潜力评估

| 维度 | 判断 |
|------|------|
| **立意合理性** | ✅ context isolation 是真实洞察，对标人类工程实践 |
| **与内置 agent 的关系** | 互补而非竞争 — 独立审计 vs 自检 |
| **竞争差异化** | 结构性差异：隔离边界 + 确定性判定 + 公开 eval |
| **全制品扩展潜力** | 蓝海 — 软件工程领域无专门的 AI 全制品审查工具 |
| **商业化可行性** | 渐进可行：CLI → Action → API → Enterprise |
| **最大护城河** | eval 体系（数据壁垒）+ 协议标准（网络效应） |
| **v0 就绪度** | 33 fixture eval 9/9 通过，0.1.0a1 已发布；下一步是 dogfood 与发布 smoke |

### 三层价值定位

```
第 1 层（v0）：AI 代码的独立审计
  → "AI 写的代码谁来审？"
  → 有竞品但都缺 isolation + 确定性判定

第 2 层（v1）：全制品的独立审查
  → "AI 写的设计/方案/分析谁来审？"
  → 无直接竞品（蓝海）

第 3 层（v2）：AI 编程时代的质量基础设施
  → "整个 AI 辅助开发流程的可信度？"
  → ReviewPack / ReviewResult 协议可能成为行业标准
```
