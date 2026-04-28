# CrossReview — 长期路线

1. **Phase 0.5: Prompt Lab** — 验证核心假设 ✅
2. **Phase 1: v0 CLI** — crossreview pack + verify，通过 release gate ✅
3. **v0 Dogfood** — 日常使用 2 周+，收集反馈
4. **v0.5: Evidence + Loop** — `--evidence-cmd` 收集 lint/test 结果 → `--loop` 置信度驱动验证循环
5. **v1: Multi-artifact + SDK** — ArtifactType 扩展（design_doc / plan）+ stable Python SDK + cross-model
6. **v1+: 平台集成** — MCP Server / CI Action / 反馈闭环

### 优先级排序

| 优先级 | 任务 | 前置条件 | 阶段 |
|--------|------|---------|------|
| P0 | v0 CLI dogfood 2 周+ | v0 release gate ✅ | 当前 |
| P0 | CI/CD: GitHub Actions (test + lint on PR, PyPI auto-publish on tag) | — | 基建 |
| P0 | README badges (PyPI version, tests, license, Python version) | CI/CD | 基建 |
| P0.5 | Evidence collector (`--evidence-cmd`) | v0 dogfood | v0.5 |
| P1 | CONTRIBUTING.md (三级贡献模型: Fix/Enhancement/Feature) | — | 基建 |
| P1 | README 语言选择器 (顶部 English \| 中文) | — | 基建 |
| P1 | Loop mode + stop policy | evidence collector | v0.5 |
| P1 | Multi-artifact schema 扩展 | v0 dogfood + plan eval baseline | v1 |
| P2 | Quick Start 补 API key 步骤 + Troubleshooting 段 | — | 文档 |
| P2 | README collapsible install paths (`<details>`) | — | 文档 |
| P2 | history_log + circuit_breaker | loop mode | v1 |
| P2 | Cross-model reviewer | v0 dogfood | v1 |
| P3 | Founder voice section ("Why I Built This") | v0.5+ | 文档 |
| P3 | MCP Server / CI Action | stable SDK | v1+ |

### 关键决策

| # | 决策 | 内容 |
|---|------|------|
| D-CR1 | Verify Loop 不独立建项目 | 核心抽象与 CrossReview 高度重合（6/7 概念对应）；stop_policy / rubric / multi-artifact 等好想法吸收进 CrossReview |
| D-CR2 | Loop mode 内置 CrossReview | `--loop` 作为 CLI flag，不依赖外部 orchestrator——符合 standalone-first；宿主可选调用但非必须 |
| D-CR3 | Stop policy: hardcoded 默认 + 可覆写 | 默认规则链（质量达标 → 人工介入 → 无进展 → 信号衰减 → 兜底）；power user 可通过 crossreview.yaml 调整阈值 |

详见当前执行计划 → `.sopify-skills/plan/20260420_crossreview_v0_prompt_lab/`
