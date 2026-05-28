# Quality Judge — Phase Q04: 技术方案覆盖度审计

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

- [ ] 每条 REQ/SE 都已标注覆盖状态
- [ ] GAP/OPEN 闭环状态已检查
- [ ] 反向审计已完成（NEW_DESIGN + NOT_IN_SCOPE）

## 检查清单（必须逐条检查）

- 每条 REQ/BR/SE 是否在技术方案中有对应设计
- COVERED 判定是否有具体设计证据（不是仅提到接口名）
- MISSING 是否真的缺失
- 技术方案中超出 PRD 范围的设计是否标记为 NEW_DESIGN

## 行为红线（绝对不能做）

- 不评估技术方案质量（Q03 的事）
- 不把 PARTIAL 乐观判为 COVERED

## 领域词汇

- **COVERED**: 需求在技术方案中有完整设计
- **PARTIAL**: 需求在技术方案中有部分设计，缺少异常/边界
- **MISSING**: 需求在技术方案中完全缺失
- **NEW_DESIGN**: 技术方案中有但 PRD 未要求的设计

## 重点检查方向

- 异常分支覆盖
- 反向审计（方案有但需求没有）

## 评审维度 + 检查清单（compose_rubric 生成）

# 评审维度（共享 + 路由 + 动态）

## 通用质量维度（每条结论必须满足）

### source_citation: 来源标注完整性
每条结论是否标注了来源（[来源: 文件名:行号]）
  - 5分: 所有结论都有精确的来源标注（文件名:行号）
  - 4分: 90%+ 结论有来源标注，个别缺失
  - 3分: 70-90% 有来源标注
  - 2分: 来源标注不足 70%
  - 1分: 几乎无来源标注

### confidence_tagging: 置信度标注
每条结论是否标注了置信度（High/Medium/Low）
  - 5分: 所有结论都有置信度标注，且标注合理
  - 4分: 90%+ 有置信度标注
  - 3分: 70-90% 有标注，部分标注不合理
  - 2分: 标注不足 70%
  - 1分: 几乎无置信度标注

### structural_completeness: 结构完整性
报告是否包含所有必要章节，格式是否规范
  - 5分: 所有必要章节齐全，格式规范，无截断
  - 4分: 主要章节齐全，个别格式瑕疵
  - 3分: 缺少 1-2 个非核心章节
  - 2分: 缺少核心章节或格式混乱
  - 1分: 结构严重不完整

### reasoning_quality: 推理日志质量
推理日志是否记录了关键决策过程，可追溯
  - 5分: 每个关键决策都有推理过程记录，可完整追溯
  - 4分: 主要决策有记录，个别步骤缺失
  - 3分: 部分决策有记录，但关键判断缺少推理过程
  - 2分: 推理日志流于形式，缺少实质内容
  - 1分: 几乎无推理记录

## Phase 专属维度（本 Phase 必须检查）

### coverage_accuracy: 覆盖判定准确率
COVERED/PARTIAL/MISSING/IMPLICIT 的判定是否正确
  - 5分: 所有覆盖状态判定正确，COVERED 确实有完整设计，MISSING 确实缺失
  - 4分: 90%+ 判定正确，个别 PARTIAL/COVERED 边界有争议
  - 3分: 70-90% 正确，存在将仅提到接口名就判为 COVERED 的情况
  - 2分: 多个判定错误，正向流程有但异常分支缺失仍判为 COVERED
  - 1分: 大面积判定错误，覆盖率虚高

### missing_detection: 遗漏检出率
技术方案中真正缺失的需求点是否被标记为 MISSING
  - 5分: 所有缺失的需求点都被准确标记为 MISSING
  - 4分: 核心缺失全部检出，仅遗漏 1-2 个边缘 MISSING
  - 3分: 检出了部分 MISSING，但遗漏了关键异常处理/并发场景的缺失
  - 2分: MISSING 检出不足，多个关键缺失未发现
  - 1分: 几乎未检出 MISSING，或全部标为 COVERED

### reverse_audit: 反向审计完整性
技术方案中的新增设计是否被标记为 NEW_DESIGN/NOT_IN_SCOPE
  - 5分: 技术方案中所有超出 PRD 范围的设计都被识别并标记
  - 4分: 主要新增设计已识别，仅遗漏 1-2 个
  - 3分: 部分新增设计被识别，但遗漏了重要的范围外设计
  - 2分: 反向审计明显不足
  - 1分: 未做反向审计

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

Phase 输出目录: `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/finance-model/Q04`

请读取以下文件进行评审：

1. `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/finance-model/Q04/tech_design_coverage_review.md`
2. `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/finance-model/Q04/phase_a5_structured.json`
3. Phase Q01 产物: `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/finance-model/Q01/phase_a_structured.json`

## BUG_CASES — 已知判错案例（务必避免重犯）

以下是 Phase Q04 与当前输入最相关的历史判错案例。

### 反例 1: coverage_summary [漏报]

### 反例 2: Input should be a valid list [type=list_type, input_value={'req': {'total': 10,  [漏报]

### 反例 3: SE-12 标 MISSING 正确，但未分析 BPM 回调并发场景：同一流程多个回调消息同时到达时的处理顺序（与 Q03 EXC-005 同源） [漏报]

**教训**: SE-12 标 MISSING 正确，但未分析 BPM 回调并发场景：同一流程多个回调消息同时到达时的处理顺序（与 Q03 EXC-005 同源）

### 反例 4: SE-05（待交车状态下工单流转状态不变）标 COVERED，但未验证非法状态跳转拦截：工单在非待交车状态下发起提前交车申请时的状态机行为 [漏报]

**教训**: SE-05（待交车状态下工单流转状态不变）标 COVERED，但未验证非法状态跳转拦截：工单在非待交车状态下发起提前交车申请时的状态机行为

### 反例 5: For further information visit https://errors.pydantic.dev/2.12/v/list_type [漏报]

### 反例 6: 1 validation error for PhaseA5Output [错判]

### 反例 7: GAP-03（代驾单取消后状态回退）标「未闭环」但未分析该场景对状态机的影响：代驾单取消后提前交车标识是否回退、工单状态如何处理 [漏报]

**教训**: GAP-03（代驾单取消后状态回退）标「未闭环」但未分析该场景对状态机的影响：代驾单取消后提前交车标识是否回退、工单状态如何处理

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
`/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/finance-model/Q04/_judge_result.json`

```json
{
  "phase": "Q04",
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