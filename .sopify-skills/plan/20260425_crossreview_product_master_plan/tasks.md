# CrossReview 产品总纲 — 任务拆分

> **执行原则**：先验证核心假设（context isolation + 确定性判定在 code_diff 上可行），再扩展通道和制品类型。
> **Sopify 协同**：CR v0 release gate → Sopify Phase 4a advisory → 3 项目 dogfood → 数据驱动后续。
> **最近同步**：2026-04-28 — v0.1.0a1 已发布，9/9 release gate 通过，当前聚焦发布 smoke + Phase 4a dogfood 准备。

## 三阶段执行路线

| 阶段 | 内容 | 时间窗口 |
|------|------|---------|
| **阶段 1 — 验证就绪** | v0-04a→v0-07 → PyPI 0.1.0a1 | ✅ 已完成 |
| **阶段 2 — 价值验证** | 发布 smoke + Sopify Phase 4a advisory + 3 项目 dogfood | 当前聚焦 |
| **阶段 3 — 数据驱动** | 数据好 → GitHub Action；数据一般 → 退回 prompt pattern | dogfood 数据后 |

最小判定口径：≥3 个真实项目、≥2 个 valid issue、误报不阻塞主流程、完整流程 ≤1 次手工修正。

---

## 当前状态

> v0 目标已完成：code_diff 通过 9 指标 release gate，CLI / host-integrated 基础命令已发布为 0.1.0a1。

| ID | 任务 | 优先级 | 依赖 | 状态 |
|----|------|--------|------|------|
| v0-02 | 20 fixture 收集与人工标注 | P0 | - | ✅ 完成 |
| v0-03 | eval harness 完整实现 | P0 | v0-02 | ✅ 完成 |
| v0-04a | unclear_rate 修复 | P0 | v0-02, v0-03 | ✅ 完成 (0.133 ≤ 0.150) |
| v0-04b | 全量 release gate 重跑 | P0 | v0-04a | ✅ 完成 (33 fixtures, 9/9) |
| v0-05 | human-readable output (`--format human`) | P0 | - | ✅ 完成 |
| v0-06 | one-stop verify (`crossreview verify --diff`) | P0 | - | ✅ 完成 |
| v0-07 | v0 发布就绪判定 | P0 | v0-04b, v0-05, v0-06 | ✅ 完成 |
| v05-01a | PyPI alpha 发布 (crossreview 0.1.0a1) | P0 | v0-07 | ✅ 完成 |
| v05-02a | CrossReview advisory SKILL.md + skill.yaml 草拟 | P0 | v0-07 | ✅ 完成（仓库内 `.agents/skills/cross-review/`） |

**v0 退出条件**：已满足。当前不再阻塞在 unclear_rate / release gate / CLI 形态上；后续重点转为发布 smoke、Sopify 侧消费与 dogfood 数据。

---

## 当前活跃

**v0.5: 发布核对 + 生态集成 + dogfood** `触发：v0-07 release gate 通过，0.1.0a1 已发布`

> 表内 P0/P1/P2 是 CR v0.5 版本内优先级；跨项目排序以生态总纲为准。

| ID | 任务 | 优先级 | 依赖 | 状态 |
|----|------|--------|------|------|
| v05-01b | 发布 smoke：PyPI 元数据 / clean env install / CLI smoke / tag 对齐 | P0 | v05-01a | 当前 |
| v05-02b | Sopify Phase 4a 消费侧草拟：迁移或复用 advisory SKILL.md + skill.yaml | P0 | v05-01b | 待 |
| v05-03 | Phase 4a 端到端验证: develop → `verify --diff --format human` → 结果展示 | P0 | v05-01b, v05-02b, v05-04 | 待 |
| v05-04 | SKILL.md verdict 处理指令（4 种 verdict） | P0 | v05-02a | ✅ 仓库内草拟完成，待 dogfood 校验 |
| v05-05 | 技术文章 #1：产品定位与核心洞察 | P1 | v0-07 | 待 |
| v05-06 | 技术文章 #2：eval 体系与质量承诺 | P2 | v0-04b | 待 |
| v05-07 | fixture 持续扩充（目标 50） | P1 | v0-02 | 待 |
| v05-08 | README 更新（公开 eval 结果 + 质量承诺） | P1 | v0-04b | ✅ 当前 README 已覆盖 0.1.0a1，后续随补丁维护 |

**v0-01: Evidence Collector** `延后至 v0.5+，不阻塞 release gate`

---

## 延后 (数据驱动后决策)

> 版本内的 P0/P1/P2 只表示启动后的内部优先级，不进入 0-6 个月执行队列。

| 方向 | 内容摘要 | 启动条件 | 任务 ID 范围 |
|------|---------|---------|------------|
| v1 核心能力 | design_doc + plan artifact type、路由机制 | v0.5 稳定 + dogfood 数据 | v1-01~09 |
| v1 产品通道 | GitHub Action (P0 优先) → MCP → SDK | v0.5 稳定 | v1-10~16 |
| v1 质量增强 | Eval dashboard + fixture 扩充至 100 | v1 核心启动后 | v1-17~18 |

### 冻结

**v1 Sopify 4b: Runtime 模式** `🧊 冻结，不进入 0-6 个月承诺`
- bridge.py + pipeline_hooks + verdict→checkpoint 映射 (v1-19~23)
- 启动条件：Sopify Phase 3 就绪 + Phase 4a 价值验证 + 3 个 dogfood 数据

---

## Vision only

> 不进入 0-6 个月执行计划。保留方向，不展开任务。

| 版本 | 方向 | 触发条件 | 任务 ID 范围 |
|------|------|---------|------------|
| v1.5 | 商业化：Hosted API + 企业 policy engine + 定价 | release gate + Action 采纳 + 企业询盘。触发前 MIT 全免费 | v15-01~07 |
| v2 | 质量基础设施：全链路审查编排 + 合规报告 + 协议标准化 | v1.5 稳定 | v2-01~08 |

---

## 依赖与里程碑

```
v0-04a → v0-04b → v0-05/v0-06 → v0-07 → PyPI 0.1.0a1
                                               │
                                               ↓
                                     v05-01b 发布 smoke
                                               │
                              ┌────────────────┴───────────────┐
                              ↓                                ↓
                 v05-02b/v05-04 Phase 4a             v05-05/v05-06 文章
                              │
                              ↓
                       3 项目 dogfood
                              │
                       数据驱动决策
                     ┌────────┴────────┐
                     ↓                 ↓
           Action (v1-10~12)    退回 prompt pattern
```

**Sopify 交叉依赖：**

```
CR v0 release gate 通过 ──→ Sopify Phase 4a (advisory SKILL.md)
Sopify Phase 4a dogfood 数据 ──→ 决定是否启动 Sopify Phase 1-3
Sopify Phase 3 就绪 ──→ CrossReview v1 Sopify 4b (runtime, 🧊 冻结，不进入 0-6 个月承诺)
```

> **Source of Truth (2026-04-28)**：CR 产品方向、eval 体系、release gate、通道设计以本文档（CR 总纲）为准；已发布事实以 README / CHANGELOG / git tag / PyPI 为校验依据。Sopify 侧设计以 Sopify 总纲为准。跨项目排序和依赖图以生态总纲为准。
> **Phase 4a scope 确认 (2026-04-26)**：advisory only（SKILL.md + skill.yaml + `verify --diff --format human`），无 bridge.py / pipeline_hooks。Phase 4a scope 三份总纲已对齐。

| 里程碑 | 关键交付 | 判定标准 |
|--------|---------|---------|
| **M0: v0 Release Gate** | 9 指标全部达标 | ✅ release gate 通过 |
| **M1: 首次发布** | PyPI 0.1.0a1 + advisory 插件草稿 | ✅ 可安装待 smoke 复核 + LLM 自主调用 CLI |
| **M1.5: Dogfood** | 3 项目 Phase 4a advisory 数据 | ≥2 valid issue，误报不阻塞，完整流程 ≤1 次手工修正 |
| M2: GitHub Action | Marketplace 上架 | 真实 PR 触发 + inline comment |
| M3~M6 | 全制品 / MCP / 商业化 / 协议标准 | 详见 design.md |
