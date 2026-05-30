# Q05a EUT 矩阵设计报告 — failure-cause（故障原因主数据建设）

## 结论

**PASS_WITH_NON_TESTABLE_ITEMS**

共设计 54 条 EUT，覆盖 15 个业务逻辑实现类中的核心方法。95 个纯数据/接口/基础设施文件已分类到 `excluded_diff_files`，7 个不可测需求项已标注。

---

## 机器产物索引

| 产物 | 路径 |
|------|------|
| code_index.json | q05a/code_index.json（110 diff files，110 classes） |
| eut_matrix.json | q05a/eut_matrix.json（54 EUTs） |
| branch_inventory.json | q05a/branch_inventory.json（9 targets，30 branches） |
| business_outcomes.json | q05a/business_outcomes.json（30 outcomes） |
| eut_matrix.md | q05a/eut_matrix.md |
| reasoning_log.md | q05a/reasoning_log.md |

---

## 覆盖分布

| 路径类型 | EUT 数量 |
|---------|---------|
| Happy Path | 10 |
| Exception | 9 |
| Boundary | 5 |
| Concurrent | 1 |
| 合计 | 25 |

| 风险等级 | EUT 数量 |
|---------|---------|
| T1（高风险，核心业务） | 22 |
| T2（中风险，边界防御） | 3 |

---

## EUT 摘要

### 核心业务路径（T1）

1. **故障原因编辑主流程**（EUT-001~006）：涵盖 Happy Path（无BPM直接更新）、BPM拦截、SKU互斥拦截、名称重复拦截、最后有效原因校验。这是本次需求最高密度的校验逻辑。
2. **故障原因品类配置**（EUT-007~008）：启用/禁用品类的 Happy Path 和有数据时的拦截场景。
3. **批量修改故障原因**（EUT-009~010）：全量合法的 Happy Path 和触发「最后有效原因」校验的 Exception。
4. **类型管理双向校验**（EUT-016~017）：已开启故障原因品类不能设置软件故障第1/2级，未开启则允许。
5. **BPM 审批流程**（EUT-018~019）：修改故障原因名称的审批通过和解析失败场景。
6. **状态聚合关键场景**（EUT-020~022）：并发唯一性、边界状态聚合、binlog触发聚合。

### 关键语义验证（SE）

- **SE-001 并发唯一性**（EUT-020）：并发创建同名故障原因，只允许一个成功。
- **SE-002 底表状态聚合**（EUT-021）：最后有效关系置无效后底表状态自动为无效。
- **SE-003 两层状态独立**（EUT-024）：故障现象状态变更不影响故障原因关系状态。
- **SE-007 批量上限**（EUT-025）：超 5000 条数据上传被拦截。

---

## 不可测项（7 项）

| 需求 | 原因 | 建议处置 |
|------|------|---------|
| REQ-007 | 批量导出，无核心分支 | 集成测试 |
| REQ-009 | 互斥规则由系统配置实现 | 系统配置 + 人工验证 |
| REQ-010 | XMS 跨系统接口 | 接口联调测试 |
| REQ-011 + SE-006 | 灰度实现机制未定（GAP-001） | 待 GAP-001 解决后补测 |
| SE-005 | SKU 互斥需全请求上下文 | 集成测试 |
| SE-008 | AS 工单互斥，不在本仓库 | AS 工单系统单独测 |

---

## 风险说明

1. **EUT-025（SE-007）**：FaultServiceImpl.importFaultBrandClassData 方法名需与代码确认，可能方法名有差异。
2. **EUT-020（SE-001 并发）**：需在测试环境具备并发支持（如 @RepeatedTest + CountDownLatch）。
3. **EUT-024（SE-003）**：需集成两张表（base_fault_relationship_ext 和 base_fault_reason_relation）进行验证，可能属于集成测试范畴。

---

## 下一步

Q05b：根据本矩阵生成 Java 单测代码，覆盖 EUT-001 到 EUT-025，重点关注：
- FaultReasonFacadeImpl 的核心校验逻辑（EUT-001~010）
- 并发 EUT-020
- 状态聚合 EUT-021~022
