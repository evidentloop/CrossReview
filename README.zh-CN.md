# CrossReview

[English](README.md) | 简体中文

> AI 编码助手的自动化交叉审查 —— 用全新的隔离 LLM session 验证助手的产出。

## 什么是交叉审查？

在人工代码评审中，变更通常由**未直接参与实现的人**复核，以降低作者偏见。CrossReview 将这一原则应用到 AI 生成代码：把“生成”与“复核”拆到两个相互隔离的上下文中完成。

AI 编码助手（Claude、Copilot、Cursor 等）先在其原始会话中完成实现。随后，CrossReview 将 diff、意图、focus 区域和可选上下文组装成 `ReviewPack`，交给一个**独立的 reviewer session** 做二次审查。该 reviewer 不继承原始对话、推理轨迹或工具历史，只基于最小必要输入判断这次变更是否存在问题。

核心洞察：**你不需要换一个模型，只需要换一个上下文。** 同模型，干净 session，真实发现。

## 为什么有效

它依赖的不是模型多样性，而是**输入隔离**。

原始实现会话会累积大量局部假设、试错过程、放弃的方案和工具调用痕迹。如果复核阶段沿用这些上下文，reviewer 很容易继承作者视角，而不是重新独立判断这次改动是否正确。

CrossReview 通过把 reviewer 输入限制在复核工件本身来避免这个问题：

| Reviewer 能拿到 | Reviewer 拿不到 |
|-----------------|----------------|
| Diff / changed files | 原始对话 |
| 声明的意图 | 规划或推理轨迹 |
| 重点区域 | 工具调用历史 |
| 可选 context files | 重试记录、失败尝试、中间草稿 |

这种拆分带来两个直接效果：

- 提高复核独立性：第二次审查必须基于工件本身给出判断，而不是复用原始会话状态。
- 提高可审计性：reviewer 的结论可以回落到 `ReviewPack` 输入、结构化 findings 和确定性 normalizer 规则上验证。

## 评测结果

33 个 fixture 完整评测（claude-opus-4.6，external_only scope）：

| 指标 | 值 | Gate |
|------|-----|------|
| 精确率 | 0.885 | ≥ 0.70 ✅ |
| 召回率 | 0.929 | ≥ 0.80 ✅ |
| Unclear rate | 0.133 | ≤ 0.150 ✅ |
| 每次运行无效发现数 | 1 | ≤ 2 ✅ |

**9 项 release gate 全部通过** — `blocking_pass: true`。完整 gate 定义见 [v0-scope.md §12](docs/v0-scope.md)。

## 快速开始

```bash
pip install crossreview              # 从 PyPI 安装（v0.1.0a1+）
pip install -e .                     # 本地开发（包含 pack + verify 命令）
pip install -e '.[anthropic]'        # 加 Anthropic standalone reviewer 后端

# 通过 flags、crossreview.yaml 或环境变量配置 standalone verify
# 示例：
#   export CROSSREVIEW_PROVIDER=anthropic
#   export CROSSREVIEW_MODEL=claude-sonnet-4-20250514
#   export CROSSREVIEW_API_KEY_ENV=ANTHROPIC_API_KEY
#   export ANTHROPIC_API_KEY=...

crossreview pack --diff HEAD~1 --intent "fix auth token refresh" > pack.json
crossreview verify --pack pack.json
```

或一步完成：

```bash
crossreview verify --diff HEAD~1 --intent "fix auth token refresh"
```

`crossreview verify --diff` 默认输出终端可读格式。`crossreview verify --pack` 默认输出 `ReviewResult` JSON，或用 `--format human` 获得终端可读格式：

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
      "summary": "Token refresh 在 refresh_token 过期时静默成功",
      "detail": "第 42 行的 try/except 捕获了 TokenExpiredError 但返回旧 token，而不是抛出异常。",
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
    "failure_reason": null
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

## 架构

```
         git diff + intent + focus + context
                      │
                      ▼
              ┌────────────────┐
              │      Pack      │  组装 ReviewPack
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Budget Gate   │  按重点排序，截断过大输入
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
              │  Normalizer    │  从文本提取结构化发现
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │  Adjudicator   │  应用规则 → 建议性判定
              └───────┬────────┘
                      │
                      ▼
              ┌────────────────┐
              │ ReviewResult   │  发现 + 判定 + 质量指标
              │ (JSON)         │
              └────────────────┘
```

> **Isolation Boundary（隔离边界）**：Reviewer 在全新 session 中运行，零共享上下文。

只有 Reviewer 调用 LLM，其余全部基于规则 —— 没有 AI 参与。

## 安装

```bash
pip install crossreview              # 从 PyPI 安装（v0.1.0a1+）
pip install -e .                     # 本地开发（包含 pack + verify 命令）
pip install -e '.[anthropic]'        # 加 Anthropic standalone reviewer 后端
pip install -e '.[dev]'              # 开发依赖（pytest + ruff）
```

Reviewer 后端有两种模式：

| 模式 | 说明 | 依赖 |
|------|------|------|
| **Host-integrated** *（CLI 已实现）* | 宿主在隔离上下文（新会话 / sub-agent）中渲染 reviewer prompt，再通过 `render-prompt + ingest` 流程把原始分析文本回传给 normalizer + adjudicator | CrossReview 侧无额外 SDK |
| **Standalone** *（已实现）* | CLI 直接调 LLM API | `crossreview[anthropic]` + reviewer config + API key |

Host-integrated 是计划中的默认产品路径。宿主不需要实现 Python `ReviewerBackend`；集成方式是 `render-prompt + ingest`，由宿主负责在 fresh context 中执行 canonical prompt，再把原始分析文本回传。

## 命令

### `crossreview pack`

```bash
crossreview pack --diff HEAD~1 > pack.json
crossreview pack --diff main..feat --intent "add caching" --focus cache --context ./plan.md > pack.json
```

| 参数 | 说明 |
|------|------|
| `--diff REF` | Git ref（`HEAD~1`）或范围（`main..feat`） |
| `--intent TEXT` | 任务意图（背景声明，非真相） |
| `--task FILE` | 完整任务描述文件 |
| `--focus TERM` | 重点审查区域（可重复） |
| `--context FILE` | 额外 context 文件（可重复） |

### `crossreview verify`

两种模式：`--pack`（验证已有 ReviewPack）或 `--diff`（一站式：打包 + 审查）。

```bash
# 一站式：打包 + 审查，默认 human 格式输出
crossreview verify --diff HEAD~1
crossreview verify --diff HEAD~1 --intent "修复 auth" --focus auth

# 验证已有 pack，默认 JSON 格式输出
crossreview verify --pack pack.json
crossreview verify --pack pack.json --model claude-sonnet-4-20250514 --provider anthropic
```

`crossreview verify` 要求 reviewer 配置能成功解析，来源可以是：

- `--model / --provider / --api-key-env`
- 或 `crossreview.yaml`
- 或 `~/.crossreview/config.yaml`
- 或 `CROSSREVIEW_MODEL / CROSSREVIEW_PROVIDER / CROSSREVIEW_API_KEY_ENV`

| 参数 | 说明 |
|------|------|
| `--diff REF` | git diff 基准（如 `HEAD~1`、`main..feat`）。内联组装 ReviewPack，与 `--pack` 互斥 |
| `--pack FILE` | ReviewPack JSON 文件路径，与 `--diff` 互斥 |
| `--intent TEXT` | 任务意图（--diff 模式） |
| `--task FILE` | 任务描述文件（--diff 模式） |
| `--focus TERM` | 重点审查区域，可重复（--diff 模式） |
| `--context FILE` | 额外 context 文件，可重复（--diff 模式） |
| `--format FORMAT` | 输出格式。`--diff` 默认 `human`，`--pack` 默认 `json` |
| `--model TEXT` | 覆盖 reviewer 模型 |
| `--provider TEXT` | 覆盖 provider（当前仅 `anthropic`） |
| `--api-key-env VAR` | 覆盖 API key 环境变量名 |

### `crossreview render-prompt`

```bash
crossreview render-prompt --pack pack.json > prompt.md
crossreview render-prompt --pack pack.json --template custom-template.md > prompt.md
```

将 ReviewPack 渲染为完整的 canonical reviewer prompt，供宿主在隔离上下文中直接喂给 LLM。不调用 LLM，不需要 API key。

| 参数 | 说明 |
|------|------|
| `--pack FILE` | ReviewPack JSON 文件路径 |
| `--template FILE` | 自定义 prompt 模板（缺省：内置 product/v0.1） |

### `crossreview ingest`

```bash
crossreview ingest --raw-analysis raw.md --pack pack.json --model claude-sonnet-4-20250514
crossreview ingest --raw-analysis - --pack pack.json --model host_unknown --prompt-source product --prompt-version v0.1
```

接收宿主在隔离上下文中执行后的 raw analysis 文本，经 normalizer + adjudicator 生成标准 ReviewResult。默认输出 JSON；用 `--format human` 获得终端可读格式。不调用 LLM，不需要 API key。

| 参数 | 说明 |
|------|------|
| `--raw-analysis FILE` | raw analysis 文件路径；`-` 读 stdin |
| `--pack FILE` | 原始 ReviewPack JSON |
| `--model TEXT` | 宿主使用的模型名（不知道时传 `host_unknown`） |
| `--format FORMAT` | 输出格式：`json`（默认）或 `human` |
| `--prompt-source TEXT` | prompt 来源标识（可选） |
| `--prompt-version TEXT` | prompt 版本标识（可选） |
| `--latency-sec FLOAT` | 宿主侧 LLM 调用耗时（可选） |
| `--input-tokens INT` | 宿主侧 input token 计数（可选） |
| `--output-tokens INT` | 宿主侧 output token 计数（可选） |

### 退出码

所有命令在成功产出 `ReviewResult` 时返回 **0**，无论 `review_status` 或 `advisory_verdict` 是什么。非零退出码表示命令未能产出结果（输入无效、缺 API key、空 diff 等）。

自动化场景请检查 JSON 输出中的 `review_status` 和 `advisory_verdict`，不要仅凭退出码判断 review 是否通过：

```bash
crossreview verify --diff HEAD~1 --format json | jq -e '.advisory_verdict.verdict == "pass_candidate"'
```

## 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| Schema | ✅ 完成 | ReviewPack / Finding / ReviewResult / Config |
| Pack CLI | ✅ 完成 | `crossreview pack` |
| Budget Gate | ✅ 完成 | focus 优先 + soft/hard 截断 |
| Reviewer | ✅ 完成 | ReviewerBackend 接口 + Anthropic standalone |
| Normalizer | ✅ 完成 | 基于规则的结构化发现提取 |
| Adjudicator | ✅ 完成 | 基于规则的建议性判定 |
| Verify CLI | ✅ 完成 | `crossreview verify --pack` |
| Render Prompt CLI | ✅ 完成 | `crossreview render-prompt --pack`（host-integrated 前半段） |
| Ingest CLI | ✅ 完成 | `crossreview ingest --raw-analysis --pack --model`（host-integrated 后半段） |
| Evidence Collector | 🔜 待做 | ReviewPack.evidence 通路已有，空 evidence 可正常运行 |
| Eval Harness | ✅ 完成 | 33 fixtures，9/9 gate 通过，`blocking_pass: true` |
| 可读输出 | ✅ 完成 | verify/ingest 支持 `--format human` |
| 一站式 Verify | ✅ 完成 | `crossreview verify --diff`（一步完成 pack + review，默认 `--format human`） |

## v0 边界

**当前支持**: 仅 `code_diff` artifact · advisory verdict · 单 reviewer（`fresh_llm`） · 确定性 adjudicator 和 normalizer（不做 LLM fallback）

**明确不做（v0）**: Python SDK · MCP Server · CI/CD Action · Agent Skill runtime 模式（advisory SKILL.md 已提供；runtime bridge 推迟） · cross-model reviewer · verdict = block

**Release gate**: v0 需通过 [9 项 blocking 指标](docs/v0-scope.md)（§12），包括 manual_recall ≥ 0.80、precision ≥ 0.70、fixture_count ≥ 20、invalid_findings_per_run ≤ 2 等。当前 9 项全部通过（`blocking_pass: true`）。

## 许可

MIT
