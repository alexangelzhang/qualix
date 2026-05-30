# Q06 测试覆盖审计报告 — wmx-logistic-exchange

## 审计结论

**PASS_WITH_RISKS**

37条 EUT 全部审计，36条 COVERED，1条 PARTIAL（EUT-037 特批查询异常降级断言较弱）。测试代码通过 static-verify 验证（文件和方法存在性），但因项目构建环境预存在 API 不兼容问题，未经过真实 Maven 运行验证（FINDING-004）。

---

## 增量覆盖率门禁结果

| 指标 | 要求 | 实际 |
|------|------|------|
| 增量行覆盖率 | ≥85% | N/A（coverage_required=false，无 JaCoCo 报告）|
| 增量分支覆盖率 | ≥85% | N/A |

**风险**：未运行 JaCoCo，无法量化覆盖率数字。按语义覆盖分析，关键目标类（LogisticExchangeIdentifyManager、ExchangeOrderService、Cn3c Extension 类、OrderCenterConsumer）的核心分支均有 EUT 覆盖，预期覆盖率达标，但需研发修复 API 不兼容后运行 JaCoCo 确认。

---

## Coverage / Mutation 证据

- **JaCoCo**：未执行（coverage_required=false）
- **PIT Mutation**：未执行（mutation_required=false）
- **语义覆盖**：基于 Q05a EUT 矩阵设计，37条 EUT 覆盖 7个目标类的关键分支

---

## 按目标类的增量覆盖率

| 目标类 | EUT数 | COVERED | PARTIAL | 风险 |
|--------|------|---------|---------|------|
| LogisticExchangeIdentifyManager | 14 | 14 | 0 | 低 |
| ExchangeOrderService | 7 | 6 | 1 | 中（EUT-037） |
| Cn3cCreateTagExt | 3 | 3 | 0 | 低 |
| Cn3cProcessExtendTagExt | 4 | 4 | 0 | 低 |
| Cn3cProcessMethodValidateExt | 5 | 5 | 0 | 低 |
| OrderCenterConsumer | 3 | 3 | 0 | 低 |
| LogisticExchangeIdentifyParam | 1 | 1 | 0 | 低 |

---

## Findings

### FINDING-001（WARNING）
**EUT-037 断言较弱**：特批查询异常时降级逻辑的断言未验证 special_approval_id='' 的具体结果。
- **业务后果**：若 querySpecialApprovalByServiceNo 的 try-catch 降级失效，special_approval_id 可能为 null，导致 OC 接口解析异常。
- **下一步**：在 `assembleLogisticExchangeOrderParams_approvalSearchThrows_doesNotThrow` 中补充 special_approval_id='' 的断言。

### FINDING-002（INFO）
**OPEN-001/002 未覆盖**：拒收换流程（REQ-008）和物流取消后 SN 再建单规则（BR-010）因 Q01 OPEN 项未解决，未设计 EUT。
- **下一步**：产品拍板后补充 EUT 和测试。

### FINDING-003（INFO）
**enable_time 格式错误路径未覆盖**：`isLogisticExchangeEnabled` 中 `DateUtil.strToDate` 返回 null 的异常路径（格式错误）未被测试。
- **下一步**：可添加 enableTimeStr='invalid-format' 场景的边界测试。

### FINDING-004（WARNING）
**构建环境限制**：项目存在预存在编译错误（RoleService/UserBaseManager API 不兼容），测试代码未经 Maven 运行验证，使用 static-verify 作为证据。
- **业务后果**：测试代码本身可能存在编译错误（如类引用错误）而未被发现。
- **下一步**：修复 CommonSrvService.java、SrvCustomerUpdateService.java、TimeoutWarningService.java 的 API 调用后，运行 `mvn test -Dtest="LogisticExchangeIdentifyManagerTest,..."`。

---

## 未覆盖场景说明

| 需求 | 原因 | 处理 |
|------|------|------|
| REQ-002（强安装工单流变更） | 工作流引擎，集成测试范畴 | 已在不可测项中说明 |
| REQ-005（XMS物流展示） | 前端展示，集成测试 | 已在不可测项中说明 |
| REQ-006（妥投全链路） | MQ消费者全链路，集成测试 | 已在不可测项中说明 |
| REQ-008（拒收换） | OPEN-001未解决 | FINDING-002 |

---

## 下一步

1. 研发修复 API 不兼容问题后运行完整 Maven 测试并获取 JaCoCo 报告
2. 补充 EUT-037 的断言强度（FINDING-001）
3. 待产品拍板 OPEN-001/002 后补充 EUT（FINDING-002）
4. 可选：添加 enable_time 格式错误边界测试（FINDING-003）
