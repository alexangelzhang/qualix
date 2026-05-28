# Quality Judge — Phase Q05a: EUT 矩阵设计

## 评估目标

基于原始输入、Phase 产物、Gate Checklist 和已知失败案例，判断本 Phase 输出是否满足质量门禁。

## Gate Checklist（通过标准）

- [ ] 三层驱动目标模块完整（se_mappings + br_mappings + git_diff_files 全部非空）
- [ ] 每条 REQ/BR/SE 都有对应 EUT（bound_item 非空，100% 覆盖）
- [ ] git diff 每个实现类都出现在某条 EUT 的 when 字段（C10 无 BLOCKED）
- [ ] then 字段包含具体断言（非模糊描述）

## 评审输入

### EUT 矩阵（产物节选）

**严重铁律违反：按 SE 汇总，非 EUT 逐条模式**

| EUT ID | 被测目标 | 路径 | 绑定项 | then |
|--------|---------|------|-------|------|
| EUT-SE001 | SE-001 全部相关测试 | Mixed | SE-001 | 验证 SE-001 的所有路径均通过 |
| EUT-SE002 | SE-002 全部相关测试 | Mixed | SE-002 | 验证 SE-002 能力识别逻辑正确 |
| EUT-SE003 | SE-003 全部相关测试 | Mixed | SE-003 | 验证提交强校验逻辑通过 |
| EUT-SE004 | SE-004 全部相关测试 | Mixed | SE-004 | 验证入库单跳过逻辑 |
| EUT-SE005 | SE-005 全部相关测试 | Mixed | SE-005 | 验证换货单创建成功 |
| EUT-SE006 | SE-006 全部相关测试 | Mixed | SE-006 | 验证批量查询接口正确返回 |
| EUT-SE007 | SE-007 全部相关测试 | Mixed | SE-007 | 验证非物流取旧送新返回 false |
| EUT-SE008 | SE-008 全部相关测试 | Mixed | SE-008 | 验证降级逻辑不阻断主流程 |
| EUT-SE009 | SE-009 全部相关测试 | Mixed | SE-009 | 验证 null 参数抛出异常 |
| EUT-SE010 | SE-010 全部相关测试 | Mixed | SE-010 | 验证工单流切换正确 |
| EUT-SE011 | SE-011 全部相关测试 | Mixed | SE-011 | 验证日志写入且终态正确 |

**统计：11 个 EUT，覆盖 11 个 SE（一对一）**

### 问题说明

本产物使用了 SE-based 汇总模式：
- 每个 SE 对应一个 EUT（11 SE → 11 EUT）
- EUT ID 格式为 EUT-SE001 等，按 SE 编号命名
- then 字段均为泛化描述（"验证...正确""验证...通过"）
- Happy/Exception/Boundary 路径未分别列出
- 实际应有 40-60 条 EUT 才能覆盖所有路径组合

## BUG_CASES — 已知判错案例（务必避免重犯）

### 反例 1: EUT then 字段模糊 [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 2: SE-based 聚合模式 [铁律违反]

**教训**: Q05a 必须使用 EUT 逐条模式，禁止按 SE 汇总——每个 SE 可能对应多个路径类型（Happy/Exception/Boundary），必须逐条列出

## 开始评审

请逐个维度评审。注意：本产物使用了 SE-based 聚合（每 SE 对应一条 EUT），而非正确的 EUT 逐条模式（每路径类型一条 EUT）。
