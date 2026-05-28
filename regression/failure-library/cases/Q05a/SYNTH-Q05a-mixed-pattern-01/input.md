# Quality Judge — Phase Q05a: EUT 矩阵设计

## 评估目标

基于原始输入、Phase 产物、Gate Checklist 和已知失败案例，判断本 Phase 输出是否满足质量门禁。

## Gate Checklist（通过标准）

- [x] 三层驱动目标模块完整
- [x] 每条 REQ/BR/SE 都有对应 EUT
- [x] git diff 每个实现类都出现在某条 EUT 的 when 字段
- [ ] then 字段包含具体断言（部分 SE-aggregated EUT 的 then 为泛化描述）

## 评审输入

### EUT 矩阵（20 条，混合模式）

大多数 EUT 符合逐条模式，但 SE-006/SE-007/SE-008 被合并为一条聚合 EUT。

| EUT ID | 被测类 | 路径类型 | 绑定项 | then |
|--------|--------|---------|-------|------|
| EUT-001 | LogisticExchangeIdentifyManager | Exception | SE-001 | assertEquals(false, result); verify(fulfillmentRuleInterfaceService, never()).isSendAndInstallSupport(...) |
| EUT-002 | LogisticExchangeIdentifyManager | Happy Path | SE-001 | assertEquals(true, result); verify(fulfillmentRuleInterfaceService, times(1)).isSendAndInstallSupport(...) |
| EUT-003 | Cn3cProcessMethodValidateExt | Exception | SE-003 | assertThrows(BizException.class, () -> ext.validateMethod(domainModel, processMethod)) |
| EUT-004 | Cn3cProcessMethodValidateExt | Happy Path | SE-003 | assertEquals(0, capturedExceptions.size()) |
| EUT-005 | ExchangeOrderService | Exception | SE-005 | assertThrows(BizException.class, () -> service.createExchangeOrder(request)) |
| EUT-006 | ExchangeOrderService | Happy Path | SE-005 | verify(exchangeOrderRepository, times(1)).save(any(ExchangeOrder.class)); assertEquals(orderId, result.getOrderId()) |
| EUT-SE-BATCH | LogisticExchangeIdentifyManager | Mixed | SE-006, SE-007, SE-008 | 验证批量查询接口（SE-006）、非物流取旧送新返回 false（SE-007）、接口异常降级处理（SE-008）均正确 |
| EUT-007 | ExchangeOrderService | Exception | SE-009 | assertThrows(NullPointerException.class, () -> service.createExchangeOrderForSingleOrder(null, null, null)) |
| EUT-008 | DetectionProcessSrvService | Happy Path | SE-010 | verify(srvSecondVisitManager, never()).createSecondVisit(any()); assertEquals(WorkflowState.SWITCHED, state) |
| EUT-009 | DetectionProcessSrvService | Exception | SE-010 | assertThrows(BizException.class, () -> service.processDetectionResult(workflowContext)) |
| EUT-010 | OrderCenterConsumer | Happy Path | SE-011 | verify(srvDetailDubboServiceImpl, times(1)).closeSrv(orderNo, opCode, userId); assertEquals(SrvState.SERVICE_COMPLETED, finalState) |
| EUT-011 | OrderCenterConsumer | Exception | SE-011 | assertThrows(ProcessException.class, () -> consumer.handleCancelMessage(message)) |
| EUT-012 | DetectionProcessSrvVoBuilder | Happy Path | SE-004 | verify(storageOrderService, never()).createStorageOrder(any()); assertEquals(0, storageOrderList.size()) |
| EUT-013 | GenericConfigDataManager | Happy Path | BR-001 | assertEquals(Arrays.asList("cat001", "cat002"), result.getCategoryWhitelist()) |
| EUT-014 | GenericConfigDataManager | Boundary | BR-002 | assertEquals(Collections.emptyList(), result) |
| EUT-015 | OrderCenterConsumer | Happy Path | BR-016 | verify(xmsRouteService, times(1)).addRouteNode(routeNodeDTO); assertEquals(RouteNodeType.SEND_NEW, node.getType()) |
| EUT-016 | OrderCenterConsumer | Exception | BR-019 | verify(logisticCallbackService, times(1)).cancelCallback(orderNo); assertEquals(CancelReason.SITE_CANCEL, reason) |
| EUT-017 | LogisticExchangeIdentifyManager | Happy Path | SE-002 | assertEquals(true, result); verify(fulfillmentRuleInterfaceService, times(1)).isSendAndInstallSupport(...) |
| EUT-018 | VisitSrvService | Exception | SE-002 | assertThrows(BizException.class, () -> service.reIdentifyTagForVisit(srvNo, brandCode, processMethod)) |
| EUT-019 | Cn3cProcessExtendTagExt | Boundary | BR-008 | assertEquals("LOGISTIC_EXCHANGE", tagResult.getTagCode()); assertTrue(tagResult.getIsEnabled()) |

**总计：20 条 EUT（包含 1 条 SE 聚合：EUT-SE-BATCH 覆盖 SE-006+SE-007+SE-008）**

### 铁律违反说明

- EUT-SE-BATCH 将 SE-006、SE-007、SE-008 合并为单条，绑定项格式为"SE-006, SE-007, SE-008"
- 路径类型填写为"Mixed"而非具体的 Happy/Exception/Boundary
- then 字段为泛化文字描述，未包含具体断言方法和期望值
- 其余 19 条 EUT 均符合标准（EUT-based 逐条模式，强断言）

## BUG_CASES — 已知判错案例（务必避免重犯）

### 反例 1: SE-based 聚合 [铁律违反]

**教训**: Q05a 必须 EUT 逐条模式，禁止将多个 SE 合并为一条 EUT

## 开始评审

请逐个维度评审。注意：大多数 EUT 格式正确，但 EUT-SE-BATCH 是隐藏的 SE-based 聚合违规。
