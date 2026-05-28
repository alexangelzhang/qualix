# Quality Judge — Phase Q05a: EUT 矩阵设计

## 评估目标

基于原始输入、Phase 产物、Gate Checklist 和已知失败案例，判断本 Phase 输出是否满足质量门禁。

## Gate Checklist（通过标准）

- [x] 三层驱动目标模块完整
- [x] 每条 REQ/BR/SE 都有对应 EUT
- [x] git diff 每个实现类都出现在某条 EUT 的 when 字段
- [ ] then 字段包含具体断言（非模糊描述）

## 评审输入

### EUT 矩阵（产物节选，28 条，路径类型正确但 then 字段均为泛化描述）

| EUT ID | 被测类 | 路径类型 | 绑定项 | then |
|--------|--------|---------|-------|------|
| EUT-001 | LogisticExchangeIdentifyManager | Exception | SE-001 | 验证品类不支持时接口不被调用 |
| EUT-002 | LogisticExchangeIdentifyManager | Happy Path | SE-001 | 验证品类支持时接口被正常调用且返回正确 |
| EUT-003 | LogisticExchangeIdentifyManager | Exception | SE-006 | 验证批量查询中非物流取旧送新返回 false |
| EUT-004 | LogisticExchangeIdentifyManager | Exception | BR-001 | 验证品类白名单配置正确生效 |
| EUT-005 | LogisticExchangeIdentifyManager | Happy Path | BR-001 | 验证在白名单内时品类校验通过 |
| EUT-006 | LogisticExchangeIdentifyManager | Boundary | BR-002 | 验证 SKU 黑名单配置边界正确 |
| EUT-007 | Cn3cProcessMethodValidateExt | Happy Path | SE-003 | 验证强校验通过的场景正常运行 |
| EUT-008 | Cn3cProcessMethodValidateExt | Exception | SE-003 | 验证强校验失败时抛出异常 |
| EUT-009 | Cn3cProcessMethodValidateExt | Exception | SE-003 | 验证普通换货时强校验逻辑正确 |
| EUT-010 | LogisticExchangeIdentifyManager | Happy Path | SE-006 | 验证批量查询服务接口正常返回 |
| EUT-011 | LogisticExchangeIdentifyManager | Happy Path | SE-007 | 验证非物流取旧送新时返回正确值 |
| EUT-012 | LogisticExchangeIdentifyManager | Exception | SE-008 | 验证接口异常时降级处理正确 |
| EUT-013 | SrvCommonDubboServiceImpl | Exception | SE-008 | 验证降级后主流程不受影响 |
| EUT-014 | LogisticExchangeIdentifyManager | Happy Path | SE-002 | 验证能力识别第一次正常执行 |
| EUT-015 | VisitSrvService | Exception | SE-002 | 验证能力识别第二次强校验异常场景 |
| EUT-016 | ExchangeOrderService | Happy Path | SE-005 | 验证换货单创建正常流程 |
| EUT-017 | ExchangeOrderService | Exception | SE-005 | 验证换货单创建异常场景处理正确 |
| EUT-018 | ExchangeOrderService | Boundary | SE-009 | 验证 null 参数边界处理正确 |
| EUT-019 | OrderCenterConsumer | Happy Path | SE-011 | 验证物流取消后工单状态正确更新 |
| EUT-020 | OrderCenterConsumer | Exception | SE-011 | 验证物流取消异常场景处理正确 |
| EUT-021 | DetectionProcessSrvService | Happy Path | SE-010 | 验证强安装场景工单流切换正确 |
| EUT-022 | SrvSecondVisitManager | Exception | SE-010 | 验证不生成二次上门换新工单逻辑正确 |
| EUT-023 | DetectionProcessSrvVoBuilder | Happy Path | SE-004 | 验证物流取旧送新工单跳过入库单生成 |
| EUT-024 | GenericConfigDataManager | Happy Path | BR-001 | 验证品类白名单查询接口正确 |
| EUT-025 | GenericConfigDataManager | Boundary | BR-006 | 验证 1仓/7仓 SKU 黑名单边界 |
| EUT-026 | OrderCenterConsumer | Happy Path | BR-016 | 验证 XMS 展示送新单路由节点正确 |
| EUT-027 | OrderCenterConsumer | Exception | BR-019 | 验证网点取消 XMS 工单后回传正确 |
| EUT-028 | OrderCenterConsumer | Happy Path | BR-020 | 验证物流侧取消后 XMS 取消原工单 |

**总计：28 条 EUT，路径类型分布正常（Happy:10 Exception:13 Boundary:5）**

### 铁律违反说明

本产物的 then 字段**全部为泛化描述**：
- 无 assertEquals(期望值, 实际值)
- 无 assertThrows(异常类型, () -> ...)
- 无 verify(mock, times(N)).methodName(...)
- 所有描述均为"验证...正确""验证...通过"等无法直接转代码的文本
- 这使单测工程师无法直接从 EUT 生成可执行的单测代码

## BUG_CASES — 已知判错案例（务必避免重犯）

### 反例 1: eut_items.87.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

## 开始评审

请逐个维度评审，重点检查 then 字段是否包含可验证的断言方法和期望值。
