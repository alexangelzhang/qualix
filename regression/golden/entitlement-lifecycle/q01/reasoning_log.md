# Q01 Reasoning Log — entitlement-lifecycle

### Step 1：证据采集

- 下载飞书 PRD（故障原因主数据建设-2026.1），共 980 行，内含 23 个功能点（F-001~F-023）
- 拉取 feature/fix-warranty-update 分支与基点 a934896e 的 diff
- 生产代码变更文件：WarrantyUpdateParam.java、WarrantyFacadeImpl.java、WarrantyUpdateCommandHandler.java、WarrantyUpdateTypeEnum.java、SrvThreeGuarantee.java
- MafGatewayImpl.java 仅 1 行改动（非核心逻辑），暂不纳入 EUT 设计范围

### Step 2：假设前置

**假设 A**：PRD（故障原因）和代码（warranty update）的关联是：entitlement-lifecycle-service 是 AS工单 的后端服务，AS工单 是故障原因功能的下游消费方（工程师检测处理工单时使用故障原因数据）。warranty update 接口的修复是为了确保故障原因上线后三包数据的人工修正可靠性。

**假设 B**：`fixWarrantyData` 是运营后台的"人工修正三包"工具接口，不是用户侧高频调用接口。全字段必填语义合理，因为人工修正时必须明确所有字段值。

**假设 C**：`Se006` 场景不影响本次变更的核心测试，但需要确认。

### Step 3：全量理解

**核心改动逻辑**：
1. 旧逻辑：`fixWarrantyData` 调用 `WarrantyUpdateTypeEnum.checkData(param)` 做字段选择性校验，再 `setData()` 将参数写到 threeGuarantee，再根据 `updateType.isCalculate()` 决定是否重算；最后在 `WarrantyUpdateCommandHandler` 中执行全套重算逻辑
2. 新逻辑：`fixWarrantyData` 直接解析并校验全部9字段，直接覆盖所有字段到 dbSrvThreeGuarantee 后 dispatch 命令；`WarrantyUpdateCommandHandler` 仅做 null 检查后直接落库

**关键区别**：
- 旧：按 updateType 选择性更新；新：全字段必填覆盖
- 旧：WarrantyUpdateCommandHandler 会重算；新：不重算，Facade 已准备好完整 threeGuarantee
- 旧：起算类型解析只用 getIdByCode；新：三步解析链（code→numeric→convertLifeTimeTypeNull）
- 旧：截止时间只接受 strToDate；新：parseFixWarrantyEndDate 兼容纯日期

### Step 4：自检结果

- 遍历 validateAndParseFixWarrantyParam 方法：覆盖 9 条错误分支 → SE-001~006 覆盖
- 遍历 fixWarrantyData 主流程：DB null/revisable=YES 分支、revisable=NO 分支 → BR-007 覆盖
- 遍历 WarrantyUpdateCommandHandler.handle：threeGuarantee null 检查 → BR-006/SE-008 覆盖
- fixMaterialWarrantyData：日期解析变更 → REQ-002/SE-009 覆盖

### Step 5：批评者视角

- **遗漏检查**：MaterialWarrantyUpdateParam 未加 @NotBlank → GAP-002 记录
- **隐性风险**：timeType/startTime 老字段兼容是否完整（只设了 timeType=returnTimeType 和 startTime=repairStartTime，其他老字段如 endTime 未变化）→ 认为合理，老字段本就少于新三包字段
- **幂等性**：多次调用 fixWarrantyData 是否幂等？每次都覆盖，幂等 → 无需额外 SE
- **并发**：同一设备并发修正，threeGuaranteeRepositoryHolder.insertOrUpdate 是否有锁？当前 PRD 范围内不要求并发保护 → 不加 SE

### Step 6：修正记录

无修正，第一轮结果通过自检。
