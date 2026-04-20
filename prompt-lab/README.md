# Prompt Lab

验证核心假设：fresh LLM reviewer 能否从 ReviewPack 中稳定产出真 finding。

## 为什么在工程实现前做这一步

CrossReview 的全部价值取决于"给模型一个 ReviewPack，它能输出多少真 finding"。如果 raw output 质量不行，schema / adjudicator / formatter 都是在包装失败。

## 怎么跑

```bash
# 1. 在 cases/ 下创建新 case 目录
mkdir cases/001-auth-refresh

# 2. 准备 diff 和 pack
#    - diff.patch: 真实 git diff
#    - pack.json: 手工/半手写 ReviewPack（格式见下方）
#    - manual-findings.yaml: 手工 cross-review 发现的问题（gold baseline）

# 3a. 有 LLM client 实现时：直接运行
python run.py cases/001-auth-refresh

# 3b. 无 LLM client 时：渲染 prompt → 手动粘贴给模型
python run.py --render-only cases/001-auth-refresh
# → 生成 cases/001-auth-refresh/rendered-prompt.md
# → 粘贴到 Claude/ChatGPT session，保存 output 到 raw-output.md

# 4. 查看 raw output → cases/001-auth-refresh/raw-output.md

# 5. 人工 adjudication → 编辑 cases/001-auth-refresh/adjudication.yaml
```

## ReviewPack 手写格式

```json
{
  "artifact_type": "code_diff",
  "diff": "<unified diff text>",
  "changed_files": ["src/auth/token.ts", "src/auth/types.ts"],
  "intent": "修复 token refresh 过期判断",
  "focus": ["auth"],
  "context_files": [],
  "evidence": []
}
```

## Adjudication 记录格式

```yaml
fixture_id: "001-auth-refresh"
adjudicated_at: "2026-04-20T16:00:00+08:00"
model: "claude-sonnet-4-20250514"
latency_sec: 45.2
input_tokens: 3200
output_tokens: 1800

findings:
  - auto_finding_id: "f-001"
    judgment: valid        # valid | invalid | unclear
    matched_manual_id: "mf-001"  # 匹配手工 baseline 的哪条 finding
    actionability_judgment: actionable  # actionable | not_actionable | unclear
    notes: ""

  - auto_finding_id: "f-002"
    judgment: invalid
    matched_manual_id: null
    actionability_judgment: not_actionable
    notes: "模型编造了一个不存在的竞态条件"

summary:
  valid_count: 1
  invalid_count: 1
  unclear_count: 0
  observations: "模型在 auth 逻辑上能发现真问题，但容易在并发场景编造 finding"
```

## 要回答的三个问题

完成 3-5 个 case 后，总结：

1. **模型是否能稳定给出真问题？** → valid rate 是否 > 50%
2. **需要哪些 context 才能给出真问题？** → 哪些 case 因为缺 context 导致 finding 质量差
3. **主要噪音来自 prompt 还是 pack 缺失？** → invalid finding 的根因分类

## Gate

Prompt Lab 通过 → 进入 Phase 1 正式实现。
Prompt Lab 不通过 → 调整 prompt / pack 策略重试，或存档方案等待模型能力提升。
