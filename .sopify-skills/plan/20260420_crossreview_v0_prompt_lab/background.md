# CrossReview v0 Prompt Lab + Phase 1 — 背景

## 目标

验证 "fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding"，如果成立则实现 v0 CLI。

## 上游 Scope

产品范围定义来自 [docs/v0-scope.md](../../../docs/v0-scope.md)（canonical，Status: Confirmed）。

## 当前阶段

**Phase 0.5 — Prompt Lab**

在搭建完整工程框架前，先用 3-5 个真实 diff 验证 reviewer prompt 质量。如果 raw output 质量不行，后面的 schema / adjudicator / CLI 都是在包装失败。

## Gate

Prompt Lab 通过（模型能稳定给出真问题 + 噪音来源可控）→ 进入 Phase 1。

## 非目标

本 plan 不涉及：

- SDK / MCP Server / Agent Skill / CI/CD Action
- Sopify adapter / review.md 资产面
- cross_model_reviewer / skill_guided_reviewer
- verdict = block
- 三层产品线落地（CrossReview > sopify-code-review > Sopify）
