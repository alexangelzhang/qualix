### Step 1: 加载审计输入

- Q01 requirements: 17 REQ/BR + 10 SE + 2 GAP + 3 OPEN
- Q05a EUT: 37条，7个目标类
- Q05b code_status: 37条全部 passes=true（static-verify）

### Step 2: 四层审计 - 有没有

37条 EUT 均有对应测试方法，无 MISSING 项。
test_class/test_method/test_file 均已在 code_status 中注册。

### Step 3: 四层审计 - 全不全

按路径类型：
- Happy Path (8条): EUT-001, EUT-012, EUT-013, EUT-015, EUT-017, EUT-019, EUT-022, EUT-026 → 全部有对应测试
- Exception (14条): EUT-002~006, EUT-008, EUT-011, EUT-018, EUT-020~021, EUT-023~025, EUT-028 → 全部有对应测试
- Boundary (6条): EUT-004, EUT-005, EUT-007, EUT-009, EUT-010, EUT-016 → 全部有对应测试

### Step 4: 四层审计 - 好不好

**强断言**（assertEquals, assertFalse, verify(mock).method(args)）：
- LogisticExchangeIdentifyManager 全部使用 assertEquals(Boolean.TRUE/false) + verify() → 强
- ExchangeOrderService 使用 assertEquals("2", ...), assertEquals("", ...), assertEquals(2, size()) → 强
- Cn3c Extension 类使用 verify(srvServiceExtendManager).save/delete() + verify(never()) → 强
- OrderCenterConsumer 使用 verify(srvProcessService).addOpProcess(contains(...)) → 强

**弱断言识别**：
- EUT-037: assertEquals(SERVICE_NO, srvService.getId()) 断言了参数传入但未验证降级后的 special_approval_id → PARTIAL

### Step 5: 四层审计 - 准不准

期望值来源检查：
- "unified_replacement=2" → 来自生产常量 LOGISTIC_UNIFIED_REPLACEMENT_VALUE = "2" [ExchangeOrderService.java] ✓
- "特批单号传递" → APPROVAL_ID="SA-001" 是测试构造值，匹配业务语义 ✓
- "LOGISTIC_EXCHANGE" + "Enable.Y" → 来自生产枚举 SrvTagEnum.LOGISTIC_EXCHANGE 和 Enable.Y ✓
- "换新单取消回传" → contains("换新单取消回传") 匹配生产日志格式 [OrderCenterConsumer.java] ✓

### Step 6: 覆盖率审计

coverage_required=false，无 JaCoCo 报告。
按语义覆盖率计划：5个关键目标类的核心分支均有 EUT 覆盖：
- LogisticExchangeIdentifyManager: 7个核心分支 → 12条 EUT
- ExchangeOrderService: 4个核心分支 → 7条 EUT
- Cn3c Extension: 每类3~5条 EUT
- OrderCenterConsumer: 3条 EUT 覆盖取消路径

**未覆盖的集成级场景**（已在不可测项中说明）：
- REQ-002（强安装工单流）、REQ-005（XMS展示）、REQ-006（妥投全链路）、REQ-008（拒收换）

### Step 7: Phantom EUT 检查

全部 37条 EUT ID 均来自 Q05a eut_matrix.json，无 phantom EUT。

### Step 8: 自检

- T1 EUT 100% 审计：26条 T1 EUT 全部出现在 audit_result.json ✓
- PARTIAL EUT（EUT-037）已有 FINDING-001 ✓
- coverage_gate 设置为 null（无 JaCoCo）并说明原因 ✓
