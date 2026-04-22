# Fixtures

v0 eval harness 使用的 diff fixture 集合。

## 格式

每个 fixture 是一个目录：

```
fixtures/
├── 001-auth-refresh/
│   ├── fixture.yaml            # fixture_id + pool (external|self_hosting)
│   ├── pack.json               # ReviewPack
│   ├── review-result.json      # 运行产出的 ReviewResult
│   ├── manual-findings.yaml    # 手工 cross-review baseline（recall denominator）
│   └── auto-adjudications.yaml # 对自动 finding 的人工判定（precision numerator）
└── 002-cache-layer/
    └── ...
```

`python -m crossreview_eval --fixtures ./fixtures/` 只消费上述 5 个文件，不负责触发 reviewer 调用。

## fixture.yaml 格式

```yaml
fixture_id: "001-auth-refresh"
pool: external           # external | self_hosting
```

## Manual Findings 格式

```yaml
fixture_id: "001-auth-refresh"
source: manual_fresh_session
reviewer_model: "claude-sonnet-4-20250514"
reviewed_at: "2026-04-20T16:00:00+08:00"

context_items:
  - type: diff
    path_or_desc: "src/auth/token.ts"
    required: true
    covered_by_pack: null    # eval 时人工标记

findings:
  - id: "mf-001"
    summary: "Token expiry off-by-one"
    file: "src/auth/token.ts"
    severity_estimate: high
```

## Auto Adjudications 格式

```yaml
fixture_id: "001-auth-refresh"
run_id: "run-20260421-001"
adjudicated_at: "2026-04-21T16:05:00+08:00"

findings:
  - auto_finding_id: "f-001"
    judgment: valid                 # valid | invalid | unclear
    matched_manual_id: "mf-001"     # recall 计算使用；可为 null
    actionability_judgment: actionable  # actionable | not_actionable | unclear
```

## Review Result

`review-result.json` 必须是 `crossreview verify` 产出的完整 `ReviewResult` JSON。

- eval harness 会从中读取 `review_status`
- 读取顶层 `raw_findings` 作为 eval 的自动 finding 集合
- 读取顶层 `findings` 作为 runtime 发给产品侧的 emitted findings
- 读取 `quality_metrics.raw_findings_count / emitted_findings_count / noise_count / speculative_ratio`
- 读取 `raw_findings[].locatability / confidence / evidence_related_file`
- 不会重新推断这些字段；`auto-adjudications.yaml` 也必须覆盖全部 `raw_findings`

## 分阶段目标

| 阶段 | 数量 | 目的 |
|------|------|------|
| Prompt Lab | 3-5 | 验证 prompt 质量 |
| Dev Milestone | 10 | 跑通 eval harness |
| Release Gate | ≥ 20 | v0 发布门槛 |

详见 [docs/v0-scope.md §4](../docs/v0-scope.md) 和 [§12](../docs/v0-scope.md)。

## Prompt Lab 与 Fixtures 的关系

- `prompt-lab/cases/` 是 Prompt Lab 当前使用的工作目录，采用 `--render-only` 渲染 prompt 后手动粘贴到模型会话
- `fixtures/` 是后续 eval harness 使用的正式 fixture 集合
- Prompt Lab 通过后，可把已验证的 case 迁移/复制到 `fixtures/`
- Prompt Lab 第一批 case 固定来自真实 commit，优先从 `cross-review/`、`helloagents/`、`hermes-agent/` 提取，且至少保留 1 个 clean diff
