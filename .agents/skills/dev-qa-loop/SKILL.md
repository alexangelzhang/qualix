---
name: "dev-qa-loop"
description: "逐任务实现 + 逐任务 review 的开发循环。当用户有多步实现任务、重构或 migration 时触发，确保每个 task 通过 review 后才推进下一个。"
---

# Dev-QA Loop

IRON LAW: 每个 task 必须通过 QA review 才能推进下一个。NEVER 批量实现后统一 review，NEVER 跳过失败 task 不带 feedback 重试。

---

## 触发条件

| 场景 | 信号 |
|------|------|
| 多步 feature 开发 | 有 plan 或 task list，包含 3+ 个实现步骤 |
| 重构 / migration | 需要分步改动，每步需验证不破坏现有功能 |
| 用户明确要求 | "用 dev-qa loop"、"逐步实现并验证" |

**不触发**：单文件修改、简单 bug fix、纯研究任务。

---

## 流程

### Phase 1: 建立 Task List

如果还没有 task list，先创建：

1. 分析需求，拆分为可独立验证的 task
2. 用 `TaskCreate` 逐个建立，设置依赖关系（`addBlockedBy`）
3. 每个 task 的 description 必须包含：
   - 要改什么（文件、函数、模块）
   - 完成标准（怎样算 PASS）
   - 验证方式（测试命令、检查点）

### Phase 2: Dev-QA 循环

对每个 task 执行：

```
┌─────────────┐
│  Task N      │
│  (pending)   │
└──────┬──────┘
       ▼
┌─────────────┐
│  实现        │  ← 标记 in_progress，写代码
└──────┬──────┘
       ▼
┌─────────────┐
│  自验证      │  ← 运行测试、lint、type check
└──────┬──────┘
       ▼
┌─────────────┐     FAIL (attempt < 3)
│  QA Review   │  ──────────────────────┐
│  (agent)     │                        │
└──────┬──────┘                        │
       │ PASS                          ▼
       ▼                     ┌─────────────┐
┌─────────────┐              │  修复        │
│  标记完成    │              │  (带 feedback)│
│  → 下一个    │              └──────┬──────┘
└─────────────┘                     │
                                    ▼
                              回到 QA Review
```

#### 实现阶段

1. `TaskUpdate` 标记当前 task 为 `in_progress`
2. 实现代码改动
3. 运行自验证：
   - 有测试的项目：跑相关测试
   - 有 lint/type check：跑一遍
   - 无自动化验证：手动检查改动点

#### QA Review 阶段

用 `pr-review-toolkit:code-reviewer` agent 做 review：

```
prompt: "Review the changes for task: [task subject].
Focus on: [task 的完成标准].
Check: correctness, no regressions, code quality."
```

#### 判定逻辑

| QA 结果 | 当前 attempt | 动作 |
|---------|-------------|------|
| PASS | any | 标记 completed，推进下一个 task |
| FAIL | < 3 | 带 review feedback 修复，重新提交 QA |
| FAIL | = 3 | 标记为 blocked，记录失败原因，跳到下一个 task |

**关键**：每次 retry 必须带上 QA 的具体 feedback，不能盲目重试。

### Phase 3: 集成验证

所有 task 完成后：

1. 运行完整测试套件（如果有）
2. 用 `superpowers:verification-before-completion` 做最终验证
3. 汇总报告：
   - 完成的 task 数 / 总数
   - 一次通过率
   - blocked 的 task（如果有）及原因

---

## 状态报告模板

每完成一个 task 后输出简要状态：

```
[Dev-QA] Task 3/8 PASS (attempt 1) | 累计: 3 passed, 0 blocked
[Dev-QA] Task 4/8 FAIL (attempt 2/3) | feedback: [一句话摘要]
[Dev-QA] 集成验证 PASS | 8/8 tasks completed, 一次通过率 75%
```

---

## 与其他流程的关系

- 在 `EnterPlanMode` 或 `superpowers:writing-plans` 之后使用——先有 plan，再用本 skill 执行
- QA review 使用 `pr-review-toolkit:code-reviewer`，不重复造轮子
- 最终验证使用 `superpowers:verification-before-completion`
- 如果 task 涉及多个独立模块，可以用 `superpowers:dispatching-parallel-agents` 并行实现

---

## 反模式

遇到以下倾向时，加载 [references/anti-patterns.md](references/anti-patterns.md) 对照检查。

| 错误 | 正确 |
|------|------|
| 一口气实现所有 task 再统一 review | 逐 task 验证，问题早发现早修 |
| QA 失败后不看 feedback 直接重试 | 带 feedback 定向修复 |
| retry 3 次还失败继续死磕 | 标记 blocked，跳过，最后集中处理 |
| 跳过集成验证直接宣布完成 | 所有 task 过了还要跑一遍完整验证 |
| 每个 task 都用重量级 review | 简单 task 自验证即可，复杂 task 才派 review agent |
