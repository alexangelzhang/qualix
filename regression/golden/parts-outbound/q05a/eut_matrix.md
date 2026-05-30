# Q05a EUT 矩阵明细

## 设计原则

围绕 Q01 的 REQ/BR/SE 与真实 Java diff 双维度设计。每条 EUT 都绑定具体业务场景、目标类、分支和强断言蓝图；索赔/预授权展示被单独列为可追踪场景。

## Diff 归档

- real_diff_files: 100 个生产 Java 文件。
- included_diff_files: 8 个核心业务文件。
- excluded_diff_files: 92 个字段承载、转换层或相邻传播文件，已逐项记录原因。
- scope_conflicts: 0 个。

## EUT 矩阵

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| `EUT-001` | QuoteService 收到支持小数且单价为整数元的配件，numDecimal=1.50。 | Happy Path / T1 | QuoteService / QuoteService.validatePartDecimalSupport(detail, partSsuInfo) | assertDoesNotThrow，随后 verify(mrItemService).storageMrItemModel(any()) 被允许进入保存链路。 | REQ-001 B-004 |
| `EUT-002` | QuoteService 查询到配件主数据 supportDecimal=1。 | Happy Path / T1 | QuoteService / QuoteService.populateSupportDecimal(relations, ssuInfoMap) | assertEquals(1, relation.getSupportDecimal())，证明输入/展示能力由主数据标记驱动。 | BR-001 B-008 |
| `EUT-003` | QuoteService 收到 numDecimal=1.50，精度正好两位。 | Happy Path / T1 | QuoteService / QuoteService.validateNumDecimal(detail) | assertDoesNotThrow，assertEquals(new BigDecimal("1.50"), detail.getNumDecimal())。 | BR-002 B-001 |
| `EUT-004` | QuoteService 收到 numDecimal=1.234，超过两位精度。 | Exception / T1 | QuoteService / QuoteService.validateNumDecimal(detail) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("精度不能超过2位")。 | BR-002 B-003 |
| `EUT-005` | 服务行动提交包含配件 ssuCountDecimal=1.50，商品主数据支持小数且价格为整数元。 | Happy Path / T1 | ActionAggregateFactory / ActionAggregateFactory.checkSsuCountDecimal(ssuEntities) and ActionAggregateFactory.checkDecimalPartsPrice(ssuEntities) | assertDoesNotThrow，assertEquals(1, ssuEntities.get(0).getSupportDecimal())，服务行动聚合继续创建。 | BR-005 B-031,B-037 |
| `EUT-006` | MrOrderDetailProviderImpl 查询到工单配件使用数量 numDecimal=1.50。 | Happy Path / T1 | MrOrderDetailProviderImpl / MrOrderDetailProviderImpl.queryPartRepair(request) | assertEquals(new BigDecimal("1.50"), result.getData().getRows().get(0).getPartNumberDecimal())。 | REQ-002 B-047 |
| `EUT-007` | 报价单详情 relations 中存在小数出库配件。 | Happy Path / T1 | QuoteService / QuoteService.populateSupportDecimal(relations, ssuInfoMap) | assertEquals(1, relation.getSupportDecimal())，报价单展示可按支持小数处理。 | BR-007 B-008 |
| `EUT-008` | MrDetailPerfectServiceImpl 组装端侧工单详情，工时和配件均带 numDecimal=1.50。 | Happy Path / T1 | MrDetailPerfectServiceImpl / MrDetailPerfectServiceImpl.detailMrPerfect(mid, status, type, orgPhoneFuture, superTicketBo, superTicketDetail, entity) | assertEquals(new BigDecimal("1.50"), entity.getMrDetailInfo().getItems().get(0).getItemDetails().get(0).getNumDecimal())。 | BR-008 B-050 |
| `EUT-009` | 索赔/预授权相关页面通过配件维修/工单详情链路读取小数配件数量，底层 item.numDecimal=1.50。 | Happy Path / T1 | MrOrderDetailProviderImpl / MrOrderDetailProviderImpl.queryPartRepair(request) and MrDetailPerfectServiceImpl.detailMrPerfect(...) | assertEquals(new BigDecimal("1.50"), partNumberDecimal)，assertEquals(new BigDecimal("1.50"), partInfo.getNumDecimal())，索赔/预授权展示不取整。 | BR-009 B-047,B-050 |
| `EUT-010` | 退款提交中小数配件请求数量等于可退数量，amountResult 已计算配件金额。 | Happy Path / T1 | MrRefundServiceImpl / MrRefundServiceImpl.validatePartRefund(reqPart, refundablePart) and MrRefundServiceImpl.buildRefundBOWithAmount(...) | assertDoesNotThrow，assertEquals(amountResult.getPartSumPrice().longValue(), refundBO.getPartRefundSumPrice())。 | REQ-003 B-010,B-019 |
| `EUT-011` | 用户请求退款数量 2.00，大于可退数量 1.50。 | Exception / T1 | MrRefundServiceImpl / MrRefundServiceImpl.validatePartRefund(reqPart, refundablePart) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("退款数量超过可退数量")。 | BR-011 B-011 |
| `EUT-012` | 支持小数且使用数量为 1.50 的配件，用户只退 1.00。 | Exception / T1 | MrRefundServiceImpl / MrRefundServiceImpl.validatePartRefund(reqPart, refundablePart) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("只允许全额退款")，verify(refundGateway, never()).submit(any())。 | BR-012 B-012 |
| `EUT-013` | 支持小数但使用数量为整数 2，用户退 1。 | Happy Path / T1 | MrRefundServiceImpl / MrRefundServiceImpl.calculatePartRefundAmount(reqPart, refundablePart) | assertEquals(unitSelfPayAmount, amount)，不会强制全额退款。 | BR-013 B-015 |
| `EUT-014` | 报价/工单添加支持小数出库配件，但商品主数据 price=101 分。 | Exception / T1 | QuoteService / QuoteService.validatePartDecimalSupport(detail, partSsuInfo) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("单价不是整数元")。 | REQ-004 B-007 |
| `EUT-015` | 直接绕过前端向后端提交不支持小数的配件 numDecimal=1.50。 | Exception / T1 | QuoteService / QuoteService.validatePartDecimalSupport(detail, partSsuInfo) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("不支持小数数量")，后端防绕过生效。 | BR-014 B-006 |
| `EUT-016` | 服务项组套包含单价含小数的支持小数配件，配件名为 A。 | Exception / T1 | MrItemSetService / MrItemSetService.validateDecimalRules(itemGroupDTO) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("配件A").contains("单价不是整数元")。 | BR-015 B-026 |
| `EUT-017` | 小数出库标记为否的配件被传入 numDecimal=1.50。 | Exception / T1 | QuoteService / QuoteService.validatePartDecimalSupport(detail, partSsuInfo) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("不支持小数数量")。 | SE-001 B-006 |
| `EUT-018` | 支持小数且使用数量为 1.50 的退款页面提交部分退款。 | Exception / T1 | MrRefundServiceImpl / MrRefundServiceImpl.validatePartRefund(reqPart, refundablePart) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("只允许全额退款")。 | SE-003 B-012 |
| `EUT-019` | 支持小数但使用数量为整数 2 的退款页面提交 1 件部分退款。 | Happy Path / T1 | MrRefundServiceImpl / MrRefundServiceImpl.calculatePartRefundAmount(reqPart, refundablePart) | assertEquals(unitSelfPayAmount, amount)，assertEquals(1, reqPart.getRefundNum())。 | SE-004 B-015 |
| `EUT-020` | 服务行动候选配件 supportDecimal=1 且 marketPrice=101 分。 | Exception / T1 | SsuItemService / SsuItemService.queryCarMaintenanceSsu(req) and ActionAggregateFactory.checkDecimalPartsPrice(ssuEntities) | assertThat(resp.getMaintenanceSsuDto()).doesNotContain(badSsu)，直接提交时 assertThrows(BusinessException.class)。 | SE-005 B-039,B-045 |
| `EUT-021` | 服务项组套包含配件A、配件B 两个单价含小数配件。 | Exception / T1 | MrItemSetService / MrItemSetService.validateDecimalRules(itemGroupDTO) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("配件A").contains("配件B")，用于暴露当前实现若只提示单个配件的风险。 | SE-006 B-026 |
| `EUT-022` | 报价单、工单、退款、索赔/预授权、服务行动、车辆档案的后端详情对象均携带 numDecimal=1.50。 | Happy Path / T1 | MrDetailPerfectServiceImpl / MrOrderDetailProviderImpl.queryPartRepair(request) and MrDetailPerfectServiceImpl.detailMrPerfect(...) and SsuItemService.queryCarMaintenanceSsu(req) | assertEquals(new BigDecimal("1.50"), partNumberDecimal/numDecimal)，assertThat(serviceActionResp).extracting("ssuCountDecimal").contains(new BigDecimal("1.50"))。 | SE-008 B-047,B-050,B-040 |
| `EUT-023` | QuoteService 收到 numDecimal=0 或 -1。 | Exception / T1 | QuoteService / QuoteService.validateNumDecimal(detail) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("必须大于0")。 | BR-002 B-002 |
| `EUT-024` | QuoteService/MrRefundServiceImpl/MrDetailPerfectServiceImpl 遇到空列表、旧单据 numDecimal=null、非目标状态。 | Boundary / T2 | QuoteService / QuoteService.populateSupportDecimal(empty, emptyMap) and MrRefundServiceImpl.queryRefundInfoByRefundNo(refundNo) and MrDetailPerfectServiceImpl.detailMrPerfect(...) | assertDoesNotThrow，assertEquals(BigDecimal.valueOf(num), fallbackDecimal)，assertNull(entity.getMrDetailInfo())。 | REQ-002 B-005,B-009,B-018,B-051,B-055,B-057 |
| `EUT-025` | 历史支持小数配件存在非整数元价格脏数据，但退款数量合法。 | Boundary / T2 | MrRefundServiceImpl / MrRefundServiceImpl.validatePartRefund(reqPart, refundablePart) | assertDoesNotThrow，assertEquals(refundablePart.getSelfPayAmount(), calculatePartRefundAmount(...))，只记录 warn 不阻断。 | REQ-003 B-013,B-014 |
| `EUT-026` | 查询退款详情时原单配件 numDecimal=1.50，refundNumDecimal 同步返回。 | Happy Path / T1 | MrRefundServiceImpl / MrRefundServiceImpl.queryRefundInfoByRefundNo(refundNo) | assertEquals(new BigDecimal("1.50"), refundInfo.getPartList().get(0).getNumDecimal())。 | REQ-003 B-016 |
| `EUT-027` | 退款单查询不到审批明细。 | Exception / T2 | MrRefundServiceImpl / MrRefundServiceImpl.queryRefundInfoByRefundNo(refundNo) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("无审批明细")。 | REQ-003 B-017 |
| `EUT-028` | 服务项组套无配件 ssuId、服务行动空 ssuEntities、SsuItem 关键词无结果。 | Boundary / T2 | MrItemSetService / MrItemSetService.validateDecimalRules(itemGroupDTO) and ActionAggregateFactory.checkSsuCountDecimal(emptyList) and SsuItemService.queryCarMaintenanceSsu(req) | assertDoesNotThrow，verify(goodsServiceGateway, never()).pageCarMaintenanceSsu(any())，assertEquals(0L, resp.getTotal())。 | BR-005 B-020,B-027,B-032,B-038,B-041,B-044,B-046,B-059,B-060 |
| `EUT-029` | 服务行动配件数量为空、非正数、超过两位或主数据不支持小数。 | Exception / T1 | ActionAggregateFactory / ActionAggregateFactory.checkSsuCountDecimal(ssuEntities) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("配件数量") 或 contains("不支持小数数量")。 | BR-005 B-033,B-034,B-035,B-036 |
| `EUT-030` | ActionAggregateFactory 收到非法 actionType 或缺少必填基础参数。 | Exception / T2 | ActionAggregateFactory / ActionAggregateFactory.factoryByAction(actionType, req, logList) | assertThrows(BusinessException.class)，verify(actionGateway, never()).save(any())。 | BR-005 B-029 |
| `EUT-031` | ActionAggregateFactory 处理纯工时或空配件列表。 | Boundary / T2 | ActionAggregateFactory / ActionAggregateFactory.factoryByAction(actionType, req, logList) | assertDoesNotThrow，verify(goodsServiceGateway, never()).pageCarMaintenanceSsu(emptyList)。 | BR-005 B-030,B-061,B-062 |
| `EUT-032` | 服务行动保存入口携带合法小数配件，factoryByAction 应进入保存聚合。 | Happy Path / T1 | ActionAggregateFactory / ActionAggregateFactory.factoryByAction(OptionType.SAVE, req, logList) | assertSame(expectedApplyClass, result.getClass())，verify(goodsServiceGateway).pageCarMaintenanceSsu(any())。 | BR-005 B-028 |
| `EUT-033` | SsuItemService 查询服务行动可选配件，结果包含合法小数配件并过滤坏价格配件。 | Happy Path / T1 | SsuItemService / SsuItemService.queryCarMaintenanceSsu(req) and SsuItemService.queryAssociationBySsu(ssuId, engCarType) and SsuItemService.isDecimalWithNonIntegerYuanPrice(ssu) | assertThat(resp.getMaintenanceSsuDto()).extracting("ssuId").contains(goodSsuId).doesNotContain(badSsuId)，assertTrue(filterBad)。 | BR-005 B-040,B-042,B-045 |
| `EUT-034` | 配件维修/端侧详情查询的领域服务抛 BusinessException 或未知异常，或结算关键金额异常。 | Exception / T2 | MrOrderDetailProviderImpl / MrOrderDetailProviderImpl.queryPartRepair(request) and MrDetailPerfectServiceImpl.detailMrPerfect(...) | assertEquals(errorCode, result.getCode())，assertEquals(GeneralCodes.ParamError, genericResult.getCode())，assertThrows(BusinessException.class)。 | REQ-002 B-048,B-049,B-052 |
| `EUT-035` | MrDetailPerfectServiceImpl 的 orgPhoneFuture 等异步输入已完成，两个线程同时请求同一详情对象。 | Concurrent / T2 | MrDetailPerfectServiceImpl / ExecutorService + CountDownLatch invoke MrDetailPerfectServiceImpl.detailMrPerfect(...) | assertEquals(1, entity.getMrDetailInfo().getItems().size())，assertEquals(new BigDecimal("1.50"), partInfo.getNumDecimal())，小数数量不因并发 future 丢失。 | REQ-002 B-053 |
| `EUT-036` | 服务项组套 detail.numDecimal=0 或 1.234。 | Exception / T1 | MrItemSetService / MrItemSetService.validateSingleNumDecimal(numDecimal) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("必须大于0") 或 contains("精度不能超过2位")。 | BR-005 B-021,B-022 |
| `EUT-037` | 服务项组套嵌套配件 numDecimal=1.50，主数据 supportDecimal=1 且 price=100。 | Happy Path / T1 | MrItemSetService / MrItemSetService.validateSingleNumDecimal(numDecimal) and MrItemSetService.validateDecimalRules(itemGroupDTO) | assertDoesNotThrow，verify(goodsServiceGateway).pageCarMaintenanceSsu(any())。 | BR-005 B-023,B-024 |
| `EUT-038` | 服务项组套内配件主数据 supportDecimal=0 但请求 numDecimal=1.50。 | Exception / T1 | MrItemSetService / MrItemSetService.validateDecimalRules(itemGroupDTO) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("不支持小数数量")。 | SE-006 B-025 |
| `EUT-039` | QuoteService 商品中台未返回 ssuInfo，SsuItemService 查询非配件或价格为空。 | Boundary / T2 | QuoteService / QuoteService.validatePartDecimalSupport(detail, emptyMap) and SsuItemService.isDecimalWithNonIntegerYuanPrice(ssu) | assertDoesNotThrow，assertFalse(filterResult)，不误伤正常工时或缺价格数据。 | REQ-004 B-005,B-046,B-058 |
| `EUT-040` | SsuItemService 查询关联工时时商品中台没有返回任何可用工时/配件。 | Exception / T2 | SsuItemService / SsuItemService.queryAssociationBySsu(ssuId, engCarType) | assertThrows(BusinessException.class)，assertThat(e.getMessage()).contains("暂无可用工时/配件")。 | BR-005 B-043 |
| `EUT-041` | 退款和展示工具收到 numDecimal=1.50，旧整数字段 num=1。 | Happy Path / T2 | NumberUtil / NumberUtil.getDecimalValue(numDecimal, num) and NumberUtil.toIntValue(numDecimal) | assertEquals(new BigDecimal("1.50"), decimalValue)，assertEquals(2, NumberUtil.toIntValue(new BigDecimal("2.00")))。 | BR-002 B-054,B-056 |
| `EUT-042` | SsuItemService 查询服务行动配件时，关键词无匹配、关联配件为空，或候选项为非配件/价格为空。 | Boundary / T2 | SsuItemService / SsuItemService.queryCarMaintenanceSsu(req) and SsuItemService.queryAssociationBySsu(ssuId, engCarType) and SsuItemService.isDecimalWithNonIntegerYuanPrice(ssu) | assertEquals(0L, resp.getTotal())，assertTrue(itemDetails.isEmpty())，assertFalse(filterResult)。 | BR-005 B-041,B-044,B-046 |
| `EUT-043` | MrOrderDetailProviderImpl 查询配件维修列表时 pageBo.rows 为空。 | Boundary / T2 | MrOrderDetailProviderImpl / MrOrderDetailProviderImpl.queryPartRepair(request) | assertEquals(pageBo.getPageSize(), resp.getPageSize())，assertTrue(resp.getRows() == null || resp.getRows().isEmpty())。 | REQ-002 B-064 |
| `EUT-044` | MrDetailPerfectServiceImpl 收到非详情补全状态、itemAndPayInfo=null 或历史空数量。 | Boundary / T2 | MrDetailPerfectServiceImpl / MrDetailPerfectServiceImpl.detailMrPerfect(mid, status, type, orgPhoneFuture, superTicketBo, superTicketDetail, entity) | assertNull(entity.getMrDetailInfo())，assertDoesNotThrow，历史空数量不写出错误小数。 | REQ-002 B-051,B-063 |
| `EUT-045` | NumberUtil 收到 numDecimal=null 或待判断字符串为空。 | Boundary / T2 | NumberUtil / NumberUtil.getDecimalValue(null, num) and NumberUtil.toIntValue(null) and NumberUtil.isGreaterThanZero(null) | assertEquals(new BigDecimal("2"), decimalValue)，assertNull(intValue)，assertFalse(NumberUtil.isGreaterThanZero(null))。 | BR-002 B-055,B-057,B-065 |
| `EUT-046` | NumberUtil 收到非法数字字符串。 | Exception / T2 | NumberUtil / NumberUtil.isGreaterThanZero("abc") | assertThrows(NumberFormatException.class)，assertEquals("abc", originalInput)，防止脏数量被静默当作合法数量且不修改原输入。 | BR-002 B-066 |

## 复杂方法覆盖策略

- `QuoteService.validatePartDecimalSupport`：line_count=19，branch_signal_count=5，策略：按合法、ssuInfo 缺失、防绕过 unsupported decimal、非整数元价格和防御 return 五类场景覆盖。
- `MrRefundServiceImpl.validatePartRefund`：line_count=27，branch_signal_count=7，策略：拆为超可退、真小数部分退、历史脏价告警和合法退款四类 EUT。
- `MrRefundServiceImpl.queryRefundInfoByRefundNo`：line_count=111，branch_signal_count=19，策略：只围绕小数数量展示、缺审批异常、历史整数回退三个业务风险设计，其他展示字段由既有测试覆盖。
- `MrRefundServiceImpl.buildRefundBOWithAmount`：line_count=91，branch_signal_count=2，策略：聚焦金额汇总字段，快照字段通过已有退款测试补齐。
- `MrItemSetService.validateSingleNumDecimal`：line_count=15，branch_signal_count=5，策略：按 null、防御 return、非正、超两位、合法值四类场景覆盖。
- `MrItemSetService.validateDecimalRules`：line_count=53，branch_signal_count=12，策略：围绕嵌套配件合法、unsupported decimal、非整数价格、空配件四类风险拆分。
- `ActionAggregateFactory.factoryByAction`：line_count=93，branch_signal_count=17，策略：入口工厂只验证小数校验被接入，具体数量/价格分支下钻到 checkSsuCountDecimal/checkDecimalPartsPrice。
- `ActionAggregateFactory.checkSsuCountDecimal`：line_count=55，branch_signal_count=14，策略：按空列表、空数量、非正、超精度、unsupported decimal、合法六类场景覆盖。
- `ActionAggregateFactory.checkDecimalPartsPrice`：line_count=30，branch_signal_count=6，策略：按空列表/空 ssuId、商品缺失、合法整数元、非整数元拒绝四类场景覆盖。
- `MrDetailPerfectServiceImpl.detailMrPerfect`：line_count=104，branch_signal_count=11，策略：仅覆盖与小数展示和详情补全稳定性相关的 happy/boundary/exception/concurrency，金额细节沿用既有测试。

## 自我评审记录

- 已确认 PRD 6.6 的索赔/预授权展示点在 EUT-009/EUT-022 中显式出现。
- 已确认 proretail-claim 无生产 Java diff，不生成 phantom EUT。
- 已为每条 EUT 写入 assertion_blueprint.expected_source。
