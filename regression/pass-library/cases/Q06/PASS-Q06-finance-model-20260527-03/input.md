# Quality Judge — Phase Q06: 单测覆盖审计

## 评估目标

基于原始输入、Phase 产物、Gate Checklist、评估协议和已知失败案例，判断本 Phase 输出是否满足质量门禁。
结论必须由证据支撑；没有原文引用或文件依据的判断一律视为不成立。

## 行为约束

- 每个结论都必须引用具体证据；没有引用的结论不能计入评分依据
- 不接受'基本覆盖''整体还行'这类无法验证的模糊表述
- 主动寻找漏报（FN）、错判、虚构和证据不足，不为已有产物辩护
- 不修复产物，只输出评审结论和结构化问题

## 评审规则

1. 你是独立评审员，不是执行者。你的任务是找出问题，不是修复问题。
2. 每个评分维度按 1-5 分 Likert 量表打分，严格对照每级标准。
3. 漏报（FN）比误报（FP）更严重 — 宁可多报不可漏报。
4. 必须对照原始输入（PRD/技术方案/代码）逐条验证，不能只看输出的自洽性。
5. 每个维度必须列出具体的扣分证据（引用原文位置）。

## Gate Checklist（通过标准）

- [ ] 覆盖率门禁达标（line >= 80%, branch >= 80%）
- [ ] T1 核心异常分支 100% 覆盖
- [ ] 无 WRONG_TARGET 问题

## 检查清单（必须逐条检查）

- 每条 EUT 的覆盖状态判定是否正确
- 弱断言是否标记为 WRONG_TARGET
- T1 核心异常分支是否有测试
- 测试数据是否覆盖真实故障组合（多记录/边界值/枚举组合）

## 行为红线（绝对不能做）

- 不评估测试代码风格
- 不把 assertNotNull 判为 COVERED
- 团队有意的模式冲突标记 CONFLICT 而非误判

## 领域词汇

- **WRONG_TARGET**: 测试存在但断言目标错误（弱断言）
- **CONFLICT**: 团队有意的模式与审计标准冲突，交人工裁决
- **T1**: Tier 1，核心业务路径

## 重点检查方向

- 弱断言检测
- 场景覆盖质量
- 增量覆盖率

## 评审维度 + 检查清单（compose_rubric 生成）

# 评审维度（共享 + 路由 + 动态）

## 通用质量维度（每条结论必须满足）

### source_citation: 来源标注完整性
每条结论是否标注了来源（[来源: 文件名:行号]）

### confidence_tagging: 置信度标注
每条结论是否标注了置信度（High/Medium/Low）

### structural_completeness: 结构完整性
报告是否包含所有必要章节，格式是否规范

### reasoning_quality: 推理日志质量
推理日志是否记录了关键决策过程，可追溯

## Phase 专属维度（本 Phase 必须检查）

### audit_accuracy: 审计判定准确率
COVERED/MISSING/WRONG_TARGET 的判定是否正确
  - 5分: 所有审计状态判定正确，COVERED 确实有强断言，WRONG_TARGET 确实是弱断言
  - 4分: 90%+ 判定正确，个别边界 case 有争议
  - 3分: 70-90% 正确，存在将 assertNotNull 判为 COVERED 的情况
  - 2分: 多个判定错误，弱断言未被识别
  - 1分: 大面积判定错误

### wrong_target_detection: WRONG_TARGET 检出率
弱断言的测试是否被正确标记为 WRONG_TARGET
  - 5分: 所有弱断言（assertNotNull/assertTrue(true)等）都被标记为 WRONG_TARGET
  - 4分: 90%+ 弱断言被检出
  - 3分: 主要弱断言被检出，但遗漏了只验证返回值不验证业务语义的情况
  - 2分: WRONG_TARGET 检出不足，多个弱断言被判为 COVERED
  - 1分: 几乎未检出 WRONG_TARGET

### exception_branch: 异常分支覆盖
T1 核心异常分支是否都有对应测试
  - 5分: 所有 T1 异常分支都有测试，断言包含异常类型+状态不变+无脏数据
  - 4分: 90%+ T1 异常有测试，个别断言不够完整
  - 3分: 主要异常有测试，但缺少并发冲突/事务回滚等场景
  - 2分: 异常分支测试明显不足
  - 1分: 几乎无异常分支测试

### scenario_quality: 场景覆盖质量
测试数据是否覆盖真实故障组合（多记录/边界值/特定枚举组合/多条件AND）
  - 5分: 测试数据覆盖了多记录场景、边界值组合、特定枚举组合，mock 数据贴近真实业务
  - 4分: 主要故障组合已覆盖，个别边界组合缺失
  - 3分: 测试数据偏简单（单记录、默认值），未覆盖多条件组合触发的分支
  - 2分: 测试数据明显不足，多个关键组合未覆盖
  - 1分: 测试数据几乎全是 happy path 默认值，无法触发真实故障路径

## 动态维度（本项目特有，必须检查）

### dyn_state_machine: 状态机完整性
[8 SE] 状态流转的合法性、非法跳转拦截是否都被验证
  - 5分: 所有状态迁移路径（含非法路径）都有验证
  - 4分: 正向流转全覆盖，仅遗漏 1-2 个非法跳转
  - 3分: 主要流转已覆盖，但反向/跨状态跳转未验证
  - 2分: 状态机验证不完整
  - 1分: 几乎未验证状态流转

### dyn_amount_precision: 金额精度验证
[3 SE] 涉及金额计算的 SE 是否都有精度校验（BigDecimal、setScale、舍入模式）
  - 5分: 所有金额类 SE 都有精确到分的验证，舍入模式明确
  - 4分: 90%+ 金额 SE 有精度验证
  - 3分: 主要金额 SE 有验证，但部分缺少舍入模式检查
  - 2分: 金额精度验证不足，存在 double 直接计算的风险
  - 1分: 几乎未验证金额精度


## Anti-Rationalization（禁止放水）

以下是 Judge 常见的放水借口。如果你发现自己在用这些理由，立即停下来重新评估。

| 常见放水借口 | 为什么不能接受 | 正确做法 |
|---|---|---|
| "虽然缺少边界测试，但主流程覆盖了" | 边界是 bug 高发区，缺失即扣分 | 按 SE 逐条检查边界覆盖，缺失的列入 issues |
| "文档描述基本清晰" | "基本"="有歧义"，必须指出哪里不清晰 | 找到具体的模糊描述，标注为 GAP |
| "整体质量可接受" | 禁止整体评价，必须逐维度打分 | 每个维度独立打分，列出具体扣分证据 |
| "虽然没有并发测试，但业务场景简单" | 只要 SE 涉及并发，就必须有对应验证 | 检查 SE 列表，有并发关键词的必须有测试 |
| "覆盖率数字达标了" | 覆盖率不等于断言质量，assertNotNull 不算有效覆盖 | 检查断言是否验证了业务语义，不只是执行路径 |
| "异常处理已经有 try-catch" | try-catch 存在不等于异常被正确处理 | 检查 catch 块是否有正确的回滚/补偿/通知 |
| "这个问题影响不大" | Judge 不做影响评估，只做事实判定 | 如实报告问题，影响评估留给 approve 阶段 |
| "上一轮已经改进了" | 每轮独立评审，不考虑历史改进 | 只看当前版本的产物质量 |

**核心原则**：宁可多报不可漏报（FN 比 FP 更严重）。如果犹豫是否扣分，扣。

## 评审输入

Phase 输出目录: `/Users/zhangyiqian/git_dev/qualix/qualix/output/finance-model/Q06`

请读取以下文件进行评审：

1. `/Users/zhangyiqian/git_dev/qualix/qualix/output/finance-model/Q06/ut_audit_report.md`
2. `/Users/zhangyiqian/git_dev/qualix/qualix/output/finance-model/Q06/phase_c_structured.json`
3. Phase Q01 产物: `/Users/zhangyiqian/git_dev/qualix/qualix/output/finance-model/Q01/phase_a_structured.json`

## BUG_CASES — 已知判错案例（务必避免重犯）

以下是 Phase Q06 与当前输入最相关的历史判错案例。

### 反例 1: audit_items.0.eut_id [漏报]

### 反例 2: audit_items.0.status [漏报]

### 反例 3: audit_items.1.eut_id [漏报]

### 反例 4: audit_items.1.status [漏报]

### 反例 5: audit_items.2.eut_id [漏报]

### 反例 6: audit_items.2.status [漏报]

### 反例 7: audit_items.3.eut_id [漏报]

### 反例 8: audit_items.3.status [漏报]

### 反例 9: audit_items.4.eut_id [漏报]

### 反例 10: audit_items.4.status [漏报]

## Anti-Rationalization（禁止放水）

以下是 Judge 常见的放水借口。如果你发现自己在用这些理由，立即停下来重新评估。

| 常见放水借口 | 为什么不能接受 | 正确做法 |
|---|---|---|
| "虽然缺少边界测试，但主流程覆盖了" | 边界是 bug 高发区，缺失即扣分 | 按 SE 逐条检查边界覆盖，缺失的列入 issues |
| "文档描述基本清晰" | "基本"="有歧义"，必须指出哪里不清晰 | 找到具体的模糊描述，标注为 GAP |
| "整体质量可接受" | 禁止整体评价，必须逐维度打分 | 每个维度独立打分，列出具体扣分证据 |
| "虽然没有并发测试，但业务场景简单" | 只要 SE 涉及并发，就必须有对应验证 | 检查 SE 列表，有并发关键词的必须有测试 |
| "覆盖率数字达标了" | 覆盖率不等于断言质量，assertNotNull 不算有效覆盖 | 检查断言是否验证了业务语义，不只是执行路径 |
| "异常处理已经有 try-catch" | try-catch 存在不等于异常被正确处理 | 检查 catch 块是否有正确的回滚/补偿/通知 |
| "这个问题影响不大" | Judge 不做影响评估，只做事实判定 | 如实报告问题，影响评估留给 approve 阶段 |
| "上一轮已经改进了" | 每轮独立评审，不考虑历史改进 | 只看当前版本的产物质量 |

**核心原则**：宁可多报不可漏报（FN 比 FP 更严重）。如果犹豫是否扣分，扣。

## 输出格式

请输出以下 JSON 格式的评审结果，保存到：
`/Users/zhangyiqian/git_dev/qualix/qualix/output/finance-model/Q06/_judge_result.json`

```json
{
  "phase": "Q06",
  "project_id": "finance-model",
  "judged_at": "ISO8601 时间戳",
  "gate_checklist": [
    {"item": "checklist 项", "passed": true/false, "evidence": "判断依据"}
  ],
  "dimensions": [
    {
      "id": "维度 ID",
      "score": 4,
      "max_score": 5,
      "issues": [
        {"type": "FN/FP/WRONG", "description": "具体问题", "evidence": "原文引用"}
      ]
    }
  ],
  "overall_score": 3.8,
  "precision_estimate": 0.85,
  "recall_estimate": 0.75,
  "summary": "一句话总结",
  "top_issues": ["最重要的 3 个问题"]
}
```

## 开始评审

请逐个维度评审，先读取所有文件，再给出评分。