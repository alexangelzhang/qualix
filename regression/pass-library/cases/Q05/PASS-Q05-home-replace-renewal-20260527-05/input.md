# Quality Judge — Phase Q05: 单测生成

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

- [ ] EUT 矩阵覆盖了所有 REQ/BR/SE
- [ ] 单测代码使用强断言（非仅执行流程）
- [ ] 异常路径有对应测试

## 检查清单（必须逐条检查）

- 每条 REQ/BR/SE 是否有对应 EUT
- Happy Path + Exception + Boundary 三种路径是否覆盖
- 断言是否验证业务语义（不是 assertNotNull）
- Mock 层级是否合理（Real > Fake > Stub > Mock）
- 代码是否可编译

## 行为红线（绝对不能做）

- 不评估被测代码质量
- 不接受 assertNotNull 冒充覆盖

## 领域词汇

- **EUT**: Expected Unit Test，预期单元测试
- **DAMP**: Descriptive And Meaningful Phrases，测试可读性优先原则
- **弱断言**: assertNotNull/assertTrue(true) 等不验证业务语义的断言

## 重点检查方向

- 断言强度
- SE 追溯性
- 编译可行性

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

### eut_coverage: EUT 覆盖完备性
EUT 矩阵是否覆盖了所有 REQ/BR/SE，包括 Happy Path、Exception、Boundary
  - 5分: 每条 REQ/BR/SE 都有对应 EUT，三种路径类型均覆盖
  - 4分: 90%+ REQ/SE 有 EUT，仅遗漏 1-2 个边界场景
  - 3分: 主要 REQ 有 EUT，但 Exception/Boundary 路径覆盖不足
  - 2分: EUT 覆盖不足 70%，大量 SE 无对应测试
  - 1分: EUT 矩阵严重不完整

### assert_strength: 断言强度
生成的单测是否使用强断言验证业务语义，而非仅 assertNotNull/assertTrue(true)
  - 5分: 所有测试都有 assertEquals 验证业务字段、verify 验证交互、assertThrows 验证异常码
  - 4分: 90%+ 测试有强断言，个别测试断言稍弱
  - 3分: 主要测试有强断言，但存在 assertNotNull 冒充覆盖的情况
  - 2分: 多个测试仅有弱断言，未验证业务语义
  - 1分: 大量测试无实质断言或仅 assertNotNull

### code_compilability: 代码可编译性
生成的单测代码是否能通过编译，import/mock/setup 是否正确
  - 5分: 所有测试代码编译通过，import 正确，mock 配置完整
  - 4分: 90%+ 编译通过，个别 import 缺失但易修复
  - 3分: 主要测试可编译，但 mock 配置有遗漏导致部分编译失败
  - 2分: 多个测试编译失败，缺少关键依赖或 mock
  - 1分: 大面积编译失败

### se_traceability: SE 追溯性
每个测试方法是否能追溯到对应的 SE/EUT ID
  - 5分: 每个 @Test 方法都有 @Tag 或注释标注对应的 EUT/SE ID
  - 4分: 90%+ 测试有追溯标注
  - 3分: 部分测试有标注，但缺少系统性的追溯
  - 2分: 追溯标注不足 50%
  - 1分: 几乎无追溯标注

## 动态维度（本项目特有，必须检查）

### dyn_error_recovery: 异常恢复业务规则
[必查, 2 SE 命中] 失败/回滚/撤销场景下的业务规则是否明确（数据留/删、状态回退到哪、用户可否重试）
  - 5分: 所有失败/回滚/撤销 SE 都有明确业务规则（数据去向、状态回退目标、用户可否重试）
  - 4分: 90%+ 异常恢复 SE 有明确业务规则
  - 3分: 主要异常场景有规则，但部分失败后数据状态未定义
  - 2分: 异常恢复规则不完整，可能产生数据孤岛
  - 1分: 几乎未定义异常恢复规则

### dyn_external_dependency: 外部依赖降级策略
[必查, 0 SE 命中 — 按门限兜底] PRD 涉及外部系统/中台/第三方时是否有业务级降级策略（用户看到什么、本地数据怎么处理）
  - 5分: 所有外部依赖 SE 都明确了业务级降级：错误码/用户提示/本地兜底流
  - 4分: 90%+ 外部依赖 SE 有降级策略
  - 3分: 主要外部依赖有降级，但部分场景未定义超时行为
  - 2分: 降级策略不完整，用户可能看到技术错误栈
  - 1分: 几乎未定义外部依赖降级

### dyn_concurrency: 并发安全覆盖
[必查, 0 SE 命中 — 按门限兜底] 涉及并发/幂等的 SE 是否都有对应的保护机制验证
  - 5分: 所有并发类 SE 都有锁/幂等/事务隔离的验证
  - 4分: 90%+ 并发 SE 有保护机制验证
  - 3分: 主要并发场景已覆盖，但缺少竞争窗口分析
  - 2分: 并发安全验证不足
  - 1分: 几乎未验证并发安全

### dyn_data_consistency: 数据一致性口径
[必查, 0 SE 命中 — 按门限兜底] 多入口/多表/异步数据的一致性口径是否明确且可验证
  - 5分: 所有跨入口/跨表/跨系统 SE 都有字段级一致性口径（如 A 入口 vs B 入口的字段对齐规则）和可执行验证
  - 4分: 90%+ 一致性 SE 有明确口径和验证方法
  - 3分: 主要一致性场景有口径，但部分跨系统/异步一致性未明确
  - 2分: 一致性口径模糊，缺少字段级对齐规则
  - 1分: 几乎未明确一致性口径

### dyn_state_machine: 状态机完整性
[必查, 0 SE 命中 — 按门限兜底] 状态流转的合法性、非法跳转拦截是否都被验证
  - 5分: 所有状态迁移路径（含非法路径）都有验证
  - 4分: 正向流转全覆盖，仅遗漏 1-2 个非法跳转
  - 3分: 主要流转已覆盖，但反向/跨状态跳转未验证
  - 2分: 状态机验证不完整
  - 1分: 几乎未验证状态流转


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

Phase 输出目录: `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/home-replace-renewal/Q05`

请读取以下文件进行评审：

1. `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/home-replace-renewal/Q05/eut_matrix.md`
2. `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/home-replace-renewal/Q05/phase_b_structured.json`
3. Phase Q01 产物: `/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/home-replace-renewal/Q01/phase_a_structured.json`

## BUG_CASES — 已知判错案例（务必避免重犯）

以下是 Phase Q05 与当前输入最相关的历史判错案例。

### 反例 1: SE-014（授权店与直营店隔离）仅通过 EUT-003/013/014 验证了 isCarAuthorityBusinessMode 的 true/false [漏报]

**教训**: SE-014（授权店与直营店隔离）仅通过 EUT-003/013/014 验证了 isCarAuthorityBusinessMode 的 true/false，未验证直营店调用提前交车接口时的拦截行为

### 反例 2: BR-003（角色条件：店长/服务顾问主管/服务顾问）无独立 EUT 验证非授权角色被拒绝 [漏报]

**教训**: BR-003（角色条件：店长/服务顾问主管/服务顾问）无独立 EUT 验证非授权角色被拒绝

### 反例 3: 审批权限（BR-009 OR 逻辑）仅通过 EUT-041/042 验证了通过场景，未验证非授权角色尝试审批时的拦截 [漏报]

**教训**: 审批权限（BR-009 OR 逻辑）仅通过 EUT-041/042 验证了通过场景，未验证非授权角色尝试审批时的拦截

### 反例 4: eut_items.0.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 5: eut_items.1.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 6: eut_items.2.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 7: eut_items.3.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 8: eut_items.42.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 9: eut_items.43.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 10: eut_items.44.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

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
`/Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate/output/home-replace-renewal/Q05/_judge_result.json`

```json
{
  "phase": "Q05",
  "project_id": "home-replace-renewal",
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