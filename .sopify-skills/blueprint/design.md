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

### 当前架构约束补充

> 来源：`plan/20260425_crossreview_product_master_plan/design.md`。以下为结论性原则摘要。

**Release gate 体系：** 9 指标阈值验证（manual_recall、precision、invalid_findings_per_run、max_invalid_single_run、unclear_rate、context_fidelity、actionability、failure_rate、fixture_count）。此外 `self_hosting_pool_limit_ok`（self_hosting 比例 ≤ 25%）作为 fixture 池组成约束参与 `blocking_pass` 判定。当前唯一 blocker：unclear_rate (0.200 > 0.150 阈值)。指标不满足时退回 prompt pattern，不做产品发布。

**ReviewPack / ReviewResult 协议：** v0 scope = code_diff；v1 预留 design_doc / plan artifact。ReviewPack 是标准化输入契约，ReviewResult 是标准化输出契约，两者构成 CrossReview 的核心协议。

**Sopify 集成约束（对齐 Sopify ADR-012/014）：**
- Phase 4a (advisory)：LLM 读取 SKILL.md 后自主调用 CrossReview CLI，不改 runtime state
- Phase 4b (runtime)：bridge.py 产出 review_result + checkpoint proposal → Sopify Core validates → Core materializes checkpoint
- CrossReview bridge 只能 propose checkpoint，不能直接写入 Sopify state
- Pipeline hook 检查由 Sopify Plugin Runtime / Core validation layer 负责，不由 engine 硬编码

### Repo / 组织策略补充

CrossReview 的长期推荐形态是：

| 维度 | 口径 |
|------|------|
| 仓库归属 | 迁往 `evidentloop` 同 org 下的独立 repo |
| 当前阶段 | 在个人仓库继续 incubate，直到 v0 gate 与发布路径稳定 |
| 产品叙事 | 独立 verifier，不是 Sopify 私有模块 |
| 宿主关系 | Sopify 是 first deep host，不是 exclusive host |
| contract 约束 | ReviewPack / ReviewResult 不引入 Sopify 内部状态词 |

当前不建议因此单独优化 org 名。只要 sibling repo 保持 standalone-first，`evidentloop` 不会自动把 CrossReview 锁定为 Sopify-only 产品；是否需要更中性的 umbrella org，应在出现明确外部 adoption / 品牌信号后再评估。
