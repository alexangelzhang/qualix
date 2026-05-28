# Quality Judge — Phase Q05a: EUT 矩阵设计

## 评估目标

基于原始输入、Phase 产物、Gate Checklist 和已知失败案例，判断本 Phase 输出是否满足质量门禁。
结论必须由证据支撑；没有原文引用或文件依据的判断一律视为不成立。

## Gate Checklist（通过标准）

- [x] 三层驱动目标模块完整（se_mappings + br_mappings + git_diff_files 全部非空）
- [x] 每条 REQ/BR/SE 都有对应 EUT（bound_item 非空，100% 覆盖）
- [x] git diff 每个实现类都出现在某条 EUT 的 when 字段（C10 无 BLOCKED）
- [x] then 字段包含具体断言（非模糊描述）

## 行为约束

- 每个结论都必须引用具体证据；没有引用的结论不能计入评分依据
- 不接受'基本覆盖''整体还行'这类无法验证的模糊表述
- 主动寻找漏报（FN）、错判、虚构和证据不足，不为已有产物辩护
- 不修复产物，只输出评审结论

## 评审规则

1. 每个评分维度按 1-5 分 Likert 量表打分，严格对照每级标准。
2. 漏报（FN）比误报（FP）更严重 — 宁可多报不可漏报。
3. 必须对照原始输入逐条验证，不能只看输出的自洽性。
4. 每个维度必须列出具体的扣分证据（引用原文位置）。

## 评审维度 + 检查清单（compose_rubric 生成）

### req_coverage: 需求覆盖完备性
EUT 矩阵是否覆盖了所有 REQ/BR/SE，每条需求都有对应的 EUT 条目
  - 5分: 每条 REQ、BR、SE 都有至少一个对应 EUT，bound_item 字段引用准确
  - 4分: 90%+ REQ/BR/SE 有对应 EUT，仅遗漏 1-2 个非关键语义点

### code_path_projection: 代码路径覆盖投影
EUT 矩阵对目标类的 Happy/Exception/Boundary/Concurrent 路径是否达到 100% 投影覆盖
  - 5分: 所有目标类的路径均有 EUT 覆盖
  - 4分: Happy+Exception 路径全覆盖，Boundary 仅遗漏 1-2 个

### assertion_quality: 断言描述质量
EUT 的 then 字段是否包含具体可验证的断言语义
  - 5分: 所有 EUT 的 then 包含具体断言方法和期望值
  - 4分: 90%+ then 字段是具体断言，个别条目描述稍泛化

### git_diff_coverage: git diff 变更覆盖
feature branch 新增/修改的每个实现类是否都出现在至少一条 EUT 的 when 字段中
  - 5分: git diff 变更的所有实现类均出现在 EUT 的 when 字段
  - 4分: 90%+ 变更类有 EUT 覆盖

## 评审输入

Phase 产物：

### 三层驱动目标模块（全部满足）

**SE 驱动（11 条 SE，全部 found=True）**

| SE ID | 描述 | 实现类 |
|-------|------|-------|
| SE-001 | 品类不支持物流取旧送新时不调用履约中心接口 | LogisticExchangeIdentifyManager / SrvCommonDubboServiceImpl |
| SE-002 | 能力识别两次（建单+待上门→待服务），第二次结果用于强校验 | VisitSrvService / LogisticExchangeIdentifyManager |
| SE-003 | 工单提交强校验：仅同时满足物流送新拉旧=支持+处理方法=上门换新仅检测才允许提交 | Cn3cProcessMethodValidateExt |
| SE-004 | 工单业务完成生成入库单时，物流取旧送新工单跳过入库单生成 | DetectionProcessSrvVoBuilder |
| SE-005 | 换货单创建：ExchangeOrderService.createExchangeOrder | ExchangeOrderService |
| SE-006 | batchCheckLogisticExchange：批量判断服务单是否为物流取旧送新 | LogisticExchangeIdentifyManager |
| SE-007 | 批量查询中非物流取旧送新服务单返回 false | LogisticExchangeIdentifyManager |
| SE-008 | 履约中心/能力识别接口异常时降级，不阻断主流程 | LogisticExchangeIdentifyManager / SrvCommonDubboServiceImpl |
| SE-009 | createExchangeOrderForSingleOrder null 参数抛异常 | ExchangeOrderService |
| SE-010 | 强安装+物流取旧送新时工单流切换——不生成二次上门换新工单 | DetectionProcessSrvService / SrvSecondVisitManager |
| SE-011 | 已换货完成后物流原因取消：工单日志写入且终态=服务完成 | OrderCenterConsumer / SrvDetailDubboServiceImpl |

**git diff 有逻辑文件覆盖（14/14 = 100%）**

| 文件 | 是否有逻辑 | 测试类 | EUT 数量 |
|------|---------|-------|---------|
| LogisticExchangeIdentifyManager.java | ✅ | LogisticExchangeIdentifyManagerTest | 22 |
| OrderCenterConsumer.java | ✅ | OrderCenterConsumerTest | 29 |
| ExchangeOrderService.java | ✅ | ExchangeOrderServiceTest | 14 |
| GenericConfigDataManager.java | ✅ | GenericConfigDataManagerLogisticTest | 9 |
| Cn3cProcessMethodValidateExt.java | ✅ | Cn3cProcessMethodValidateExtTest | 8 |
| Cn3cProcessExtendTagExt.java | ✅ | Cn3cProcessExtendTagExtTest | 7 |
| Cn3cCreateTagExt.java | ✅ | Cn3cCreateTagExtTest | 5 |
| VisitSrvService.java | ✅ | VisitSrvServiceReIdentifyTagTest | 5 |
| DetectionProcessSrvService.java | ✅ | DetectionProcessSrvServiceWmsExchangeTest | 3 |
| SrvCommonDubboServiceImpl.java | ✅ | SrvCommonDubboServiceImplLogisticTest | 11 |
| SrvDetailDubboServiceImpl.java | ✅ | SrvDetailDubboServiceImplLogisticTest | 4 |
| SrvSecondVisitManager.java | ✅ | SrvSecondVisitManagerTest | 4 |
| DetectionProcessSrvVoBuilder.java | ✅ | DetectionProcessSrvVoBuilderTest | 1 |
| ExchangeSrvVo.java | ✅ | ExchangeSrvVoTest | 1 |

### EUT 矩阵概要（120 条，EUT 逐条模式）

**统计：**
- Happy Path：44 条
- Exception：52 条
- Boundary：24 条
- 强断言（assertEquals/assertThrows/verify）：117/120（97.5%）
- 泛化描述（可能需补强）：3/120（EUT-118、EUT-119、EUT-120）

**样本（前 15 条 + 典型 Exception/Boundary 各 3 条）：**

| EUT ID | 被测类 | 路径类型 | 绑定项 | then（摘要） |
|--------|--------|---------|-------|-----------|
| EUT-001 | LogisticExchangeIdentifyManager | Exception | SE-001 | assertEquals(false, result); verify(fulfillmentRuleInterfaceService, never()).isSendAndInstallSupport(...) |
| EUT-002 | LogisticExchangeIdentifyManager | Happy Path | SE-001 | assertEquals(true, result); verify(fulfillmentRuleInterfaceService, times(1)).isSendAndInstallSupport(...) |
| EUT-003 | LogisticExchangeIdentifyManager | Exception | SE-006 | assertEquals(false, result); verify(genericConfigDataManager, times(1)).isLogisticExchangeGoodsAllowed(...) |
| EUT-004 | LogisticExchangeIdentifyManager | Exception | BR-001 | assertEquals(false, result) |
| EUT-005 | LogisticExchangeIdentifyManager | Happy Path | BR-001 | assertEquals(true, result) |
| EUT-006 | LogisticExchangeIdentifyManager | Boundary | BR-002 | assertEquals(false, result) |
| EUT-007 | Cn3cProcessMethodValidateExt | Happy Path | SE-003 | assertEquals(0, capturedExceptions.size()) |
| EUT-008 | Cn3cProcessMethodValidateExt | Exception | SE-003 | assertThrows(BizException.class, () -> ext.validateMethod(domainModel, processMethod)) |
| EUT-009 | Cn3cProcessMethodValidateExt | Exception | SE-003 | assertThrows(BizException.class, () -> ext.validateMethod(domainModel, processMethod, 普通换货)) |
| EUT-010 | LogisticExchangeIdentifyManager | Happy Path | SE-006 | assertEquals(true, result) |
| EUT-011 | LogisticExchangeIdentifyManager | Happy Path | SE-007 | assertEquals(false, result); verify(genericConfigDataManager, times(1)).isLogisticExchangeGoodsAllowed(...) |
| EUT-012 | LogisticExchangeIdentifyManager | Exception | SE-008 | assertEquals(false, result) |
| EUT-013 | SrvCommonDubboServiceImpl | Exception | SE-008 | verify(srvCommonDubboService, times(1)).fulfillmentRuleQuery(...); assertFalse(result.getIsLogisticExchange()) |
| EUT-014 | LogisticExchangeIdentifyManager | Happy Path | SE-002 | assertEquals(true, result); verify(fulfillmentRuleInterfaceService, times(1)).isSendAndInstallSupport(...) |
| EUT-015 | VisitSrvService | Exception | SE-002 | assertThrows(BizException.class, () -> service.reIdentifyTagForVisit(srvNo, brandCode, processMethod)) |
| EUT-050 | ExchangeOrderService | Exception | SE-005 | assertThrows(BizException.class, () -> service.createExchangeOrder(request)) |
| EUT-051 | ExchangeOrderService | Exception | SE-009 | assertThrows(NullPointerException.class, () -> service.createExchangeOrderForSingleOrder(null, null, null)) |
| EUT-080 | OrderCenterConsumer | Exception | SE-011 | verify(srvDetailDubboServiceImpl, times(1)).closeSrv(orderNo, opCode, userId); assertEquals(SrvState.SERVICE_COMPLETED, state) |
| EUT-095 | OrderCenterConsumer | Boundary | SE-011 | verify(orderCenterConsumer, times(1)).handleCancelMessage(message) |
| EUT-100 | GenericConfigDataManager | Boundary | BR-006 | assertEquals(Collections.emptyList(), result) |
| EUT-118 | SrvDetailDubboServiceImpl | Boundary | BR-005 | assertFalse(labels.contains(SrvTagEnum.LOGISTIC_EXCHANGE.getName())) |

## BUG_CASES — 已知判错案例（务必避免重犯）

以下是 Phase Q05a 与当前输入最相关的历史判错案例。

### 反例 1: eut_items.87.then [漏报]

**教训**: EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述

### 反例 2: eut_items.12 [漏报]

**教训**: Skill 规则未覆盖此失败场景，需要补充检查项

### 反例 3: eut_items.58 [漏报]

**教训**: Skill 规则未覆盖此失败场景，需要补充检查项

## 开始评审

请逐个维度评审，对照上述产物内容给出评分和总体判定。
