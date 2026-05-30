# Q05a EUT 矩阵设计报告 — wmx-logistic-exchange

## 结论

**通过（含不可测项）**

37条EUT覆盖8个核心变更类，涵盖全部T1风险分支。共有多类场景属于集成测试范畴，无法在单元测试层覆盖（已在不可测项中说明）。

---

## 机器产物索引

| 产物 | 路径 |
|------|------|
| EUT 矩阵JSON | artifacts/wmx-logistic-exchange/q05a/eut_matrix.json |
| EUT 矩阵MD | artifacts/wmx-logistic-exchange/q05a/eut_matrix.md |
| 分支清单 | artifacts/wmx-logistic-exchange/q05a/branch_inventory.json |
| 业务后果映射 | artifacts/wmx-logistic-exchange/q05a/business_outcomes.json |
| code_index | artifacts/wmx-logistic-exchange/q05a/code_index.json |
| 推理日志 | artifacts/wmx-logistic-exchange/q05a/reasoning_log.md |

---

## 覆盖分布

| 路径类型 | EUT 数量 |
|---------|---------|
| Happy Path | 8 |
| Exception | 14 |
| Boundary | 6 |
| **合计** | **37** |

| 风险层级 | EUT 数量 |
|---------|---------|
| T1（必测） | 26 |
| T2（建议测） | 2 |

---

## EUT 摘要

| 目标类 | EUT数量 | 核心风险场景 |
|--------|--------|------------|
| LogisticExchangeIdentifyManager | 12 | 三段式识别全路径（品类短路、黑名单、时间、履约中心异常降级） |
| ExchangeOrderService | 4 | 换新单OC扩展参数组装（特批、照片） |
| Cn3cCreateTagExt | 2 | 建单T2打标（换货/非换货） |
| Cn3cProcessExtendTagExt | 3 | 检测处理T8重新识别和清标 |
| Cn3cProcessMethodValidateExt | 5 | 处理方法门控（配置缺失防呆、禁止方法） |
| OrderCenterConsumer | 2 | OC取消回传分叉（物流取旧送新/普通取消） |

---

## 不可测项

1. **REQ-002**（工单流变更）：强安装品类工单流路由依赖工作流引擎，集成测试覆盖
2. **SE-009**：同上
3. **REQ-005**（XMS展示）：展示层，前端集成测试
4. **REQ-006全链路**：妥投消息全链路，集成测试；OrderCenterConsumer消费者侧分支通过EUT-027间接覆盖
5. **REQ-008**（拒收换）：OPEN-001未解决，拒绝设计不确定性EUT

---

## 风险说明

1. **GAP-001（HIGH）**：`logistic_exchange_enable_time`配置项上线前必须配置，否则所有工单识别结果为false，功能无法生效。EUT-009已覆盖此边界。
2. **EUT-025**（允许方法未配置防呆）：如数据字典未配置`logistic_exchange_only_detect_method`，物流取旧送新工单无法提交处理方法，功能完全不可用。

---

## 下一步

进入 Q05b：依照本 EUT 矩阵（37条），在目标仓库 `maf-srv-service/src/test/` 中生成 JUnit 5 + Mockito 测试代码。

需优先实现：
1. LogisticExchangeIdentifyManagerTest（12条，T1核心）
2. Cn3cProcessMethodValidateExtTest（5条，BR-005门控）
3. OrderCenterConsumerTest（2条，取消路径分叉）
4. ExchangeOrderServiceTest（4条，OC扩展组装）
5. Cn3cCreateTagExtTest + Cn3cProcessExtendTagExtTest（5条，打标/清标）
