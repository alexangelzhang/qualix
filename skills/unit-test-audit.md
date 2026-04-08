---
name: unit-test-audit
description: "Phase C: 需求驱动的单测覆盖审计，验证测试与需求真实匹配"
trigger: "用户要求审计单测覆盖质量，或 Phase B 完成后进入"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase C: 单测覆盖审计

验证单测是否真正测对了业务场景，而非仅追求覆盖率数字。

## 前置依赖

- Phase A 产出（REQ/BR/SE）

## 技术栈基线

- profile 基线：
  - `java-ddd-tmf` → `references/java-ddd-tmf-baseline.md`
  - `go-service` → `references/go-service-baseline.md`
- `FEATURE-MUTATION-TESTING.md`

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase A 结构化产物是唯一的需求基线，不要回溯飞书原文。
4. 若存在 `_internal/_weak_assert_context.md`，必须优先读取；它是基于 diff 测试文件生成的 weak assert 候选 sidecar，可作为 `WRONG_TARGET` 的优先复核清单。
5. weak assert sidecar 只是候选清单，不能直接照抄结论；必须回到测试代码逐条核实。

## 执行流程

读取 `skills/modules/08_phase_c_ut_audit_zh.md` 并按其中定义的流程执行：

执行前先读取 `output/<project>/phaseC/_internal/_weak_assert_context.md`（如存在），把其中命中的测试方法作为 Step 2 / Step 5 / Step 7.5 的重点核验对象。

1. Step 0: 基线、架构与范围确认
2. Step 1: 需求场景建模（先于代码）
3. Step 1.1: 关键语义（SEM）专项建模
4. Step 2: 场景 → 代码 → 测试映射
5. Step 3: 分层职责一致性专项审计
6. Step 4: 异常分支专项审计
7. Step 5: 异常分支强制断言审计
8. Step 6: 覆盖率门禁与特殊规则检查
9. Step 7: Mapper/Service 断言 checklist 审计
10. Step 7.5: 变异测试（默认开启）
11. Step 8: 审计结论与风险分级
12. Step 9: 自检（提交前强制检查）
    - [ ] 每个审计判定（COVERED/MISSING/WRONG_TARGET）有代码证据
    - [ ] T1 核心异常分支 100% 覆盖检查
    - [ ] 弱断言（assertNotNull/assertTrue(true)等）已识别为 WRONG_TARGET
    - [ ] 覆盖率门禁达标（line >= 80%, branch >= 80%）
    - [ ] 每个发现标注了来源和置信度
    - [ ] 如果是重跑：新版是旧版超集
    - [ ] 推理日志 _reasoning_log.md 已同步输出
13. Step 10: Judge/Critique（提交前自我评审）
    - Judge: 对照代码逐条验证审计判定准确性
    - Critique: 假设有遗漏，重点检查异常分支、并发场景、事务回滚测试
    - 记录在报告末尾"自我评审记录"章节
14. Step 11: 修正
    - 根据 Judge/Critique 发现的问题，修正审计判定和报告内容
    - 修正后重新执行自检清单，确保全部通过

## 关键门禁

| 指标 | 阈值 |
|------|------|
| 增量行覆盖率 | >= 80% |
| 增量分支覆盖率 | >= 80% |
| T1 核心异常分支 | 100% 覆盖 |
| 变异杀伤率 T1 | >= 80% |
| 变异杀伤率 T2 | >= 60% |

## 结论枚举

`PASS` / `PASS_WITH_RISKS` / `FAIL`

## 报告结构建议

- 复用 `references/ut-audit-template.md`
- 报告头必须包含 `PROFILE_CONTEXT`（来自 `output/<project>/phaseC/_profile_context.md`）

## 通过标准

- 关键门禁全部达标
- 自检清单全部通过
- Judge/Critique 已执行且问题已修正
- 推理日志已输出

## 禁止事项

- 禁止在 Phase A/A.5/A.6 输出 UT/EUT
- 禁止自动 commit/push 代码
- 禁止编造不存在的接口、字段、逻辑
- 禁止跳过自检和 Judge/Critique 直接 finalize
- 禁止重跑时从零重写
