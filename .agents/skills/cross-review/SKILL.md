---
name: cross-review
description: >-
  在开发完成后自动交叉评审代码变更。审查者运行在隔离的 LLM 会话中，
  不继承开发上下文，发现偏差和盲点。Advisory 模式：结论仅供参考，不自动阻断。
---

## 何时触发

在 develop 阶段完成、代码已写入磁盘后触发。不要在规划阶段或未产生代码变更时触发。

前置条件：
- 工作区存在未评审的代码变更（`git diff` 非空）
- `crossreview` CLI 已安装（`pip install crossreview` 或 `pip install -e .`）
- Reviewer API key 已配置（环境变量 `ANTHROPIC_API_KEY`，或 `crossreview.yaml` 中设置）

## 默认流程（One-Stop）

### Step 1 — 确定 diff 基准

[IF 任务涉及多次提交]
  REF = HEAD~{提交数}
[ELSE]
  REF = HEAD~1

验证：`git diff <REF>..HEAD` 输出非空。若为空则跳过评审。

### Step 2 — 执行评审

```bash
crossreview verify --diff <REF> --format human
```

可选参数（按需添加）：
- `--intent "任务意图摘要"` — 帮助审查者理解变更目标
- `--task ./task.md` — 任务描述文件
- `--context ./plan.md` — 额外上下文文件（可重复）
- `--focus <area>` — 聚焦区域（可重复）

完整示例：
```bash
crossreview verify --diff HEAD~1 \
  --intent "修复用户认证逻辑" \
  --task ./task.md \
  --context ./plan.md \
  --format human
```

### Step 3 — 读取输出

命令成功时（exit code 0），输出格式为：

```
CrossReview 0.1-alpha | artifact: <hash> | review_status: <status>

Intent: <intent>
Intent Coverage: covered/partial/unknown
Pack Completeness: 0.XX

Findings (N):
  [HIGH]  file.py:42 — 发现摘要
  [MED]   other.py — 另一个发现

Advisory Verdict: <verdict>
  Rationale: <理由>
```

关键字段：
- `review_status` — `complete` / `rejected` / `failed`
- `Advisory Verdict` — 见 Step 4 分支

### Step 4 — 根据 verdict 分支处理

[IF review_status != "complete"]
  [ACTION: LOG_WARNING] 记录非正常状态（rejected / failed），继续主流程，不阻断。
  [SKIP] 不进入以下 verdict 分支。

[IF Advisory Verdict == "pass_candidate"]
  [ACTION: CONTINUE]
  告知用户：评审未发现问题，代码可以继续推进。

[IF Advisory Verdict == "concerns"]
  [ACTION: SHOW_FINDINGS] 向用户展示所有 findings（按严重度排列）。
  [ACTION: ASK_USER] "评审发现以下问题：\n{findings}\n(A) 修改代码后重新评审 (B) 接受并继续 (C) 忽略"
  - 用户选 A → 修改代码，回到 Step 1 重新执行
  - 用户选 B 或 C → 继续主流程

[IF Advisory Verdict == "needs_human_triage"]
  [ACTION: SHOW_FINDINGS] 展示所有 findings。
  [ACTION: REQUEST_HUMAN] "评审发现需要人工判断的复杂问题，请审阅后决定。"
  等待用户明确指令后再继续。

[IF Advisory Verdict == "inconclusive"]
  [ACTION: LOG_WARNING] "评审结果不确定，可能由于上下文不足或模型限制。"
  继续主流程，不阻断。

## 备用流程（Pack 模式）

仅在 `verify --diff` 失败时使用（如 git 不可用、diff 过大）：

```bash
crossreview pack --diff <REF> --intent "任务摘要" > pack.json
crossreview verify --pack pack.json --format human
```

verdict 处理同 Step 4。

## 重要约束

- **Exit code 0 = 结果已产出**，不代表评审通过。必须读 `Advisory Verdict` 行判断。
- **Exit code 非零 = 命令执行失败**，无评审结果。记录错误，继续主流程。
- **Advisory 模式：verdict 仅供参考，不自动阻断任何流程。**
- 不要在无代码变更时运行（浪费 token）。
- `--format human` 用于终端展示，`--format json` 用于程序解析。

## 交付检查

- [ ] crossreview 命令成功执行（exit code 0）
- [ ] Advisory Verdict 已读取并展示给用户
- [ ] concerns / needs_human_triage 时用户已被告知并做出决定
- [ ] 结果不阻断主流程（advisory only）
