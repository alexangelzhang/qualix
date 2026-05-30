# Q05a 推理日志 — failure-cause

### Step 1：加载 Q01 产物

从 `q01/structured.json` 获取需求 ID 清单：
- REQ: REQ-001 ~ REQ-011
- BR: BR-001 ~ BR-014
- SE: SE-001 ~ SE-008

### Step 2：运行 code_index 构建

```bash
python3 validators/build_code_index.py --manifest artifacts/failure-cause/manifest.json
```
结果：110 个 diff 文件（110 个生产类），base_ref=cb038f7f，head_ref=HEAD

### Step 3：diff 文件分类

**included_diff_files（15 个，含业务分支逻辑）：**

| 类名 | 覆盖 EUT |
|------|----------|
| FaultReasonFacadeImpl | EUT-001 ~ EUT-010, EUT-020, EUT-021 |
| FaultReasonServiceImpl | EUT-011 ~ EUT-015 |
| UpdateFaultTypeCommandHandler | EUT-016, EUT-017 |
| FaultBpmApprovalServiceImpl | EUT-018, EUT-019 |
| FaultReasonBinLogCommandHandler | EUT-022, EUT-023 |
| FaultQueryServiceImpl | EUT-024 |
| FaultServiceImpl | EUT-025 |
| FaultFacadeImpl | via EUT-001~004（被 FaultReasonFacadeImpl 调用） |
| FaultListFacadeImpl | non_testable（数据组装，无核心分支） |
| FaultEditServiceImpl | via FaultFacadeImpl |
| FaultReasonBrandClassConfigRepositoryImpl | 基础设施层，通过集成测试覆盖 |
| FaultReasonRelationRepositoryImpl | 基础设施层，通过集成测试覆盖 |
| FaultReasonRepositoryImpl | 基础设施层，通过集成测试覆盖 |
| FaultAccessFacadeImpl | 查询 facade，无复杂分支 |
| FaultReasonRelationBinLogCommandHandler | 类似 FaultReasonBinLogCommandHandler |

**excluded_diff_files（95 个，分类原因）：**
- 37 个 DTO/Request/Response 类：纯数据容器，无分支 → `generated_code`
- 8 个接口定义（Facade/Repository/Service 接口）→ `generated_code`
- 9 个 Mapper 接口 → `generated_code`（MyBatis接口，无Java分支）
- 7 个 Convertor 类 → `generated_code`（字段映射）
- 6 个常量/枚举类 → `config_only`
- 5 个 Domain Model 类 → `generated_code`
- 3 个 Controller 类 → `not_backend_testable`（集成/接口测试）
- 20 个基础设施支持类（VO, DO, 序列, 配置）→ `generated_code`

### Step 4：需求到代码映射

| 需求 | Java 类 | 方法 | EUT |
|------|---------|------|-----|
| REQ-001 | FaultReasonFacadeImpl | batchUpdateConfigStatus | EUT-007/008 |
| REQ-002 | FaultReasonServiceImpl | queryFaultReason | EUT-014/015 |
| REQ-003 | FaultReasonFacadeImpl | updateBaseFaultReason | EUT-001/002/003/004 |
| BR-002 | FaultReasonFacadeImpl | batchUpdateConfigStatus | EUT-008 |
| BR-003 | UpdateFaultTypeCommandHandler | execute | EUT-016/017 |
| BR-003 | FaultReasonServiceImpl | checkNeedFaultReason | EUT-011/012/013 |
| BR-005 | FaultReasonFacadeImpl | validateFaultReasonNameParam | EUT-004 |
| BR-006 | FaultReasonFacadeImpl | validateReasonBrandClassParam | EUT-005 |
| BR-007 | FaultReasonFacadeImpl | updateBaseFaultReason | EUT-003 |
| REQ-004 | FaultReasonBinLogCommandHandler | handle | EUT-022/023 |
| REQ-006 | FaultReasonFacadeImpl | batchUpdateBaseFaultReason | EUT-009/010 |
| REQ-008 | FaultBpmApprovalServiceImpl | approveBaseFaultReason | EUT-018/019 |
| SE-001 | FaultReasonFacadeImpl | updateBaseFaultReason | EUT-020 |
| SE-002 | FaultReasonFacadeImpl | updateBaseFaultReason | EUT-021 |
| SE-003 | FaultQueryServiceImpl | queryFaultInfoList | EUT-024 |
| SE-007 | FaultServiceImpl | importFaultBrandClassData | EUT-025 |

### Step 5：关键代码分支分析

**FaultReasonFacadeImpl.updateBaseFaultReason（主干方法，最高风险）：**
1. JSON 解析失败 → catch → Result.fail（EUT-001 异常分支）
2. validateReasonUpdateParam 抛出 → catch → Result.fail（EUT-006）
3. checkFaultReasonHaveBpm = true → 审批中拦截（EUT-002）
4. hasReasonSku && checkHaveBpmFaultSku → SKU互斥拦截（EUT-003）
5. bpmBusinessLine == null → 直接更新（EUT-001 Happy）
6. bpmBusinessLine 非空 → 校验名称 → 启动BPM（EUT-004/020）

**validateReasonBrandClassParam（核心校验逻辑）：**
- 聚合计算当前品类-故障现象下有效原因数量
- 变更后有效数量 == 0 → 拒绝（EUT-005, EUT-010）

### Step 6：不可测项说明

- REQ-007（批量导出）：数据格式化，无核心分支
- REQ-009（故障互斥）：配置文件控制，无Java分支
- REQ-010（XMS三元关系）：跨系统接口
- REQ-011 + SE-006（灰度切换）：GAP-001 未解决
- SE-005（SKU互斥端到端）：需要集成测试
- SE-008（AS工单互斥）：不在本仓库范围

### Step 7：自检

- [x] 所有 110 个 diff 文件进入 included 或 excluded
- [x] included=15，excluded=95，scope_conflicts=0，合计 110
- [x] 每条 EUT 有 assertion_blueprint
- [x] 每个 assertion_blueprint 有类型、对象、期望值
- [x] branch_inventory 覆盖所有 included 类的关键方法
- [x] business_outcomes 与 branch_inventory 1:1 映射
