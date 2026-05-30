# Q01 需求结构化报告 — entitlement-lifecycle

## 证据清单

| 文件 | 说明 |
|---|---|
| `input/【PRD】信息部-中国区服务-故障原因-主数据建设-2026.1.md` | 产品需求文档，提供系统上下文（AS工单/三包/故障原因集成） |
| `WarrantyFacadeImpl.java`（diff a934896e→5fac629c） | 主改动：fixWarrantyData 重构为全字段必填直接覆盖，fixMaterialWarrantyData 日期格式兼容增强 |
| `WarrantyUpdateCommandHandler.java`（diff） | 精简：移除 WarrantyCoreService，移除 updateType 选择分支，增加 threeGuarantee null 检查 |
| `WarrantyUpdateParam.java`（diff） | 接口入参：9个时间/起算类型字段增加 @NotBlank |
| `WarrantyUpdateTypeEnum.java`（diff） | 注释更新，说明 fixWarrantyData 不再经由本枚举 |
| `SrvThreeGuarantee.java`（diff） | timeType 字段增加 @ChangeLogAnnotation(isIgnoreCompare=true) |

---

## 需求清单

| ID | 描述 | 优先级 |
|---|---|---|
| REQ-001 | 整机三包人工修正（fixWarrantyData）：9字段全部必填直接覆盖，废弃 updateType 逻辑 | P0 |
| REQ-002 | 物料三包人工修正（fixMaterialWarrantyData）：起始时间优先 yyyy-MM-dd HH:mm:ss，截止时间兼容纯日期 | P1 |

---

## 业务规则

| ID | 规则描述 | 关联需求 |
|---|---|---|
| BR-001 | fixWarrantyData 9字段全部必填（@NotBlank），任一空返回 ParamError | REQ-001 |
| BR-002 | 开始时间格式：仅支持 yyyy-MM-dd HH:mm:ss；其他格式报错「X开始时间格式错误」 | REQ-001 |
| BR-003 | 截止时间格式：支持 yyyy-MM-dd HH:mm:ss 或 yyyy-MM-dd（纯日期） | REQ-001 |
| BR-004 | 起算类型解析：枚举 code 字符串 > 数字 id 字符串 > convertLifeTimeTypeNull；均失败报「X起算类型不合法」 | REQ-001 |
| BR-005 | 覆盖语义：9个字段全部覆盖；老字段兼容：timeType=returnTimeType，startTime=repairStartTime | REQ-001 |
| BR-006 | Command 侧防御：threeGuarantee 为 null 时抛 SfpLifecycleException(ParamError) | REQ-001 |
| BR-007 | DB 无记录或 revisable=YES → 实时计算后覆盖；revisable=NO → 直接覆盖；两种情况均写变更日志 | REQ-001 |

---

## 关键语义

| ID | 语义描述 | 验证方式 | 分类 |
|---|---|---|---|
| SE-001 | 任一必填字段为空立即返回 ParamError，不写库 | 传入 returnStartTime=null，断言返回 fail，message 含字段名 | 入参校验 |
| SE-002 | 开始时间传纯日期 '2024-01-01' 返回「退货开始时间格式错误」 | 传入纯日期格式，断言 fail | 日期格式校验 |
| SE-003 | 截止时间传 yyyy-MM-dd 纯日期不报错 | 传入 '2026-12-31'，断言无 ParamError | 日期格式兼容 |
| SE-004 | 起算类型传 'ACTIVATION' 正确解析为 id | 传入枚举 code，断言 DB returnTimeType=ACTIVATION.getId() | 枚举解析 |
| SE-005 | 起算类型传 '2' 正确解析为 id=2 | 传入数字字符串，断言解析正确 | 枚举解析 |
| SE-006 | 起算类型传 'INVALID_TYPE_XYZ' 返回「退货起算类型不合法」 | 传入非法值，断言 fail | 枚举解析异常 |
| SE-007 | 成功后 DB 9字段+老字段兼容均被覆盖 | 合法入参 → 调用 → 断言 DB 字段值 | 写库正确性 |
| SE-008 | Command 侧 threeGuarantee=null 时抛 SfpLifecycleException | 构造 null threeGuarantee 命令，断言抛异常 | 防御性校验 |
| SE-009 | fixMaterialWarrantyData 接受 yyyy-MM-dd HH:mm:ss 格式起始时间 | 传入标准格式，断言不报「开始时间格式错误」 | 日期格式兼容 |

---

## GAP 清单

| ID | 描述 | 风险等级 |
|---|---|---|
| GAP-001 | PRD 未直接描述 fixWarrantyData/fixMaterialWarrantyData 接口规格；代码变更属后台工具类接口，Q05a/Q05b 以代码 diff 为主要覆盖依据 | LOW |
| GAP-002 | fixMaterialWarrantyData 入参（MaterialWarrantyUpdateParam）未同步增加 @NotBlank 校验，与 fixWarrantyData 改造不一致 | MEDIUM |

---

## OPEN 清单

| ID | 描述 | 决策方 |
|---|---|---|
| OPEN-001 | ThreeGuaranteeRepositoryHolderSe006Test 对应的 Se006 场景定义不明；需确认是否影响 fixWarrantyData 正确性 | 研发 |

---

## 自我评审记录

1. **PRD–代码 scope 对齐**：PRD 描述故障原因前端功能（故障原因品类配置/故障与非故障/XMS三元关系），code diff 是权益生命周期服务内部的三包人工修正接口重构。依据 AGENTS.md，PRD scope 约束 Q01 提取范围，code diff scope 约束 Q05a/Q05b 设计范围，两者独立。
2. **完整性检查**：BR-001~007 覆盖 validateAndParseFixWarrantyParam 的所有 9 个字段校验路径、日期解析分支、起算类型解析三条路径、DB 查询两个分支（null/revisable=YES vs revisable=NO）。
3. **异常路径覆盖**：SE-001~006 覆盖所有会返回 fail 的分支；SE-007~009 覆盖成功路径；GAP-002 标注了物料三包入参缺少 @NotBlank 的风险。
4. **边界情况**：BR-003 说明截止时间纯日期格式支持；BR-004 说明起算类型三步解析链。

---

## 结论

**PASS_WITH_OPEN_ITEMS**

需求结构化完成，9条 BR 和 9条 SE 覆盖 fixWarrantyData 全路径。存在 2 个 GAP（PRD 未覆盖 + 物料参数未加必填）和 1 个 OPEN（Se006 场景定义）。不阻断进入 Q05a。
