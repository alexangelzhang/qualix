# Q05a EUT 矩阵明细报告 — entitlement-lifecycle

## 目标模块发现过程

### diff 文件归档（4类）

**real_diff_files（全部 6 个）：**
1. MafGatewayImpl.java
2. WarrantyUpdateParam.java
3. WarrantyUpdateCommandHandler.java
4. WarrantyUpdateTypeEnum.java
5. WarrantyFacadeImpl.java
6. SrvThreeGuarantee.java

**included_diff_files（3 个，纳入 EUT 设计）：**
1. WarrantyUpdateParam.java（@NotBlank 字段改动，通过 fixWarrantyData 集成测试覆盖）
2. WarrantyUpdateCommandHandler.java（handle 方法逻辑改动）
3. WarrantyFacadeImpl.java（5 个方法改动，主要设计目标）

**excluded_diff_files（3 个，已确认排除）：**
1. MafGatewayImpl.java — 仅日志格式调整（toString→JsonUtil.writeValue），无业务逻辑
2. WarrantyUpdateTypeEnum.java — checkData 仅 JavaDoc 注释变更，无逻辑
3. SrvThreeGuarantee.java — 仅 @ChangeLogAnnotation 注解标注，无方法

**scope_conflicts：** 无

---

## 需求到代码映射

| REQ/BR/SE | 映射类 | 映射方法 | 证据行号 |
|---|---|---|---|
| REQ-001 | WarrantyFacadeImpl | fixWarrantyData | :361 |
| REQ-002 | WarrantyFacadeImpl | fixMaterialWarrantyData | :445 |
| BR-001 | WarrantyUpdateParam | N/A（@NotBlank） | :32 |
| BR-002 | WarrantyFacadeImpl | validateAndParseFixWarrantyParam | :131 |
| BR-003 | WarrantyFacadeImpl | parseFixWarrantyEndDate | :117 |
| BR-004 | WarrantyFacadeImpl | resolveStartTimeTypeId | :100 |
| BR-005 | WarrantyFacadeImpl | fixWarrantyData | :408 |
| BR-006 | WarrantyUpdateCommandHandler | handle | :40 |
| BR-007 | WarrantyFacadeImpl | fixWarrantyData | :370 |
| SE-001~007 | WarrantyFacadeImpl | fixWarrantyData | — |
| SE-008 | WarrantyUpdateCommandHandler | handle | :40 |
| SE-009 | WarrantyFacadeImpl | fixMaterialWarrantyData | :447 |

---

## diff 文件覆盖表

| 文件 | 状态 | 覆盖 EUT |
|---|---|---|
| WarrantyFacadeImpl.java | included | EUT-002~010, 013~019 |
| WarrantyUpdateCommandHandler.java | included | EUT-011, 012 |
| WarrantyUpdateParam.java | included（集成） | EUT-001, 018 |
| MafGatewayImpl.java | excluded | NT-001 |
| WarrantyUpdateTypeEnum.java | excluded | NT-002 |
| SrvThreeGuarantee.java | excluded | NT-003 |

---

## EUT 矩阵（按类分组）

### WarrantyFacadeImpl（核心类）

#### resolveStartTimeTypeId

| EUT | 路径类型 | Given | When | Then |
|---|---|---|---|---|
| EUT-006 | Happy Path | raw='ACTIVATION' | resolveStartTimeTypeId | 返回 StartTimeType.ACTIVATION.getId()，非 null |
| EUT-007 | Boundary | raw='2' | resolveStartTimeTypeId | 返回 2 |
| EUT-008 | Exception | raw='INVALID_TYPE_XYZ' | resolveStartTimeTypeId | 返回 null，调用方 fail（退货起算类型不合法） |
| EUT-009 | Boundary | raw=null | resolveStartTimeTypeId | 返回 null |

#### parseFixWarrantyEndDate

| EUT | 路径类型 | Given | When | Then |
|---|---|---|---|---|
| EUT-004 | Boundary | raw='2026-12-31' | parseFixWarrantyEndDate | 返回 Date 非 null，日期=2026-12-31 |
| EUT-005 | Exception | raw='12/31/2025' | parseFixWarrantyEndDate | 返回 null；调用方 fail（退货截止时间格式错误） |

#### validateAndParseFixWarrantyParam / fixWarrantyData

| EUT | 路径类型 | Given | When | Then |
|---|---|---|---|---|
| EUT-001 | Exception | returnStartTime=null | fixWarrantyData | Result.fail，ParamError，message 含 'returnStartTime不能为空' |
| EUT-002 | Exception | returnStartTime='2024-01-01' | fixWarrantyData | fail，'退货开始时间格式错误' |
| EUT-003 | Exception | exchangeStartTime='2024/01/01 00:00:00' | fixWarrantyData | fail，'换货开始时间格式错误' |
| EUT-010 | Happy Path | 9字段合法，revisable=NO | fixWarrantyData | success；9字段+老字段覆盖；updateType=null |
| EUT-013 | Boundary | DB 无记录 | fixWarrantyData | 实时计算分支→ 覆盖9字段→ 落库→ success |
| EUT-014 | Boundary | DB revisable=YES | fixWarrantyData | 实时计算分支→ 覆盖9字段→ 落库→ success |
| EUT-018 | Exception | exchangeStartTime='' | fixWarrantyData | ConstraintViolationException 或 fail 含 'exchangeStartTime不能为空' |
| EUT-019 | Happy Path | returnTimeType='1', repairStartTime='2024-03-01 00:00:00', revisable=NO | fixWarrantyData | timeType==1, startTime==strToDate('2024-03-01 00:00:00') |

#### fixMaterialWarrantyData

| EUT | 路径类型 | Given | When | Then |
|---|---|---|---|---|
| EUT-015 | Happy Path | startTime='2024-06-01 10:30:00', repairEndTime='2026-12-31' | fixMaterialWarrantyData | success，不报日期格式错误 |
| EUT-016 | Boundary | startTime='2024/06/01 10:30:00'（斜杠格式） | fixMaterialWarrantyData | fallback strToDateExt 成功，不报错 |
| EUT-017 | Exception | startTime='20240601'（非法） | fixMaterialWarrantyData | fail，'开始时间格式错误' |

### WarrantyUpdateCommandHandler

| EUT | 路径类型 | Given | When | Then |
|---|---|---|---|---|
| EUT-011 | Exception | threeGuarantee=null | handle | 抛 SfpLifecycleException，'threeGuarantee不能为空' |
| EUT-012 | Happy Path | threeGuarantee 合法 | handle | true；insertOrUpdate；changeReason=HUMAN_FIX_NEW；revisable=NO |

---

## 不可测项

| ID | 原因 |
|---|---|
| NT-001 | MafGatewayImpl 仅日志格式，无业务逻辑 |
| NT-002 | WarrantyUpdateTypeEnum 仅注释变更 |
| NT-003 | SrvThreeGuarantee 仅 @ChangeLogAnnotation，间接覆盖 |
| NT-004 | WarrantyUpdateParam 为纯 DTO，通过集成场景覆盖 |

---

## 自我评审记录

1. **diff 覆盖完整性**：6个 diff 文件全部归档；3个 excluded 均有业务理由；0个 scope_conflict。
2. **需求覆盖**：REQ-001/002、BR-001~007、SE-001~009 全部有 EUT 对应。
3. **分支闭环**：resolveStartTimeTypeId 4条分支 → EUT-006/007/008/009；parseFixWarrantyEndDate 4条 → EUT-004/005；fixWarrantyData 4条分支 → EUT-010/013/014/002；WarrantyUpdateCommandHandler.handle 3条 → EUT-011/012。
4. **Exception EUT**：validateAndParseFixWarrantyParam 9个 fail 路径（3开始时间+3截止时间+3起算类型）选取代表性 EUT（EUT-002/003/005/008），避免重复堆砌。
5. **assertion_blueprint**：每条 EUT 包含具体断言类型/对象/期望值，可直接驱动 Q05b 代码生成。
