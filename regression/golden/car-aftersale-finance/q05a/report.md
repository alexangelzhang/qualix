# Q05a EUT 设计报告

## 结论

Q05a 已完成 EUT 设计，产出 36 条可落地到 Java 单测的业务场景。当前结论为 `PASS_WITH_WAIVED_GAPS`：后端可测的 REQ/BR/SE 已映射到 EUT；BI 同步和旧版本失效缺少实现证据，但用户已明确要求本轮忽略，作为已接受风险留痕。

这份报告不是“测试编号清单”。它回答三个问题：为什么这些场景必须测、每个场景对应什么业务风险、最终要用什么断言证明业务后果。`B-*` 和 `O-*` 只作为追溯编号，不作为业务解释。

## 术语说明

- `REQ-*` 是需求点，说明业务目标；`BR-*` 是业务规则，说明必须满足的分支规则；`SE-*` 是关键语义，说明必须能被验证的业务不变量。
- `EUT-*` 是 Executable Unit Test，即一条可落地到 Java 单测的业务场景，不等同于一个测试方法，但必须能追到测试方法。
- `T1/T2/T3` 是风险等级，不是技术优先级。T1 表示不测会影响状态、权限、审批、数据一致性、金额/Excel 或外部同步；T2 表示重要但爆炸半径较小。
- `B-*` 是代码路径编号，只用于追溯 Java 分支；报告中不能只展示 `B-*`，必须同时说明它对应的业务场景。
- `O-*` 是业务后果编号，只用于把代码路径绑定到可断言的业务结果；报告中不能只展示 `O-*`，必须说清楚不覆盖会造成什么后果。

## 设计原则

| 原则 | 在本项目中的落地 |
|---|---|
| 需求语义优先 | 所有 EUT 都绑定 Q01 的 `REQ/BR/SE`，不从代码里凭空发明业务规则。 |
| 业务场景可读 | 每条 EUT 先写业务场景和不覆盖的后果，再列 Java 类/方法。 |
| 路径类型完整 | 同时覆盖正常、异常、边界路径，避免只测 happy path。 |
| 强断言导向 | `then` 必须落到状态、返回值、异常消息、写库副作用或 Mockito 参数。 |
| 不伪造不可测项 | BI 同步和旧版本失效没有当前仓库实现证据，不生成假 EUT；用户已接受本轮忽略。 |

## 覆盖分布

| 业务域 | 数量 |
|---|---:|
| 表单、审批与状态机 | 14 |
| 列表、导出与权限 | 10 |
| 任务生成与通知 | 7 |
| Excel 解析与经营模型数据 | 3 |
| 版本管理 | 2 |

| 路径 | 数量 |
|---|---:|
| Happy Path | 20 |
| Exception | 10 |
| Boundary | 6 |

| 风险等级 | 数量 |
|---|---:|
| T1 | 28 |
| T2 | 8 |

| 目标类 | 数量 |
|---|---:|
| FinanceExpenseServiceImpl | 14 |
| FinanceExpenseJobHandler | 11 |
| FinanceExpenseExcelUtils | 2 |
| FinanceExpenseStatusEventFactory | 2 |
| FinanceExpenseProviderImpl | 2 |
| RejectedToPendingStatusTransition | 1 |
| FinanceExpenseSnapshotGatewayImpl | 1 |
| FinanceExpenseGatewayImpl | 1 |
| FinanceExpenseDetailGatewayImpl | 1 |
| FinanceExpenseNoticeRecordGatewayImpl | 1 |

## 高风险场景摘要

| EUT | 业务场景 | 不覆盖的后果 | 目标代码 | 追溯 |
|---|---|---|---|---|
| EUT-001 | 每月任务生成遇到“已存在部分门店任务”时，只为缺失门店补建 V1 待提交任务。 | 防止同一门店同一月份重复生成任务，也防止漏建任务导致门店无法提报。 | `FinanceExpenseJobHandler.createMonthlyExpenseOrders` | BR-001；B-001；O-001 |
| EUT-002 | 每月开启上传时，系统给门店财务发送上传入口通知并记录 OPEN 场景。 | 防止门店财务不知道提报入口，影响经营模型数据按月收集。 | `FinanceExpenseJobHandler.sendOpenNotice` | BR-002；B-003；O-003 |
| EUT-003 | 每月 15 日催办未提交门店，同时通知门店财务、城市经理和区域财经 BP。 | 防止临近截止仍无人跟进，导致经营模型缺少门店财务数据。 | `FinanceExpenseJobHandler.sendReminderNotice` | BR-002；B-005, B-006；O-005, O-006 |
| EUT-005 | 列表查询创建时间只传开始或结束时直接拒绝，并且不进入数据库查询。 | 防止半开时间区间造成误筛选、慢查询或错误导出。 | `FinanceExpenseServiceImpl.list` | BR-003；B-009；O-009 |
| EUT-008 | 财务上传 Excel 后点击下一步，系统更新主表并写入快照。 | 防止预览/提交前没有保存当前文件和快照，导致审批数据不可追溯。 | `FinanceExpenseServiceImpl.stepNext` | BR-006；B-016；O-016 |
| EUT-009 | 未上传财务 Excel 时点击下一步被拒绝，且主表不被更新。 | 防止空 Excel 进入后续流程，污染审批和经营模型。 | `FinanceExpenseServiceImpl.stepNext` | BR-006；B-018, B-017；O-018, O-017 |
| EUT-010 | 某一类补充凭证超过 10 个时，暂存被拒绝并返回明确提示。 | 防止附件无限制上传造成页面、存储和审批处理异常。 | `FinanceExpenseServiceImpl.save` | SE-012；B-020；O-020 |
| EUT-011 | 提交审批时文件与暂存版本一致，触发审批中状态处理器。 | 防止合格提报无法进入 BPM 审批链路。 | `FinanceExpenseServiceImpl.submit` | BR-008；B-022；O-022 |
| EUT-012 | 提交时当前文件与已暂存版本不一致，提交被拒绝且不触发状态机。 | 防止用户把未预览或被替换的文件送审。 | `FinanceExpenseServiceImpl.submit` | SE-006；B-024, B-023；O-024, O-023 |
| EUT-013 | BPM 回调审批流单号与当前任务不匹配时拒绝处理。 | 防止旧流程、串单或外部回调误改当前任务状态。 | `FinanceExpenseServiceImpl.approve` | SE-007；B-027, B-025, B-026；O-027, O-025, O-026 |
| EUT-014 | 审批驳回回调触发驳回状态处理器。 | 防止驳回后状态没有落库，财务无法重新处理。 | `FinanceExpenseServiceImpl.reject` | BR-008；B-028, B-029, B-030；O-028, O-029, O-030 |
| EUT-015 | 驳回后重新上传生成 V2 待提交记录，并清空上一版本凭证。 | 防止新版本继承旧版本附件或误改旧版本数据。 | `RejectedToPendingStatusTransition.trigger` | BR-005；B-031, B-032, B-033；O-031, O-032, O-033 |
| EUT-016 | 归档状态下尝试暂存编辑被拒绝。 | 防止归档终态被人工修改，破坏审批闭环。 | `FinanceExpenseServiceImpl.save` | BR-004；B-021；O-021 |
| EUT-018 | 用户没有任何数据权限时，列表返回空且不查询业务数据。 | 防止无权限用户看到门店财务数据。 | `FinanceExpenseServiceImpl.list` | SE-010；B-008；O-008 |
| EUT-019 | 解析 2S Excel 模板时，正确生成手工填写字段和系统计算字段。 | 防止经营模型使用错误的收入、成本或费用明细。 | `FinanceExpenseExcelUtils.parseDetailList` | BR-007；B-037；O-037 |
| EUT-020 | 上传 Excel 的公式结果与系统计算不一致时拒绝解析。 | 防止用户篡改公式或上传脏数据进入经营模型。 | `FinanceExpenseExcelUtils.parseDetailList` | SE-008；B-039, B-038；O-039, O-038 |

完整 36 条 EUT 见 `q05a/eut_matrix.md`。

## 不可测/待确认项

| ID | 可测性 | 为什么不能直接写 Java 单测 | 业务风险 | 需要补什么 |
|---|---|---|---|---|
| BR-010 | external_system | BI 同步接口/消息实现不在当前已定位 Java 方法中，无法用本仓库现有单测直接验证。 | 用户已接受本轮忽略；若未来重新纳入范围，仍需验证 BI 不取旧版本或非生效版本。 | prd.md:564 |
| SE-015 | external_system | 需要 BI 同步报告或接口实现作为可测对象，当前仓库仅有 PRD 语义。 | 用户已接受本轮忽略；若未来重新纳入范围，需要同步接口或报表证据。 | prd.md:564 |
| SE-016 | not_backend_testable | 旧版本失效缺少状态枚举或同步过滤实现证据，先登记 GAP，不能伪造单测通过。 | 用户已接受本轮忽略；若未来重新纳入范围，需要旧版本失效或有效版本过滤证据。 | prd.md:243 |

## 机器产物

| 产物 | 用途 |
|---|---|
| `q05a/eut_matrix.json` | 机器可读 EUT 矩阵，供 Q05b/Q06 校验。 |
| `q05a/eut_matrix.md` | 人可读 EUT 明细，解释业务场景、风险后果和断言。 |
| `q05a/branch_inventory.json` | 轻量 Java 结构扫描得到的代码路径账本。 |
| `q05a/business_outcomes.json` | `B-*` 到业务后果的映射，已补充可读业务含义。 |

## 自检结论

| 检查项 | 结论 |
|---|---|
| Q01 绑定 | 所有后端可测 REQ/BR/SE 均有 EUT 或明确不可测原因。 |
| 分支链路 | 已形成 `branch_inventory -> business_outcomes -> eut_matrix` 机器链路。 |
| 可读性 | 报告不再让 `T*`、`B-*`、`O-*` 单独承担解释职责。 |
