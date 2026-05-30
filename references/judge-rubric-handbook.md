# Qualix Judge 评审维度手册

> 每个 Phase 的 Judge 按 1-5 Likert 量表逐维度打分，3.5 分以下自动不通过。
> 动态维度根据项目 SE 分布自动追加（最多 3 个），追加后权重自动归一化。

---

## Phase Q01 — 需求结构化（4 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| faithfulness | 忠实度 | 25% | 输出的 REQ/SE/GAP 是否忠实于 PRD 原文，不编造 |
| completeness | 完备性 | 30% | PRD 中的所有需求点是否都被提取为 REQ/BR |
| se_explicitness | SE 显式率 | 25% | 关键业务语义（并发/幂等/边界）是否被显式化为可验证的 SE |
| gap_detection | GAP 发现率 | 20% | PRD 中的模糊点、缺失定义是否被识别为 GAP/OPEN |

### 评分锚定（以 completeness 为例）

| 分数 | 标准 |
|------|------|
| 5 | PRD 所有功能点、业务规则、约束条件均已提取，无遗漏 |
| 4 | 核心功能点全部覆盖，仅遗漏 1-2 个边缘场景 |
| 3 | 主要功能点已覆盖，遗漏 3-5 个需求点 |
| 2 | 明显遗漏多个功能点或整个业务模块 |
| 1 | 大面积遗漏，仅提取了部分表面需求 |

---

## Phase Q04 — 技术方案覆盖度审计（3 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| coverage_accuracy | 覆盖判定准确率 | 40% | COVERED/PARTIAL/MISSING/IMPLICIT 的判定是否正确，防止虚高覆盖率 |
| missing_detection | 遗漏检出率 | 30% | 技术方案中真正缺失的需求点是否被标记为 MISSING |
| reverse_audit | 反向审计完整性 | 30% | 技术方案中超出 PRD 范围的新增设计是否被识别为 NEW_DESIGN/NOT_IN_SCOPE |

### 评分锚定（以 coverage_accuracy 为例）

| 分数 | 标准 |
|------|------|
| 5 | 所有覆盖状态判定正确，COVERED 确实有完整设计，MISSING 确实缺失 |
| 4 | 90%+ 判定正确，个别 PARTIAL/COVERED 边界有争议 |
| 3 | 70-90% 正确，存在将仅提到接口名就判为 COVERED 的情况 |
| 2 | 多个判定错误，正向流程有但异常分支缺失仍判为 COVERED |
| 1 | 大面积判定错误，覆盖率虚高 |

---

## Phase Q03 — 技术方案质量评审（3 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| issue_validity | 问题有效率 | 30% | 发现的质量问题是否是真问题（非噪音），有具体代码/设计证据支撑 |
| failure_mode_coverage | Failure Mode 覆盖率 | 35% | 关键业务路径（写操作/RPC/状态迁移）是否都做了故障场景分析 |
| exception_coverage | 异常矩阵覆盖率 | 35% | 12 类异常分支是否都被检查，每类有具体的技术方案对应分析 |

### 评分锚定（以 failure_mode_coverage 为例）

| 分数 | 标准 |
|------|------|
| 5 | 所有写操作/RPC 调用/状态迁移都有 Failure Mode 分析 |
| 4 | 核心路径全覆盖，仅遗漏 1-2 个非关键路径 |
| 3 | 主要路径已覆盖，但跨服务调用的部分失败场景遗漏 |
| 2 | Failure Mode 分析不完整，多个关键路径缺失 |
| 1 | 几乎未做 Failure Mode 分析 |

---

## Phase Q05 — 单测生成（4 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| eut_coverage | EUT 覆盖完备性 | 30% | EUT 矩阵是否覆盖了所有 REQ/BR/SE，包括 Happy/Exception/Boundary 三种路径 |
| assert_strength | 断言强度 | 35% | 是否用强断言验证业务语义，而非仅 assertNotNull/assertTrue(true) |
| code_compilability | 代码可编译性 | 20% | 生成的代码能否通过编译，import/mock/setup 是否正确 |
| se_traceability | SE 追溯性 | 15% | 每个测试方法能否追溯到对应的 SE/EUT ID |

### 评分锚定（以 assert_strength 为例）

| 分数 | 标准 |
|------|------|
| 5 | 所有测试都有 assertEquals 验证业务字段、verify 验证交互、assertThrows 验证异常码 |
| 4 | 90%+ 测试有强断言，个别测试断言稍弱 |
| 3 | 主要测试有强断言，但存在 assertNotNull 冒充覆盖的情况 |
| 2 | 多个测试仅有弱断言，未验证业务语义 |
| 1 | 大量测试无实质断言或仅 assertNotNull |

---

## Phase Q06 — 单测覆盖审计（3 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| audit_accuracy | 审计判定准确率 | 35% | COVERED/MISSING/WRONG_TARGET 的判定是否正确 |
| wrong_target_detection | WRONG_TARGET 检出率 | 30% | 弱断言（assertNotNull/assertTrue(true)等）是否被正确标记为 WRONG_TARGET |
| exception_branch | 异常分支覆盖 | 35% | T1 核心异常分支是否都有对应测试，断言包含异常类型+状态不变+无脏数据 |

### 评分锚定（以 wrong_target_detection 为例）

| 分数 | 标准 |
|------|------|
| 5 | 所有弱断言（assertNotNull/assertTrue(true)等）都被标记为 WRONG_TARGET |
| 4 | 90%+ 弱断言被检出 |
| 3 | 主要弱断言被检出，但遗漏了只验证返回值不验证业务语义的情况 |
| 2 | WRONG_TARGET 检出不足，多个弱断言被判为 COVERED |
| 1 | 几乎未检出 WRONG_TARGET |

---

## Phase Q07 — 代码评审（4 维度）

| 维度 ID | 名称 | 权重 | 评审目标 |
|---------|------|------|---------|
| finding_validity | 发现有效率 | 30% | 评审发现的问题是否是真问题，有具体文件:行号和代码片段证据 |
| req_code_alignment | 需求-代码对齐度 | 30% | 是否逐条检查了 REQ/BR/SE 在代码中的实现完整性 |
| severity_accuracy | 严重级别准确性 | 20% | BLOCKER/CRITICAL/MAJOR/MINOR 的分级是否合理 |
| call_chain_tracing | 调用链路追踪 | 20% | 是否追踪了改动功能点的完整调用链（Controller→Service→Domain→Gateway） |

### 评分锚定（以 finding_validity 为例）

| 分数 | 标准 |
|------|------|
| 5 | 所有 finding 都是真问题，引用了具体文件:行号和代码片段 |
| 4 | 90%+ 是真问题，个别 finding 证据稍弱 |
| 3 | 70-90% 是真问题，存在基于猜测的 finding |
| 2 | 噪音 finding 占比超 30% |
| 1 | 大量 finding 缺乏证据或是误报 |

---

## 动态维度（根据项目 SE 分布自动追加）

当项目的 Phase Q01 产出中某个业务域的 SE 数量 >= 2 时，Judge 会自动追加对应的评分维度：

| 触发条件 | 动态维度 ID | 名称 | 评审目标 |
|---------|------------|------|---------|
| 金额类 SE >= 2 | dyn_amount_precision | 金额精度验证 | BigDecimal/setScale/舍入模式是否都有验证 |
| 并发类 SE >= 2 | dyn_concurrency | 并发安全覆盖 | 锁/幂等/事务隔离是否都有验证 |
| 状态机类 SE >= 2 | dyn_state_machine | 状态机完整性 | 合法/非法状态迁移路径是否都被验证 |
| 权限类 SE >= 2 | dyn_permission | 权限隔离验证 | 越权访问/角色隔离是否有测试 |
| 超时类 SE >= 2 | dyn_timeout | 超时补偿机制 | 降级行为/重试次数是否有验证 |
| 回调类 SE >= 2 | dyn_callback | 回调通知验证 | verify(times(1)) 或等价验证是否存在 |

动态维度权重默认 15%，追加后所有维度权重自动归一化到 100%。最多追加 3 个（按 SE 数量排序取 top 3）。

---

## Anti-Rationalization（防止放水）

| 常见放水借口 | 为什么不能接受 | 正确做法 |
|---|---|---|
| "虽然缺少边界测试，但主流程覆盖了" | 边界是 bug 高发区，缺失即扣分 | 按 SE 逐条检查边界覆盖 |
| "文档描述基本清晰" | "基本"="有歧义"，必须指出哪里不清晰 | 找到具体的模糊描述，标注为 GAP |
| "整体质量可接受" | 禁止整体评价，必须逐维度打分 | 每个维度独立打分，列出具体扣分证据 |
| "虽然没有并发测试，但业务场景简单" | 只要 SE 涉及并发，就必须有对应验证 | 检查 SE 列表，有并发关键词的必须有测试 |
| "覆盖率数字达标了" | 覆盖率不等于断言质量 | 检查断言是否验证了业务语义 |
| "异常处理已经有 try-catch" | try-catch 存在不等于异常被正确处理 | 检查 catch 块是否有正确的回滚/补偿/通知 |
| "这个问题影响不大" | Judge 不做影响评估，只做事实判定 | 如实报告问题，影响评估留给 approve 阶段 |
| "上一轮已经改进了" | 每轮独立评审，不考虑历史改进 | 只看当前版本的产物质量 |

核心原则：**宁可多报不可漏报（FN 比 FP 更严重）。如果犹豫是否扣分，扣。**

---

*生成自 `src/qualix/quality/judge.py` 的 `_JUDGE_RUBRICS` + `_ANTI_RATIONALIZATION_SECTION` + `src/qualix/quality/dynamic_rubric.py`*

*最后更新：2026-04-09*
