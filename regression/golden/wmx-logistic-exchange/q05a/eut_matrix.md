# EUT 矩阵明细报告 — wmx-logistic-exchange

## 一、目标模块发现过程

### diff 文件四类归档

**real_diff_files（30个）**：通过 `git diff master..HEAD --name-only` 获得30个生产Java文件。

**included_diff_files（8个）**：含核心业务逻辑分支，纳入EUT设计：

| 文件 | 关联需求 |
|------|---------|
| LogisticExchangeIdentifyManager.java | REQ-001, BR-001/002/003/011 |
| LogisticExchangeIdentifyParam.java | REQ-001 |
| ExchangeOrderService.java | REQ-004, BR-007/008 |
| GenericConfigDataManager.java | REQ-001, BR-001/002 |
| Cn3cCreateTagExt.java | REQ-001, BR-003 |
| Cn3cProcessExtendTagExt.java | REQ-003 |
| Cn3cProcessMethodValidateExt.java | REQ-003, BR-005 |
| OrderCenterConsumer.java | REQ-006/007, SE-010 |

**excluded_diff_files（22个）**：枚举/接口/DTO/Dubbo API层，无独立业务分支，通过上层集成覆盖。

**scope_conflicts（0个）**：无冲突。

---

## 二、需求到代码映射

| 需求ID | 类名 | 方法名 | 证据 |
|--------|------|--------|------|
| REQ-001 | LogisticExchangeIdentifyManager | identifyByPrecheckAndFulfillment | .java:100 |
| REQ-001 | Cn3cCreateTagExt | processLogisticExchangeTag | .java:191 |
| BR-001 | LogisticExchangeIdentifyManager | passPrecheck | .java:65 |
| BR-002 | LogisticExchangeIdentifyManager | passPrecheck | .java:70 |
| BR-003 | Cn3cCreateTagExt | processLogisticExchangeTag | .java:191 |
| BR-005 | Cn3cProcessMethodValidateExt | checkLogisticExchangeOnlyDetectMethod | .java |
| BR-007 | ExchangeOrderService | querySpecialApprovalByServiceNo | .java:530 |
| BR-008 | ExchangeOrderService | collectScenePhotos | .java |
| BR-011 | LogisticExchangeIdentifyManager | isLogisticExchangeEnabled | .java:153 |
| REQ-003 | Cn3cProcessExtendTagExt | reIdentifyAndMarkLogisticExchange | .java |
| REQ-004 | ExchangeOrderService | assembleLogisticExchangeOrderParams | .java:526 |
| REQ-007 | OrderCenterConsumer | addExchangeOrderCancelProcess | .java |
| SE-003 | LogisticExchangeIdentifyManager | identifyByPrecheckAndFulfillment | .java:130 |
| SE-010 | OrderCenterConsumer | addExchangeOrderCancelProcess | .java |

---

## 三、EUT 矩阵

### LogisticExchangeIdentifyManager

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-001 | Happy Path | REQ-001 | 三段式全通过 | 返回true，履约中心调用1次 | T1 |
| EUT-002 | Exception | BR-001 | 品类不在白名单 | 返回false，履约中心未调用 | T1 |
| EUT-003 | Exception | BR-002 | SKU在黑名单 | 返回false | T1 |
| EUT-004 | Boundary | REQ-001 | brandClassId=null | 返回false | T1 |
| EUT-005 | Boundary | REQ-001 | goodsId='' | 返回false | T1 |
| EUT-006 | Exception | SE-003 | 履约中心抛异常 | 返回false，无异常传播 | T1 |
| EUT-007 | Boundary | REQ-001 | param=null | 返回false，无NPE | T1 |
| EUT-008 | Exception | SE-004 | 工单创建时间早于enable_time | 返回false，履约中心未调用 | T1 |
| EUT-009 | Boundary | SE-005 | enable_time未配置 | 返回false | T1 |
| EUT-010 | Boundary | BR-011 | createTime=null | 返回false，无NPE | T1 |
| EUT-011 | Exception | SE-008 | 多商品任一在黑名单 | 返回false | T1 |
| EUT-012 | Happy Path | SE-008 | 多商品全不在黑名单 | 返回true | T1 |

### ExchangeOrderService

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-013 | Happy Path | REQ-004 | 有特批记录 | ocExtendList含unified_replacement=2,special_approval_id=特批ID | T1 |
| EUT-014 | Boundary | SE-007 | 无特批记录 | special_approval_id=''，无异常 | T1 |
| EUT-015 | Happy Path | BR-008 | 有附件含重复URL | 返回去重URL列表 | T1 |
| EUT-016 | Boundary | BR-008 | 无附件 | 返回空列表，无异常 | T2 |

### Cn3cCreateTagExt

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-017 | Happy Path | BR-003 | 换货工单识别通过 | save(LOGISTIC_EXCHANGE, Y)调用1次 | T1 |
| EUT-018 | Exception | BR-003 | 非换货工单 | LOGISTIC_EXCHANGE标签未保存 | T1 |

### Cn3cProcessExtendTagExt

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-019 | Happy Path | REQ-003 | 检测处理重新识别通过 | save(LOGISTIC_EXCHANGE, Y) | T1 |
| EUT-020 | Exception | REQ-003 | 工单类型切换为非换货 | delete(LOGISTIC_EXCHANGE)调用 | T1 |
| EUT-021 | Exception | REQ-003 | 选择不予处理 | delete(LOGISTIC_EXCHANGE)调用 | T1 |

### Cn3cProcessMethodValidateExt

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-022 | Happy Path | BR-005 | 选择允许方法 | 正常返回无异常 | T1 |
| EUT-023 | Exception | BR-005 | 选择禁止方法 | MafSrvAftersaleException | T1 |
| EUT-024 | Exception | BR-005 | 选择多个方法 | 抛异常含'单个处理方法' | T1 |
| EUT-025 | Boundary | BR-005 | allowedMethodIds未配置 | 抛异常含'处理方法未配置' | T1 |
| EUT-026 | Happy Path | BR-005 | 非物流取旧送新工单 | 不校验，正常通过 | T1 |

### OrderCenterConsumer

| EUT-ID | 路径类型 | 绑定需求 | 场景 | 断言 | 风险 |
|--------|---------|---------|------|------|------|
| EUT-027 | Happy Path | SE-010 | 物流取旧送新取消回传 | addCancelProcess调用，closeByOrderStatus未调用，processExchangeDoAndBackCustomer调用 | T1 |
| EUT-028 | Exception | REQ-007 | 非物流取旧送新取消 | closeByOrderStatus调用（原逻辑） | T1 |

---

## 四、不可测项

| 需求 | 原因 |
|------|------|
| REQ-002（工单流变更） | 强安装工单流分支依赖工作流引擎，属于集成测试 |
| SE-009（强安装工单流） | 同上 |
| REQ-005（XMS物流展示） | 展示层逻辑，属于前端集成测试 |
| REQ-006（妥投闭环全链路） | 全链路集成测试，EUT-027覆盖消费者侧分支 |
| REQ-008（拒收换） | OPEN-001未解决，无法设计确定性EUT |

---

## 五、自我评审记录

**第一轮：** 发现遗漏了Cn3cCreateTagExt非换货工单分支（EUT-018）、allowedMethodIds为空的防呆测试（EUT-025）。已补全。

**批评者复查：** OrderCenterConsumer的非物流取旧送新取消路径（EUT-028）很关键——如果这个分支不存在，所有普通换货取消都走错路。已纳入。
