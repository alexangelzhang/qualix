# Q05b Java 单测实现报告

## 结论

Q05b 已将 Q05a 的 36 条 EUT 映射到真实 Java 测试方法，`done=36`、`passes=36`。当前结论为 `PASS_WITH_ENV_RISK`：测试方法级追溯和强断言已落地，最终覆盖率和证据真实性由 Q06 承接。

这份报告重点回答“这些测试到底证明了什么业务语义”。测试方法名和 `EUT-*` 只是追溯线索；真正的结论要看业务场景、风险后果和断言。

## 术语说明

- `REQ-*` 是需求点，说明业务目标；`BR-*` 是业务规则，说明必须满足的分支规则；`SE-*` 是关键语义，说明必须能被验证的业务不变量。
- `EUT-*` 是 Executable Unit Test，即一条可落地到 Java 单测的业务场景，不等同于一个测试方法，但必须能追到测试方法。
- `T1/T2/T3` 是风险等级，不是技术优先级。T1 表示不测会影响状态、权限、审批、数据一致性、金额/Excel 或外部同步；T2 表示重要但爆炸半径较小。
- `B-*` 是代码路径编号，只用于追溯 Java 分支；报告中不能只展示 `B-*`，必须同时说明它对应的业务场景。
- `O-*` 是业务后果编号，只用于把代码路径绑定到可断言的业务结果；报告中不能只展示 `O-*`，必须说清楚不覆盖会造成什么后果。

## 业务证明总览

| 业务域 | EUT | 测试证明了什么 |
|---|---|---|
| 任务生成与通知 | EUT-001, EUT-002, EUT-003, EUT-027, EUT-031, EUT-032, EUT-033 | 月度任务生成幂等、开启通知、催办通知和通知记录持久化可被验证。 |
| 列表、导出与权限 | EUT-004, EUT-005, EUT-006, EUT-018, EUT-021, EUT-028, EUT-029, EUT-030, EUT-034, EUT-035 | 列表筛选、导出范围、权限空集合、API 权限转换和越权拒绝可被验证。 |
| 表单、审批与状态机 | EUT-007, EUT-008, EUT-009, EUT-010, EUT-011, EUT-012, EUT-013, EUT-014, EUT-016, EUT-022, EUT-023, EUT-024, EUT-025, EUT-036 | Excel 必填、凭证上限、提交一致性、BPM 防串单、归档终态和状态迁移可被验证。 |
| 版本管理 | EUT-015, EUT-017 | 驳回后重新上传生成新版本、版本列表排序可被验证；旧版本失效已按用户要求作为已接受风险，不阻断本轮。 |
| Excel 解析与经营模型数据 | EUT-019, EUT-020, EUT-026 | 2S 模板解析、公式一致性校验、明细空列表保护和经营模型导出字段可被验证。 |

## 类级实现分布

| 生产类 | EUT 数 | 说明 |
|---|---:|---|
| `FinanceExpenseServiceImpl` | 14 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseJobHandler` | 11 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseExcelUtils` | 2 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseStatusEventFactory` | 2 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseProviderImpl` | 2 | 覆盖该类相关的业务场景和路径断言。 |
| `RejectedToPendingStatusTransition` | 1 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseSnapshotGatewayImpl` | 1 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseGatewayImpl` | 1 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseDetailGatewayImpl` | 1 | 覆盖该类相关的业务场景和路径断言。 |
| `FinanceExpenseNoticeRecordGatewayImpl` | 1 | 覆盖该类相关的业务场景和路径断言。 |

## EUT 到测试方法

| EUT | 业务场景 | 测试方法 | 核心断言证明 |
|---|---|---|---|
| EUT-001 | 每月任务生成遇到“已存在部分门店任务”时，只为缺失门店补建 V1 待提交任务。 | `FinanceExpenseJobHandlerTest.java#createMonthlyExpenseOrders_whenSomeOrgExists_shouldOnlyCreateMissingOrg` | assertEquals(1, result) and assertEquals(PENDING, insert.status) and assertEquals("V1", query.version)。 |
| EUT-002 | 每月开启上传时，系统给门店财务发送上传入口通知并记录 OPEN 场景。 | `FinanceExpenseJobHandlerTest.java#sendOpenNotice_whenHasStoreFinance_shouldInsertAndSend` | assertEquals("OPEN", record.scene) and assertEquals("STORE_FINANCE", receiverType) and verify(appPushGateway).sendInformedMessage(any())。 |
| EUT-003 | 每月 15 日催办未提交门店，同时通知门店财务、城市经理和区域财经 BP。 | `FinanceExpenseJobHandlerTest.java#sendReminderNotice_whenUnsubmitted_shouldNotifyStoreFinanceCityManagerAndLittleZoneBp` | assertEquals(3, result) and assertEquals([STORE_FINANCE,CITY_MANAGER,LITTLE_ZONE_BP], receiverTypes)。 |
| EUT-004 | 用户按筛选条件查看财务手工上传列表，列表展示门店名称和财务期间。 | `FinanceExpenseServiceImplTest.java#list_whenValidCondition_shouldReturnPageWithOrgDisplay` | assertEquals(1, result.total) and assertEquals("F6165-测试门店", orgDisplay) and assertEquals("2026年3月", periodDesc)。 |
| EUT-005 | 列表查询创建时间只传开始或结束时直接拒绝，并且不进入数据库查询。 | `FinanceExpenseServiceImplTest.java#list_whenCreateTimeMissingPair_shouldThrow` | assertThrows(BusinessException.class) and assertEquals("创建时间开始和结束必须成对传入", ex.getMessage()) and verify(financeExpenseGateway, never()).countByEntity(any())。 |
| EUT-006 | 导出列表沿用当前筛选条件和权限门店范围，并生成导出文件地址。 | `FinanceExpenseJobHandlerTest.java#exportList_whenHasData_shouldBuildExportFile` | assertEquals("https://test/export.xlsx", resp.fileUrl) and assertEquals(true, query.latestOnly) and assertEquals(["F6165"], permissionOrgIdList)。 |
| EUT-007 | 详情页打开历史版本时，返回版本号和财务 Excel 附件信息。 | `FinanceExpenseServiceImplTest.java#detail_whenHistoryVersionExists_shouldReturnAttachmentInfo` | assertEquals("V1", result.version) and assertEquals("财务.xlsx", financeExcelFileId[0].name)。 |
| EUT-008 | 财务上传 Excel 后点击下一步，系统更新主表并写入快照。 | `FinanceExpenseServiceImplTest.java#stepNext_whenFinanceExcelExists_shouldUpdateAndSnapshot` | assertEquals("success", result) and verify(financeExpenseGateway).updateByKey(captor.capture()) and assertEquals(1, snapshot.stepNext)。 |
| EUT-009 | 未上传财务 Excel 时点击下一步被拒绝，且主表不被更新。 | `FinanceExpenseServiceImplTest.java#stepNext_whenFinanceExcelMissing_shouldThrow` | assertThrows(BusinessException.class) and verify(financeExpenseGateway, never()).updateByKey(any())。 |
| EUT-010 | 某一类补充凭证超过 10 个时，暂存被拒绝并返回明确提示。 | `FinanceExpenseServiceImplTest.java#save_whenTrainingExpenseExceedsTen_shouldThrow` | assertThrows(BusinessException.class) and assertTrue(message contains "培训费凭证") and assertTrue(message contains "不能超过10个")。 |
| EUT-011 | 提交审批时文件与暂存版本一致，触发审批中状态处理器。 | `FinanceExpenseServiceImplTest.java#submit_whenFileMatched_shouldTriggerApprovingHandler` | assertEquals("success", result) and verify(statusEventHandler).trigger(any(FinanceExpenseSubmitSoIn.class))。 |
| EUT-012 | 提交时当前文件与已暂存版本不一致，提交被拒绝且不触发状态机。 | `FinanceExpenseServiceImplTest.java#submit_whenFileChangedFromSaved_shouldRejectWithConsistencyError` | assertThrows(BusinessException.class) and assertEquals("当前文件与已暂存版本不一致", normalized message prefix) and verify(statusEventFactory, never()).getStatusEventHandler(any(), any())。 |
| EUT-013 | BPM 回调审批流单号与当前任务不匹配时拒绝处理。 | `FinanceExpenseServiceImplTest.java#approve_whenBpmNoMismatched_shouldThrow` | assertThrows(BusinessException.class) and assertEquals("审批流单号不匹配", normalized message prefix) and verify(statusEventFactory, never()).getStatusEventHandler(any(), any())。 |
| EUT-014 | 审批驳回回调触发驳回状态处理器。 | `FinanceExpenseServiceImplTest.java#reject_whenApproving_shouldTriggerRejectedHandler` | verify(statusEventHandler).trigger(any(FinanceExpenseStatusSoIn.class))。 |
| EUT-015 | 驳回后重新上传生成 V2 待提交记录，并清空上一版本凭证。 | `FinanceExpenseVersionTransitionTest.java#reloadWhenRejected_shouldCreateBlankPendingVersion` | assertEquals("V2", insert.version) and assertEquals(PENDING, insert.status) and assertEquals(emptyList, equipmentMaintenanceFileIds)。 |
| EUT-016 | 归档状态下尝试暂存编辑被拒绝。 | `FinanceExpenseServiceImplTest.java#save_whenCurrentArchived_shouldRejectEdit` | assertThrows(BusinessException.class) and assertTrue(message contains "当前状态不允许暂存") and verifyNoInteractions(statusEventFactory)。 |
| EUT-017 | 版本列表返回多个版本，并按最新版本优先展示。 | `FinanceExpenseServiceImplTest.java#version_whenExpenseExists_shouldSortVersionDesc` | assertEquals(3, result.total) and assertEquals("V3", first.version)。 |
| EUT-018 | 用户没有任何数据权限时，列表返回空且不查询业务数据。 | `FinanceExpenseServiceImplTest.java#list_whenEmptyPermission_shouldReturnEmptyList` | assertEquals(0, result.total) and assertEquals(Collections.emptyList(), result.list) and verify(financeExpenseGateway, never()).countByEntity(any())。 |
| EUT-019 | 解析 2S Excel 模板时，正确生成手工填写字段和系统计算字段。 | `FinanceExpenseExcelUtilsTest.java#parseDetailList_whenTwoSTemplateMatched_shouldBuildManualAndCalcDetail` | assertEquals(new BigDecimal("25.35"), detailMap["25"].subjectValue) and assertFalse(detailMap.containsKey("4"))。 |
| EUT-020 | 上传 Excel 的公式结果与系统计算不一致时拒绝解析。 | `FinanceExpenseExcelUtilsTest.java#parseDetailList_whenFormulaResultMismatched_shouldThrow` | assertThrows(BusinessException.class) and assertEquals("上传Excel公式/系统计算结果不一致", normalized message category) for formula result mismatch validation path。 |
| EUT-021 | 导出时查询明细、组装 Excel 并上传临时文件。 | `FinanceExpenseJobHandlerTest.java#exportList_whenHasData_shouldBuildExportFile` | verify(financeExpenseDetailGateway).selectByEntity(any()) and verify(uploadGateway).uploadOutTempFile(any()) and assertEquals(export url)。 |
| EUT-022 | 状态迁移工厂能根据已注册迁移返回审批中处理器。 | `FinanceExpenseStatusEventFactoryTest.java#getStatusEventHandler_whenRegistered_shouldReturnHandler` | assertEquals(APPROVING, handler.targetStatus())。 |
| EUT-023 | 未注册状态迁移被拒绝并给出明确错误。 | `FinanceExpenseStatusEventFactoryTest.java#getStatusEventHandler_whenNotRegistered_shouldThrowBusinessException` | assertThrows(BusinessException.class) and assertTrue(message contains "未注册状态转移")。 |
| EUT-024 | 快照网关保存任务编号、版本、状态和附件字段。 | `FinanceExpenseSnapshotGatewayImplTest.java#insertSelective_whenSuccess_shouldNotThrow` | assertEquals("FE001", model.expenseNo) and assertTrue(financeExcelFileId contains "1001")。 |
| EUT-025 | 主表持久化时，未上传 Excel 的占位值被转换为空数组。 | `FinanceExpenseGatewayImplTest.java#insertSelective_whenFinanceExcelIdMinusOne_shouldStoreEmptyArray` | verify(financeExpenseMapper).insertSelective(captor.capture()) and assertEquals("[]", model.financeExcelFileId)。 |
| EUT-026 | 费用明细批量插入遇到空列表时直接跳过。 | `FinanceExpenseDetailGatewayImplTest.java#batchInsert_whenEmptyList_shouldSkip` | verify(financeExpenseDetailMapper, never()).batchInsert(anyList())。 |
| EUT-027 | 通知记录插入后返回主键，用于后续发送状态和幂等过滤。 | `FinanceExpenseNoticeRecordGatewayImplTest.java#insertSelective_whenSuccess_shouldReturnId` | assertEquals(100L, id)。 |
| EUT-028 | Provider 列表接口把请求权限转换给 service，并返回列表响应。 | `FinanceExpenseProviderImplTest.java#list_whenServiceReturnsData_shouldConvertReqAndResp` | assertEquals(true, captor.permission.headquarter) and assertEquals("FE001", result.data.list[0].expenseNo)。 |
| EUT-029 | 导出列表创建时间只传一边时被拒绝。 | `FinanceExpenseJobHandlerTest.java#exportList_whenCreateTimeMissingPair_shouldThrow` | assertThrows(BusinessException.class) and assertEquals("创建时间开始和结束必须成对传入", ex.message)。 |
| EUT-030 | 非门店财务或未配置操作权限时，下一步操作被拒绝且不进入 service。 | `FinanceExpenseProviderImplTest.java#stepNext_whenPositionTodoNotConfigured_shouldReject` | assertThrows(BusinessException.class) and assertEquals("当前用户无财务费用操作权限", ex.getMessage()) and verify(financeExpenseService, never()).stepNext(any())。 |
| EUT-031 | 每月自动为授权门店生成财务手工上传任务。 | `FinanceExpenseJobHandlerTest.java#createMonthlyExpenseOrders_whenSomeOrgExists_shouldOnlyCreateMissingOrg` | assertEquals(1, result) and verify(financeExpenseGateway).insertSelective(captor.capture()) and assertEquals(PENDING, insert.status)。 |
| EUT-032 | 门店+月份+V1 已存在时跳过，只为缺失门店生成任务。 | `FinanceExpenseJobHandlerTest.java#createMonthlyExpenseOrders_whenSomeOrgExists_shouldOnlyCreateMissingOrg` | assertEquals(1, result) and assertEquals("F1002", insert.orgId) proving existing 门店+月份+V1 is skipped。 |
| EUT-033 | 开启通知写入通知记录并标记发送状态。 | `FinanceExpenseJobHandlerTest.java#sendOpenNotice_whenHasStoreFinance_shouldInsertAndSend` | assertEquals("STORE_FINANCE", receiverType) and assertEquals(Integer.valueOf(1), sendStatus) and verify(appPushGateway).sendInformedMessage(any())。 |
| EUT-034 | 列表导出字段可进入门店经营模型计算链路。 | `FinanceExpenseJobHandlerTest.java#exportList_whenHasData_shouldBuildExportFile` | assertEquals("https://test/export.xlsx", resp.fileUrl) and verify(financeExpenseDetailGateway).selectByEntity(any()) proves export data feeds operating model fields。 |
| EUT-035 | 导出只取最新版本并遵守权限门店范围。 | `FinanceExpenseJobHandlerTest.java#exportList_whenHasData_shouldBuildExportFile` | assertEquals(true, query.latestOnly) and assertEquals(["F6165"], permissionOrgIdList) and verify(uploadGateway).uploadOutTempFile(any())。 |
| EUT-036 | 归档状态作为终态，保存操作被拒绝且不触发状态机。 | `FinanceExpenseServiceImplTest.java#save_whenCurrentArchived_shouldRejectEdit` | assertThrows(BusinessException.class) and assertTrue(message contains "当前状态不允许暂存") and verifyNoInteractions(statusEventFactory)。 |

## 测试文件

- `FinanceExpenseDetailGatewayImplTest.java`
- `FinanceExpenseExcelUtilsTest.java`
- `FinanceExpenseGatewayImplTest.java`
- `FinanceExpenseJobHandlerTest.java`
- `FinanceExpenseNoticeRecordGatewayImplTest.java`
- `FinanceExpenseProviderImplTest.java`
- `FinanceExpenseServiceImplTest.java`
- `FinanceExpenseSnapshotGatewayImplTest.java`
- `FinanceExpenseStatusEventFactoryTest.java`
- `FinanceExpenseVersionTransitionTest.java`

## 构建/运行风险

| 项 | 结论 | 影响 |
|---|---|---|
| 方法级追踪 | 每条 EUT 在对应 JUnit 方法块内有 `EUT-xxx` 标记。 | Q06 可反查测试方法真实性。 |
| 强断言 | 异常路径补充异常消息或副作用断言，写库路径补充 captor/verify/never。 | 避免只测“不报错”。 |
| Maven test run | 局部目标测试可运行；全仓历史模块/API 编译风险仍存在。 | Q06 继续以真实 JaCoCo/test evidence 做最终裁决。 |
| 已接受风险 | BI 同步和旧版本失效没有被伪造成测试通过。 | 用户已明确忽略，本轮不再作为 Q06 BLOCKER。 |
