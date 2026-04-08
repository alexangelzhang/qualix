# 技能健康度、度量与迭代闭环

> 从 SKILL.md 迁移。轻量借鉴 OpenSpace，不引入完整自进化引擎。

## 度量维度

| 维度 | 含义 | 主要 Phase | 退化信号 |
| ---- | ---- | --------- | -------- |
| 结构化完备率 | REQ/BR 无遗漏、均有父链 | A | 反复"补提 REQ" |
| SE 显式率 | 每条需求挂够可验证 SE | A | 大量 NEEDS_CONTEXT 未进 GAP |
| GAP/OPEN 闭环率 | OPEN 清零或显式延期 | A→A.5→D | OPEN 滞留多轮 |
| 多模态置信度 | 图片/白板已解析并进 SEM | A,C | 图示规则未进矩阵即判通过 |
| EUT↔契约对齐率 | EUT 覆盖 Phase A 的 REQ/BR/SE | B | 孤儿 EUT 或从代码反推 |
| 覆盖质地 | COVERED vs WRONG_TARGET/MISSING 占比 | C | WRONG_TARGET 占比上升 |
| T1 异常门禁 | T1 异常分支无 MISSING | C | 同类漏测重复出现 |
| SEM 溯源率 | 用例/SEM 可追溯到 PRD 原文 | A,C | 低置信度场景过多 |
| 技术方案覆盖率 | Phase A 产物在技术方案中的覆盖比例 | A.5 | MISSING 占比上升 |
| 技术方案质量问题密度 | 每份方案的 WARN/FAIL 数 | A.6 | 同类问题跨方案重复 |
| Failure Mode 覆盖率 | 关键路径均有故障场景分析 | A.6 | CRITICAL_GAP 出现即阻断 |
| 变异杀伤率 | Mutation Score 达标 | C | MUTATION_SURVIVED_CRITICAL 未补强 |

采集方式：人工或表格记录，无需外部平台。重点是同类失败重复出现时触发反馈动作。

## 执行后反馈

1. **归类失败**：`SKILL_RULE`（规则歧义）/ `SCRIPT`（ingest/解析）/ `TEMPLATE`（骨架）/ `CONTEXT`（输入不足）。
2. **防重复劳动**：若与上轮同类，写出根因是否相同；相同则改一处契约而非口述。
3. **沉淀形态**：FIX（修正单条规则）/ DERIVED（references/ 增附录）/ CAPTURED（成功案例写入 references/）。
4. **安全边界**：对 skill/modules/脚本的实质修改须走人工确认。

## 回归烟雾测

维护 1~3 份脱敏 PRD 快照，大改后跑 Phase A→C 迷你流程，对比 GAP/OPEN 数量级、WRONG_TARGET 数、ingest 成功率。目标：同一输入下质量不回退。
