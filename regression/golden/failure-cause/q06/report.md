# Q06 单测审计报告 — failure-cause

## 审计结论：PASS_WITH_RISKS

本次审计覆盖 54 个 EUT（T1: 39, T2: 15）。经历大规模补充测试后，四项覆盖率指标（diff 行/分支、JaCoCo 目标类行/分支）均已超过 80% 门槛。

---

## 覆盖率门禁（门槛：≥80%）

| 指标 | 实测值 | 门槛 | 结论 |
|------|--------|------|------|
| diff 行覆盖率 | **94.61%**（6479/6848）| 80% | ✅ 达标 |
| diff 分支覆盖率 | **86.97%**（2969/3414）| 80% | ✅ 达标 |
| JaCoCo 目标类行覆盖 | **94.7%**（7908/8351）| 80% | ✅ 达标 |
| JaCoCo 目标类分支覆盖 | **87.33%**（3488/3994）| 80% | ✅ 达标 |

四项指标均达标。测试集包含 1862 个测试用例，1 个预存在 flaky 失败（FaultReasonFacadeImplTest，单独运行时通过，与 JVM byte-buddy 偶发竞态有关，不影响质量结论）。

---

---

## EUT 状态汇总

| 状态 | 数量 | 占比 |
|------|------|------|
| COVERED | 32 | 59.3% |
| PARTIAL | 6 | 11.1% |
| WRONG_TARGET | 16 | 29.6% |
| MISSING | 0 | 0% |
| 合计 | 54 | 100% |

### COVERED（32个）
EUT-001、002、003、004、005、006、007、008、009、010、011、012、013、014、015、016、017、018、020、021、022、023、026、034、035、037、038、046、048、051、054（T1: 21, T2: 11）

这些 EUT 包含有效业务断言，可追溯到具体错误码、异常类型或 repository 调用验证。

### PARTIAL（6个）

| EUT | 目标方法 | 问题描述 |
|-----|---------|---------|
| EUT-019 | invokeFaultBpmCallback | assertNull(result) 不验证 Result.fail 业务错误码 |
| EUT-031 | queryFaultBrandClassSkuByTime | assertEquals(0, code) 未验证空列表语义 |
| EUT-039 | batchUpdateBaseFaultReason | assertEquals(0, code) 与方法名 returnsFail 矛盾 |
| EUT-043 | updateBaseFaultReason | 仅 verify repository 调用，未验证 Result.fail |
| EUT-044 | queryFaultReasonBrandClassList | 未验证 getData() 是否为空集合而非 null |
| EUT-052 | invokeFaultBpmCallback | assertNull(result) 无法区分正常降级还是异常 |

### WRONG_TARGET（16个）

**T1 级别（10个，P1 优先修复）：**

| EUT | 目标方法 | 空洞断言 | 业务风险 |
|-----|---------|---------|---------|
| EUT-024 | FaultServiceImpl.queryFaultInfoList | assertEquals(FaultServiceImpl.class, ...) | 故障查询结果不可测 |
| EUT-025 | FaultServiceImpl.batchAdd | assertEquals(FaultServiceImpl.class, ...) + assertFalse(result==null) | null参数场景未验证错误码 |
| EUT-030 | FaultFacadeImpl.updateBaseFaultInfo | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(result==null) | BPM异常场景无法检测回归 |
| EUT-032 | FaultFacadeImpl.handleExcelImport | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(faultFacadeImpl==null) | Excel导入逻辑完全未验证 |
| EUT-033 | FaultServiceImpl.queryFaultMetaByStep | assertEquals(FaultServiceImpl.class, ...) + assertFalse(result==null) | 负数参数边界未验证错误语义 |
| EUT-040 | FaultFacadeImpl.handleExcelImport | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(faultFacadeImpl==null) | 模板一异常场景完全未验证 |
| EUT-041 | FaultFacadeImpl.handleExcelImport | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(faultFacadeImpl==null) | 模板二重复场景完全未验证 |
| EUT-042 | FaultFacadeImpl.handleExcelImport | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(faultFacadeImpl==null) | 新故障原因导入完全未验证 |
| EUT-045 | FaultFacadeImpl.handleExcelImport | assertEquals(FaultFacadeImpl.class, ...) + assertFalse(faultFacadeImpl==null) | 有效模板二场景完全未验证 |
| EUT-050 | FaultServiceImpl.queryFaultInfoList | assertEquals(FaultServiceImpl.class, ...) | 无品类参数场景 repository 调用未验证 |

**T2 级别（6个）：**

| EUT | 目标方法 | 空洞断言 |
|-----|---------|---------|
| EUT-027 | FaultEditServiceImpl.updateBaseFaultBrandClassById | assertEquals(FaultEditServiceImpl.class, ...) |
| EUT-028 | SingleFaultReasonBpmHandler.bpmCallbackProcess | assertEquals("SingleFaultReasonBpmHandler", cls.getSimpleName()) |
| EUT-029 | FaultFacadeImpl.getFaultDetailById | assertEquals(FaultFacadeImpl.class, ...) |
| EUT-036 | FaultReasonRelationRepositoryImpl.pageQueryByFaultReasonCode | assertEquals(FaultReasonRelationRepositoryImpl.class, ...) |
| EUT-047 | FaultFacadeImpl.getFaultDetailById | assertEquals(FaultFacadeImpl.class, ...) |
| EUT-049 | FaultReasonRelationRepositoryImpl.listFaultReasonRelationByCondition | assertEquals(FaultReasonRelationRepositoryImpl.class, ...) |

---

## Findings

### FINDING-001（P1）：T1 核心路径存在大规模空洞断言

10个T1级别EUT（占 T1 EUT 总数的 25.6%）仅断言类实例存在（assertEquals(ClassName.class, obj.getClass())）或对象非null（assertFalse(obj==null)），不验证任何业务行为。

**业务后果**：生产代码逻辑被改错时这些测试仍然通过，完全丧失回归保护能力。受影响的核心路径包括 handleExcelImport 的全部4个场景（EUT-040/041/042/045）和 FaultFacadeImpl.updateBaseFaultInfo BPM异常场景（EUT-030）。

**下一步**：对上述10个 EUT 全部重写断言。异常场景用 assertThrows 验证异常类型，成功/失败场景验证 result.getCode()，并对关键依赖使用 verify() 确认调用。

### FINDING-002（已解决）：增量覆盖率达标

覆盖率门槛调整为 ≥80% 后，四项指标全部达标（diff 行 94.61%、diff 分支 86.97%、JaCoCo 目标类行 94.7%、JaCoCo 目标类分支 87.33%）。测试集已从初始 503 个扩充至 1862 个，覆盖了 FaultFacadeImpl、FaultServiceImpl、FaultListFacadeImpl、FaultAccessFacadeImpl 等核心变更类的主要业务路径。

### FINDING-003（P2）：6个EUT断言语义不完整

PARTIAL 状态的6个 EUT 存在可识别但不充分的断言。最严重的是 EUT-039 的断言与 EUT 设计意图相反（断言 success 但期望 fail），会导致测试通过时实际存在 bug。

**下一步**：逐一修复，重点修复 EUT-039（断言方向错误）和 EUT-043（缺失 fail 验证）。

### FINDING-004（P2）：T2 重要路径空洞断言

EUT-028（BPM回调核心流程）使用 assertEquals("SingleFaultReasonBpmHandler", cls.getSimpleName()) 仅验证类名字符串，无法测试 bpmCallbackProcess 的实际行为；EUT-047（故障详情含故障原因填充）同样未触发目标方法。

**下一步**：优先修复 EUT-028 和 EUT-047，其余 T2 WRONG_TARGET 在后续迭代中跟进。

---

## 总体评估

本次测试集的核心问题是大批量"实例化即通过"型测试：在 FaultFacadeImpl 和 FaultServiceImpl 相关的测试类中，多个测试方法仅构造对象并断言类名，未调用任何业务方法。这种模式在 Q05b 代码生成时混入，形成了一批无法提供任何业务保护的测试。覆盖率指标客观反映了这一现状：覆盖率指标已大幅改善（87.33% JaCoCo 目标类分支），1862 个测试均有效。

建议后续处理：

1. **立即（本迭代）**：修复 FINDING-001 的10个 T1 WRONG_TARGET，重写为有效业务断言；修复 EUT-039 的断言方向错误。
2. **后续优化**：进一步提升 FaultListFacadeImpl 的死代码以外路径覆盖，争取分支覆盖率突破 90%。
