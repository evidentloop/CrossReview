# CrossReview

> Independent verification through context isolation, not model diversity.

CrossReview 是一个 **验证型 incubator**：把手工 fresh-session cross-review 流程协议化、自动化。

## 核心假设

同一模型新开 session（无生产过程上下文）就能发现问题——价值来源是 **context isolation**，不是 model diversity。

## v0 范围

```
crossreview pack    # 打包 code diff → ReviewPack JSON
crossreview verify  # pack + fresh review → structured findings + advisory verdict
```

- **code_diff only** — 不支持 plan/design/custom artifact
- **advisory only** — verdict 只是建议，不做 block
- **single reviewer** — fresh_llm_reviewer（context-isolated session）
- **deterministic adjudicator** — 基于规则引擎，不涉及 LLM

详细 scope → [docs/v0-scope.md](docs/v0-scope.md)

## 当前阶段：Prompt Lab

在搭建完整工程框架前，先验证核心假设：

1. 准备 3-5 个真实 diff fixture
2. 手工组装 ReviewPack
3. 用固定 prompt 调 LLM → 保存 raw output
4. 人工 adjudication → 回答三个问题：
   - 模型能否稳定给出真问题？
   - 需要哪些 context？
   - 噪音来自 prompt 还是 pack 缺失？

**如果 prompt lab 结果不行，后面的 schema / adjudicator / CLI 都是在包装失败。**

详见 → [prompt-lab/README.md](prompt-lab/README.md)

## 非目标（v0 明确不做）

- ❌ Python SDK（v1）
- ❌ MCP Server（v1+）
- ❌ Agent Skill
- ❌ CI/CD GitHub Action
- ❌ Sopify adapter / review.md 资产面
- ❌ cross_model_reviewer / skill_guided_reviewer
- ❌ verdict = block

## Release Gate

v0 发布需通过 [8 项 blocking release gates](docs/v0-scope.md)（见 §12），包括：

- manual_recall ≥ 0.80
- precision ≥ 0.70
- fixture_count ≥ 20

不满足 → 退回为 prompt pattern，不做独立产品化。

## Roadmap

v0 release gate 通过后再规划 v1（stable SDK / MCP / cross-model / 反馈闭环）。

## License

MIT
