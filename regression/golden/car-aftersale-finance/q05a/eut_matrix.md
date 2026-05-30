# Q05a EUT 矩阵

## 这张矩阵怎么读

矩阵的设计原则是“业务语义和代码路径同时闭环”：先从 Q01 的 REQ/BR/SE 识别必须证明的业务语义，再找到 Java 类/方法和分支路径，最后写成可执行单测场景。

每行先说明业务场景和风险后果，再给出 Java 目标和断言。`B-*`、`O-*` 只用于机器追溯，不需要读者先理解这些编号才能看懂场景。

## 术语说明

- `REQ-*` 是需求点，说明业务目标；`BR-*` 是业务规则，说明必须满足的分支规则；`SE-*` 是关键语义，说明必须能被验证的业务不变量。
- `EUT-*` 是 Executable Unit Test，即一条可落地到 Java 单测的业务场景，不等同于一个测试方法，但必须能追到测试方法。
- `T1/T2/T3` 是风险等级，不是技术优先级。T1 表示不测会影响状态、权限、审批、数据一致性、金额/Excel 或外部同步；T2 表示重要但爆炸半径较小。
- `B-*` 是代码路径编号，只用于追溯 Java 分支；报告中不能只展示 `B-*`，必须同时说明它对应的业务场景。
- `O-*` 是业务后果编号，只用于把代码路径绑定到可断言的业务结果；报告中不能只展示 `O-*`，必须说清楚不覆盖会造成什么后果。

## 设计原则

| 原则 | 说明 |
|---|---|
| 绑定 Q01 | `绑定项` 必须来自 Q01，不能在 Q05a 自创需求。 |
| 一条 EUT 一个业务场景 | 避免把多个互斥场景塞进一个测试。 |
| 路径类型可解释 | Happy Path、Exception、Boundary 必须说明业务含义。 |
| 风险后果可理解 | 每条都说明不覆盖时可能发生的业务问题。 |
| 断言可落地 | 核心断言必须能落到 JUnit/Mockito 的强断言。 |

## EUT 明细

### 任务生成与通知

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| EUT-001 | 每月任务生成遇到“已存在部分门店任务”时，只为缺失门店补建 V1 待提交任务。<br>**不覆盖后果**：防止同一门店同一月份重复生成任务，也防止漏建任务导致门店无法提报。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.createMonthlyExpenseOrders` | assertEquals(1, result) and assertEquals(PENDING, insert.status) and assertEquals("V1", query.version)。 | BR-001：每个月只针对未关闭门店生成门店+月份任务，已关闭门店不生成任务。<br>B: B-001<br>O: O-001 |
| EUT-002 | 每月开启上传时，系统给门店财务发送上传入口通知并记录 OPEN 场景。<br>**不覆盖后果**：防止门店财务不知道提报入口，影响经营模型数据按月收集。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.sendOpenNotice` | assertEquals("OPEN", record.scene) and assertEquals("STORE_FINANCE", receiverType) and verify(appPushGateway).sendInformedMessage(any())。 | BR-002：每月 1 日通知门店财务上传，每月 15 日提醒未提交门店的财务、城市经理和区域财经BP。<br>B: B-003<br>O: O-003 |
| EUT-003 | 每月 15 日催办未提交门店，同时通知门店财务、城市经理和区域财经 BP。<br>**不覆盖后果**：防止临近截止仍无人跟进，导致经营模型缺少门店财务数据。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.sendReminderNotice` | assertEquals(3, result) and assertEquals([STORE_FINANCE,CITY_MANAGER,LITTLE_ZONE_BP], receiverTypes)。 | BR-002：每月 1 日通知门店财务上传，每月 15 日提醒未提交门店的财务、城市经理和区域财经BP。<br>B: B-005, B-006<br>O: O-005, O-006 |
| EUT-027 | 通知记录插入后返回主键，用于后续发送状态和幂等过滤。<br>**不覆盖后果**：防止通知发送结果无法追踪，重跑时无法去重。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseNoticeRecordGatewayImpl.insertSelective` | assertEquals(100L, id)。 | SE-014：每月15日提醒未提交门店，通知记录必须支撑重跑幂等过滤。<br>B: B-051, B-052<br>O: O-051, O-052 |
| EUT-031 | 每月自动为授权门店生成财务手工上传任务。<br>**不覆盖后果**：防止月度提报周期没有任务入口。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.createMonthlyExpenseOrders` | assertEquals(1, result) and verify(financeExpenseGateway).insertSelective(captor.capture()) and assertEquals(PENDING, insert.status)。 | REQ-001：授权店财务手工上传指定科目并审批，最终计算门店经营模型。<br>B: B-001<br>O: O-001 |
| EUT-032 | 门店+月份+V1 已存在时跳过，只为缺失门店生成任务。<br>**不覆盖后果**：防止重复任务和幂等重跑污染数据。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.createMonthlyExpenseOrders` | assertEquals(1, result) and assertEquals("F1002", insert.orgId) proving existing 门店+月份+V1 is skipped。 | SE-001：门店+月份+V1 任务生成必须幂等。<br>B: B-001, B-002<br>O: O-001, O-002 |
| EUT-033 | 开启通知写入通知记录并标记发送状态。<br>**不覆盖后果**：防止通知发出后没有持久化记录，无法审计和幂等。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.sendOpenNotice` | assertEquals("STORE_FINANCE", receiverType) and assertEquals(Integer.valueOf(1), sendStatus) and verify(appPushGateway).sendInformedMessage(any())。 | SE-002：开启和催办通知必须按岗位匹配接收人并避免重复发送。<br>B: B-003, B-004<br>O: O-003, O-004 |

### 列表、导出与权限

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| EUT-004 | 用户按筛选条件查看财务手工上传列表，列表展示门店名称和财务期间。<br>**不覆盖后果**：防止列表筛选/展示口径错误，影响运营人员定位任务。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseServiceImpl.list` | assertEquals(1, result.total) and assertEquals("F6165-测试门店", orgDisplay) and assertEquals("2026年3月", periodDesc)。 | BR-003：列表支持任务编号、版本、月份、审批流单号、门店、状态、创建时间和更新时间筛选，并按当前列表范围导出。<br>B: B-007<br>O: O-007 |
| EUT-005 | 列表查询创建时间只传开始或结束时直接拒绝，并且不进入数据库查询。<br>**不覆盖后果**：防止半开时间区间造成误筛选、慢查询或错误导出。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.list` | assertThrows(BusinessException.class) and assertEquals("创建时间开始和结束必须成对传入", ex.getMessage()) and verify(financeExpenseGateway, never()).countByEntity(any())。 | BR-003：列表支持任务编号、版本、月份、审批流单号、门店、状态、创建时间和更新时间筛选，并按当前列表范围导出。<br>B: B-009<br>O: O-009 |
| EUT-006 | 导出列表沿用当前筛选条件和权限门店范围，并生成导出文件地址。<br>**不覆盖后果**：防止用户导出超出页面范围或越权门店的数据。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseJobHandler.exportList` | assertEquals("https://test/export.xlsx", resp.fileUrl) and assertEquals(true, query.latestOnly) and assertEquals(["F6165"], permissionOrgIdList)。 | BR-003：列表支持任务编号、版本、月份、审批流单号、门店、状态、创建时间和更新时间筛选，并按当前列表范围导出。<br>B: B-010<br>O: O-010 |
| EUT-018 | 用户没有任何数据权限时，列表返回空且不查询业务数据。<br>**不覆盖后果**：防止无权限用户看到门店财务数据。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.list` | assertEquals(0, result.total) and assertEquals(Collections.emptyList(), result.list) and verify(financeExpenseGateway, never()).countByEntity(any())。 | SE-010：总部、区域、门店角色具有不同数据范围，无任何权限维度时不得返回业务数据。<br>B: B-008<br>O: O-008 |
| EUT-021 | 导出时查询明细、组装 Excel 并上传临时文件。<br>**不覆盖后果**：防止导出只有主表没有费用明细，影响经营分析。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.exportList` | verify(financeExpenseDetailGateway).selectByEntity(any()) and verify(uploadGateway).uploadOutTempFile(any()) and assertEquals(export url)。 | BR-009：导出字段包含财务期间、门店编码、门店名称、门店类型、是否确认以及多类收入成本费用字段。<br>B: B-010<br>O: O-010 |
| EUT-028 | Provider 列表接口把请求权限转换给 service，并返回列表响应。<br>**不覆盖后果**：防止 API 层权限范围丢失或响应结构错误。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseProviderImpl.list` | assertEquals(true, captor.permission.headquarter) and assertEquals("FE001", result.data.list[0].expenseNo)。 | REQ-004：总部、区域和门店角色按页面权限、操作权限和数据范围访问财务手工上传功能。<br>B: B-053<br>O: O-053 |
| EUT-029 | 导出列表创建时间只传一边时被拒绝。<br>**不覆盖后果**：防止导出范围与列表查询范围不一致。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.exportList` | assertThrows(BusinessException.class) and assertEquals("创建时间开始和结束必须成对传入", ex.message)。 | BR-003：列表支持任务编号、版本、月份、审批流单号、门店、状态、创建时间和更新时间筛选，并按当前列表范围导出。<br>B: B-012<br>O: O-012 |
| EUT-030 | 非门店财务或未配置操作权限时，下一步操作被拒绝且不进入 service。<br>**不覆盖后果**：防止无操作权限用户上传或推进财务表单。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseProviderImpl.stepNext` | assertThrows(BusinessException.class) and assertEquals("当前用户无财务费用操作权限", ex.getMessage()) and verify(financeExpenseService, never()).stepNext(any())。 | BR-011：门店财务可查看详情、批量下载、上传、提交审批、撤回审批和重新提交，非财务仅查看下载。<br>B: B-054<br>O: O-054 |
| EUT-034 | 列表导出字段可进入门店经营模型计算链路。<br>**不覆盖后果**：防止导出缺失经营模型所需字段。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.exportList` | assertEquals("https://test/export.xlsx", resp.fileUrl) and verify(financeExpenseDetailGateway).selectByEntity(any()) proves export data feeds operating model fields。 | REQ-003：列表下载字段包含系统计算值，上传审批后的费用数据用于经营模型计算和导出。<br>B: B-010<br>O: O-010 |
| EUT-035 | 导出只取最新版本并遵守权限门店范围。<br>**不覆盖后果**：防止旧版本或越权门店数据进入导出文件。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseJobHandler.exportList` | assertEquals(true, query.latestOnly) and assertEquals(["F6165"], permissionOrgIdList) and verify(uploadGateway).uploadOutTempFile(any())。 | SE-009：列表导出必须按照当前列表展示的数据范围下载 Excel。<br>B: B-010, B-011<br>O: O-010, O-011 |

### 表单、审批与状态机

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| EUT-007 | 详情页打开历史版本时，返回版本号和财务 Excel 附件信息。<br>**不覆盖后果**：防止版本详情与附件丢失，导致财务无法复核历史提报。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseServiceImpl.detail` | assertEquals("V1", result.version) and assertEquals("财务.xlsx", financeExcelFileId[0].name)。 | REQ-002：任务表单以门店+月份为单位，支持填写、提交、BPM审批流和版本管理。<br>B: B-013, B-014, B-015<br>O: O-013, O-014, O-015 |
| EUT-008 | 财务上传 Excel 后点击下一步，系统更新主表并写入快照。<br>**不覆盖后果**：防止预览/提交前没有保存当前文件和快照，导致审批数据不可追溯。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.stepNext` | assertEquals("success", result) and verify(financeExpenseGateway).updateByKey(captor.capture()) and assertEquals(1, snapshot.stepNext)。 | BR-006：下一步必须上传财务数据 Excel，补充凭证每类不超过 10 个，提交前文件必须与已暂存版本一致。<br>B: B-016<br>O: O-016 |
| EUT-009 | 未上传财务 Excel 时点击下一步被拒绝，且主表不被更新。<br>**不覆盖后果**：防止空 Excel 进入后续流程，污染审批和经营模型。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.stepNext` | assertThrows(BusinessException.class) and verify(financeExpenseGateway, never()).updateByKey(any())。 | BR-006：下一步必须上传财务数据 Excel，补充凭证每类不超过 10 个，提交前文件必须与已暂存版本一致。<br>B: B-018, B-017<br>O: O-018, O-017 |
| EUT-010 | 某一类补充凭证超过 10 个时，暂存被拒绝并返回明确提示。<br>**不覆盖后果**：防止附件无限制上传造成页面、存储和审批处理异常。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.save` | assertThrows(BusinessException.class) and assertTrue(message contains "培训费凭证") and assertTrue(message contains "不能超过10个")。 | SE-012：补充凭证每类不超过 10 个文件。<br>B: B-020<br>O: O-020 |
| EUT-011 | 提交审批时文件与暂存版本一致，触发审批中状态处理器。<br>**不覆盖后果**：防止合格提报无法进入 BPM 审批链路。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.submit` | assertEquals("success", result) and verify(statusEventHandler).trigger(any(FinanceExpenseSubmitSoIn.class))。 | BR-008：任何一级审批驳回后审批流结束，发起人可以在业务系统重新发起并生成新的审批流。<br>B: B-022<br>O: O-022 |
| EUT-012 | 提交时当前文件与已暂存版本不一致，提交被拒绝且不触发状态机。<br>**不覆盖后果**：防止用户把未预览或被替换的文件送审。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.submit` | assertThrows(BusinessException.class) and assertEquals("当前文件与已暂存版本不一致", normalized message prefix) and verify(statusEventFactory, never()).getStatusEventHandler(any(), any())。 | SE-006：提交审批前必须完成 Excel 上传、下一步预览并保证提交文件与暂存一致。<br>B: B-024, B-023<br>O: O-024, O-023 |
| EUT-013 | BPM 回调审批流单号与当前任务不匹配时拒绝处理。<br>**不覆盖后果**：防止旧流程、串单或外部回调误改当前任务状态。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.approve` | assertThrows(BusinessException.class) and assertEquals("审批流单号不匹配", normalized message prefix) and verify(statusEventFactory, never()).getStatusEventHandler(any(), any())。 | SE-007：BPM 回调必须校验审批流单号，避免旧流程或串单误改当前版本状态。<br>B: B-027, B-025, B-026<br>O: O-027, O-025, O-026 |
| EUT-014 | 审批驳回回调触发驳回状态处理器。<br>**不覆盖后果**：防止驳回后状态没有落库，财务无法重新处理。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.reject` | verify(statusEventHandler).trigger(any(FinanceExpenseStatusSoIn.class))。 | BR-008：任何一级审批驳回后审批流结束，发起人可以在业务系统重新发起并生成新的审批流。<br>B: B-028, B-029, B-030<br>O: O-028, O-029, O-030 |
| EUT-016 | 归档状态下尝试暂存编辑被拒绝。<br>**不覆盖后果**：防止归档终态被人工修改，破坏审批闭环。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.save` | assertThrows(BusinessException.class) and assertTrue(message contains "当前状态不允许暂存") and verifyNoInteractions(statusEventFactory)。 | BR-004：表单状态通过 BPM 审批关联控制状态机流转，归档之后不能人工编辑。<br>B: B-021<br>O: O-021 |
| EUT-022 | 状态迁移工厂能根据已注册迁移返回审批中处理器。<br>**不覆盖后果**：防止合法状态流转找不到处理器而中断。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseStatusEventFactory.getStatusEventHandler` | assertEquals(APPROVING, handler.targetStatus())。 | SE-003：表单状态通过 BPM 审批关联控制状态机流转，未注册状态迁移必须拒绝。<br>B: B-040<br>O: O-040 |
| EUT-023 | 未注册状态迁移被拒绝并给出明确错误。<br>**不覆盖后果**：防止非法状态跳转绕过状态机约束。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseStatusEventFactory.getStatusEventHandler` | assertThrows(BusinessException.class) and assertTrue(message contains "未注册状态转移")。 | SE-003：表单状态通过 BPM 审批关联控制状态机流转，未注册状态迁移必须拒绝。<br>B: B-042, B-041<br>O: O-042, O-041 |
| EUT-024 | 快照网关保存任务编号、版本、状态和附件字段。<br>**不覆盖后果**：防止审批链路缺少可审计快照。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseSnapshotGatewayImpl.insertSelective` | assertEquals("FE001", model.expenseNo) and assertTrue(financeExcelFileId contains "1001")。 | SE-011：上传和状态变化必须保留版本、状态、操作人和附件字段证据。<br>B: B-043, B-044<br>O: O-043, O-044 |
| EUT-025 | 主表持久化时，未上传 Excel 的占位值被转换为空数组。<br>**不覆盖后果**：防止 `-1` 这类前端占位值进入数据库。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseGatewayImpl.insertSelective` | verify(financeExpenseMapper).insertSelective(captor.capture()) and assertEquals("[]", model.financeExcelFileId)。 | SE-013：上传财务数据 Excel 是必填项，未上传时不能进入下一步或提交。<br>B: B-045, B-046<br>O: O-045, O-046 |
| EUT-036 | 归档状态作为终态，保存操作被拒绝且不触发状态机。<br>**不覆盖后果**：防止归档后被二次编辑或误触发状态迁移。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseServiceImpl.save` | assertThrows(BusinessException.class) and assertTrue(message contains "当前状态不允许暂存") and verifyNoInteractions(statusEventFactory)。 | SE-004：归档之后不能再人工编辑，归档状态是终态。<br>B: B-021, B-019<br>O: O-021, O-019 |

### 版本管理

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| EUT-015 | 驳回后重新上传生成 V2 待提交记录，并清空上一版本凭证。<br>**不覆盖后果**：防止新版本继承旧版本附件或误改旧版本数据。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `RejectedToPendingStatusTransition.trigger` | assertEquals("V2", insert.version) and assertEquals(PENDING, insert.status) and assertEquals(emptyList, equipmentMaintenanceFileIds)。 | BR-005：表单具有版本概念，审批通过或驳回后再次重新上传会生成+1版本，旧版本变为无效。<br>B: B-031, B-032, B-033<br>O: O-031, O-032, O-033 |
| EUT-017 | 版本列表返回多个版本，并按最新版本优先展示。<br>**不覆盖后果**：防止财务或运营查看版本历史时误把旧版本当当前版本。 | Happy Path：正常路径，证明主流程能按需求完成<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseServiceImpl.version` | assertEquals(3, result.total) and assertEquals("V3", first.version)。 | SE-005：审批通过或驳回后重新上传生成+1版本，旧版本不能被当前操作误改。<br>B: B-034, B-035, B-036<br>O: O-034, O-035, O-036 |

### Excel 解析与经营模型数据

| EUT | 业务场景 | 路径/风险 | 目标代码 | 核心断言 | 追溯编号 |
|---|---|---|---|---|---|
| EUT-019 | 解析 2S Excel 模板时，正确生成手工填写字段和系统计算字段。<br>**不覆盖后果**：防止经营模型使用错误的收入、成本或费用明细。 | Happy Path：正常路径，证明主流程能按需求完成<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseExcelUtils.parseDetailList` | assertEquals(new BigDecimal("25.35"), detailMap["25"].subjectValue) and assertFalse(detailMap.containsKey("4"))。 | BR-007：2S 店模板既填写售后也填写销售数据，1S 店模板只填写售后数据，基础信息由系统自动带出。<br>B: B-037<br>O: O-037 |
| EUT-020 | 上传 Excel 的公式结果与系统计算不一致时拒绝解析。<br>**不覆盖后果**：防止用户篡改公式或上传脏数据进入经营模型。 | Exception：拒绝/异常路径，证明非法输入或错误状态不会继续写库、送审或串单<br>T1：高风险/必须覆盖：影响状态流转、审批、权限、通知、金额/Excel、数据一致性或外部同步 | `FinanceExpenseExcelUtils.parseDetailList` | assertThrows(BusinessException.class) and assertEquals("上传Excel公式/系统计算结果不一致", normalized message category) for formula result mismatch validation path。 | SE-008：Excel 模板顺序、门店编码、月份、公式和系统计算字段必须与标准模板一致。<br>B: B-039, B-038<br>O: O-039, O-038 |
| EUT-026 | 费用明细批量插入遇到空列表时直接跳过。<br>**不覆盖后果**：防止空明细写库或触发无意义 SQL。 | Boundary：边界路径，证明空值、重复、数量上限、权限空集合等边界不会造成脏数据<br>T2：重要路径：影响查询展示、导出、持久化转换、辅助网关或低爆炸半径边界 | `FinanceExpenseDetailGatewayImpl.batchInsert` | verify(financeExpenseDetailMapper, never()).batchInsert(anyList())。 | BR-009：导出字段包含财务期间、门店编码、门店名称、门店类型、是否确认以及多类收入成本费用字段。<br>B: B-048, B-047, B-049, B-050<br>O: O-048, O-047, O-049, O-050 |

## 不可测项

| ID | 原因 | 可测性 | 证据 |
|---|---|---|---|
| BR-010 | BI 同步接口/消息实现不在当前已定位 Java 方法中，无法用本仓库现有单测直接验证；用户已明确要求本轮忽略。 | external_system | prd.md:564 |
| SE-015 | 需要 BI 同步报告或接口实现作为可测对象，当前仓库仅有 PRD 语义；用户已明确要求本轮忽略。 | external_system | prd.md:564 |
| SE-016 | 旧版本失效缺少状态枚举或同步过滤实现证据；用户已明确要求本轮忽略，作为已接受风险留痕。 | not_backend_testable | prd.md:243 |

## 自我评审记录

- 每条后端可测 REQ/BR/SE 都有 EUT 或不可测原因。
- 每条 EUT 都说明业务场景、风险后果、路径类型、风险等级和核心断言。
- `B-*`/`O-*` 作为追溯编号保留，但报告中已展开业务含义。
