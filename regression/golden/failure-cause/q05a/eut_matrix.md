# Q05a EUT 矩阵报告 — failure-cause（故障原因主数据建设）

## 目标模块发现过程

### real_diff_files（全量 git diff 生产 Java 文件）

共 **110 个**生产 Java 文件，base_ref=`cb038f7f`（private-fault-reason 合并前），head_ref=`HEAD`

### diff 文件四类归档

| 分类 | 数量 | 说明 |
|------|------|------|
| included_diff_files | 15 | 含业务分支逻辑，纳入 EUT 设计 |
| excluded_diff_files | 95 | DTO/接口/Mapper/转换器/常量等，无分支业务逻辑 |
| scope_conflicts | 0 | 无需求范围冲突 |
| 合计 | 110 | = included + excluded + scope_conflicts ✓ |

**included_diff_files 清单（15个）：**
1. `FaultReasonFacadeImpl` — 故障原因主 facade，含核心校验和 BPM 流程
2. `FaultReasonServiceImpl` — 故障原因查询 service
3. `FaultEditServiceImpl` — 故障信息编辑 service（含故障原因）
4. `FaultFacadeImpl` — 故障主 facade（含故障原因集成）
5. `FaultListFacadeImpl` — 故障列表查询（含故障原因字段）
6. `FaultBpmApprovalServiceImpl` — BPM 审批 service（含故障原因分支）
7. `SingleFaultReasonBpmHandler` — 故障原因 BPM handler
8. `UpdateFaultTypeCommandHandler` — 类型管理双向校验
9. `FaultReasonBinLogCommandHandler` — 故障原因 binlog 处理
10. `FaultQueryServiceImpl` — 故障查询 service（含故障原因）
11. `FaultReasonBrandClassConfigRepositoryImpl` — 品类配置 Repository
12. `FaultReasonRelationRepositoryImpl` — 故障原因关系 Repository
13. `FaultReasonRepositoryImpl` — 故障原因底表 Repository
14. `FaultAccessFacadeImpl` — 故障访问 facade
15. `FaultServiceImpl` — 故障批量导入 service

**excluded_diff_files 主要原因（95个）：**
- 37 个 DTO/Param/Response 类：纯数据容器，无分支
- 8 个接口定义（Interface）：无实现，无分支
- 9 个 Mapper 接口：MyBatis 接口，通过集成测试覆盖
- 7 个 Convertor 类：纯字段映射
- 6 个常量/枚举类：config_only
- 3 个 Controller：通过集成测试/接口测试覆盖
- 其余：Domain Model、VO、DO、配置类等

---

## 需求到代码映射

| 需求 ID | 类名 | 方法名 | 证据 |
|---------|------|--------|------|
| REQ-001 | FaultReasonFacadeImpl | batchUpdateConfigStatus | FaultReasonFacadeImpl.java:252 |
| REQ-002 | FaultReasonServiceImpl | queryFaultReason | FaultReasonServiceImpl.java:55 |
| REQ-003 | FaultReasonFacadeImpl | updateBaseFaultReason | FaultReasonFacadeImpl.java:717 |
| BR-002 | FaultReasonFacadeImpl | batchUpdateConfigStatus | FaultReasonFacadeImpl.java:260 |
| BR-003 | UpdateFaultTypeCommandHandler | execute | UpdateFaultTypeCommandHandler.java:35 |
| BR-005 | FaultReasonFacadeImpl | validateFaultReasonNameParam | FaultReasonFacadeImpl.java:918 |
| BR-006 | FaultReasonFacadeImpl | validateReasonBrandClassParam | FaultReasonFacadeImpl.java:836 |
| BR-007 | FaultReasonFacadeImpl | updateBaseFaultReason | FaultReasonFacadeImpl.java:740 |
| REQ-004 | FaultReasonBinLogCommandHandler | handle | FaultReasonBinLogCommandHandler.java:43 |
| REQ-006 | FaultReasonFacadeImpl | batchUpdateBaseFaultReason | FaultReasonFacadeImpl.java:1480 |
| REQ-008 | FaultBpmApprovalServiceImpl | approveBaseFaultReason | FaultBpmApprovalServiceImpl.java:50 |
| SE-001 | FaultReasonFacadeImpl | validateFaultReasonNameParam | FaultReasonFacadeImpl.java:918 |
| SE-002 | FaultReasonFacadeImpl | validateReasonBrandClassParam | FaultReasonFacadeImpl.java:836 |
| SE-003 | FaultQueryServiceImpl | queryFaultInfoList | FaultQueryServiceImpl.java |
| SE-007 | FaultServiceImpl | importFaultBrandClassData | FaultServiceImpl.java |

---

## EUT 矩阵（按类分组）

### FaultReasonFacadeImpl — 故障原因核心 Facade

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-001 | 正常更新故障原因名称和状态（无BPM流程） | Happy Path / T1 | updateBaseFaultReason | Result.success + updateFaultReasonEditInfo 被调用1次 | REQ-003 |
| EUT-002 | 有审批中的BPM流程时，阻止再次修改 | Exception / T1 | updateBaseFaultReason | Result.fail + message含「审批中」 + BPM未启动 | REQ-008 |
| EUT-003 | 原因配置了SKU，且故障现象有审核中SKU，互斥拦截 | Exception / T1 | updateBaseFaultReason | Result.fail + message含「清除故障原因SKU」 + 无数据写入 | BR-007 |
| EUT-004 | 故障原因名称与其他品类重复，启动BPM前拦截 | Exception / T1 | updateBaseFaultReason | Result.fail + message含「故障原因已存在」 + BPM未启动 | BR-005 |
| EUT-005 | 品类-故障现象下最后一个有效原因被置无效 | Exception / T1 | validateReasonUpdateParam | SfpFaultBizException + FAULT_REASON_LEAST_ONE_VALID + DB不写入 | BR-006 |
| EUT-006 | 提交时faultReasonName为空字符串 | Boundary / T1 | validateReasonUpdateParam | SfpFaultBizException + REASON_NAME_REQUIRED | BR-005 |
| EUT-007 | 正常启用品类的故障原因配置 | Happy Path / T1 | batchUpdateConfigStatus | Result.success(2) + DB 2条状态=有效 | REQ-001 |
| EUT-008 | 品类下有审核中数据，不支持禁用 | Exception / T1 | batchUpdateConfigStatus | Result.fail + DB状态未变 | BR-002 |
| EUT-009 | 批量修改故障原因状态（全部合法） | Happy Path / T1 | batchUpdateBaseFaultReason | Result.success + DB 3条更新 | REQ-006 |
| EUT-010 | 批量修改中某条触发「最后一个有效原因置无效」 | Exception / T1 | batchUpdateBaseFaultReason | 异常 + DB全量不写入 | BR-006 |
| EUT-020 | 并发创建同名故障原因（名称全局唯一并发场景） | Concurrent / T1 | updateBaseFaultReason | 恰好1成功1失败 + DB行数=1 | SE-001 |
| EUT-021 | 逐步置无效，验证底表状态聚合（最后一个有效→无效） | Boundary / T1 | updateBaseFaultReason | 第2次置无效后 causeStatus=0；恢复后=1 | SE-002 |

### FaultReasonServiceImpl — 故障原因查询 Service

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-011 | 品类已开启故障原因，checkNeedFaultReason 返回 true | Happy Path / T1 | checkNeedFaultReason | Result.success(true) | BR-003 |
| EUT-012 | 品类未开启故障原因，checkNeedFaultReason 返回 false | Happy Path / T1 | checkNeedFaultReason | Result.success(false) | BR-003 |
| EUT-013 | brandClassId 为 null，防御性边界 | Boundary / T2 | checkNeedFaultReason | 不抛 NPE，返回 false | BR-003 |
| EUT-014 | 按品类+故障现象查询到有效故障原因列表 | Happy Path / T1 | queryFaultReason | 非空列表，含 faultReasonCode/Name/status | REQ-002 |
| EUT-015 | 无数据品类查询，返回空列表 | Boundary / T2 | queryFaultReason | 空列表，不抛异常 | REQ-002 |

### UpdateFaultTypeCommandHandler — 类型管理双向校验

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-016 | 已开启故障原因的品类尝试设置软件故障第1/2级，拦截 | Exception / T1 | execute | SfpFaultBizException + DB未更新 | BR-003 |
| EUT-017 | 未开启故障原因的品类设置软件故障第2级，允许 | Happy Path / T1 | execute | 无异常 + DB按请求更新 | BR-003 |

### FaultBpmApprovalServiceImpl — BPM 审批

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-018 | 故障原因名称修改审批通过，底表更新 | Happy Path / T1 | approveBaseFaultReason | faultReasonName=新名称 + 审批状态=APPROVED | REQ-008 |
| EUT-019 | BPM 回调 formJson 格式异常，解析失败 | Exception / T1 | approveBaseFaultReason | 异常被捕获 + 底表未变 | REQ-008 |

### FaultReasonBinLogCommandHandler — Binlog 触发器

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-022 | 故障原因关系最后有效变无效，触发底表状态聚合 | Happy Path / T1 | handle | causeStatus=0（底表状态更新） | REQ-004 |
| EUT-023 | Binlog payload 为空或格式异常 | Boundary / T2 | handle | 不抛未捕获异常 + DB不更新 | REQ-004 |

### 跨类集成验证

| EUT | 业务场景 | 路径/风险 | 目标方法 | 核心断言 | 追溯 |
|-----|---------|-----------|---------|---------|------|
| EUT-024 | 两层状态独立验证：修改故障现象状态不影响故障原因关系状态 | Boundary / T1 | FaultQueryServiceImpl.queryFaultInfoList | 返回故障原因关系状态=1，不受故障现象状态影响 | SE-003 |
| EUT-025 | 批量导入超 5000 条，系统拦截 | Boundary / T1 | FaultServiceImpl.importFaultBrandClassData | Result.fail + message含「最多支持5000条」 + DB不写入 | SE-007 |

---

## 不可测项说明

| ID | 原因 | 可测性 |
|----|------|--------|
| REQ-007 | 批量导出为数据格式化，无核心分支 | not_backend_testable |
| REQ-009 | 故障与非故障互斥由系统配置文件控制 | config_only |
| REQ-010 | XMS 三元关系为跨系统接口 | external_system |
| REQ-011 | 灰度切换实现机制待确认（GAP-001） | config_only |
| SE-005 | SKU 互斥端到端需集成测试 | not_backend_testable |
| SE-006 | 灰度路由依赖灰度配置开关 | config_only |
| SE-008 | 故障互斥在 AS 工单系统，不在本仓库 | not_backend_testable |

---

## 自我评审记录

1. 批评者复查：REQ-004 底表状态聚合是否有 binlog 分支 → 补充 EUT-022/023
2. 初稿遗漏 BR-002 取消品类拦截 → 补充 EUT-008
3. SE-001 并发场景需 Concurrent 路径，已加 EUT-020
4. 初稿漏 SE-002 状态聚合边界测试 → 补充 EUT-021
5. FaultServiceImpl.importFaultBrandClassData 方法名需实际确认，已标注 T1 高风险
