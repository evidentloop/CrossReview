# CrossReview — 技术约束

## 核心管道

```
ReviewPack → fresh_llm_reviewer → FindingNormalizer → Adjudicator → ReviewResult
```

注：`fresh_llm_reviewer` 是逻辑角色，不等同于固定 provider backend。其实现可来自 host-integrated fresh session，也可来自 standalone provider backend。

## 已确定的架构约束

1. **两段式审查** — reviewer 输出自由分析文本，FindingNormalizer 提取结构化 Finding。不强迫模型直接输出 JSON schema。
2. **Advisory only（v0）** — verdict 只是建议（pass_candidate / concerns / needs_human_triage / inconclusive），不做 block。
3. **code_diff only（v0）** — v0 只接受代码 diff artifact。
4. **Deterministic adjudicator** — 基于规则引擎，不涉及 LLM。
5. **Pack bias 意识** — reviewer prompt 将 intent/focus/task 视为"待验证背景声明"，raw diff 为优先证据。
6. **Core 不选择模型** — core 接收 resolved ReviewerConfig，不内置默认供应商或模型。
7. **Default review path is host-integrated same-model fresh session** — 当宿主提供 fresh-session reviewer backend 时，优先复用宿主当前模型做隔离审查；standalone provider backend 仅为 fallback / portable mode。

## 数据隔离

**Fixture 数据存放在 `eval-data` 分支**，不在 `main` 分支。

- 原因：fixture 包含其他项目（hermes-agent, helloagents, graphify, ai-daily-brief）的真实 diff 和方案包数据
- `main` 保持工具代码纯净，后续如需公开发布不含第三方项目数据
- 若需更严格隔离，从 `eval-data` 分支拆为独立 private repo

### Plan artifact 验证（v1+ 预留）

- `eval-data` 分支 `fixtures/plan-preview/` 存放 plan artifact 的预备 case
- v0 scope 锁定 code_diff，plan 验证的 prompt/eval/约束放松在 v1+ 实现
- 第一个 case：`plan-preview/001-feishu-webhook`（来自 ai-daily-brief 飞书推送方案）

## Schema

详见 [docs/v0-scope.md §7](../../docs/v0-scope.md)。

## 更多设计

当前处于 Prompt Lab 阶段。更多设计细节在验证核心假设后补充。
