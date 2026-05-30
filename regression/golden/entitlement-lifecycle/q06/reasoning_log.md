# Q06 Reasoning Log — entitlement-lifecycle

### Step 1：加载 Q01/Q05a/Q05b 产物

- Q01 structured.json: REQ-001/002, BR-001~007, SE-001~009
- Q05a eut_matrix.json: 23 条 EUT
- Q05b code_status.json: 23/23 passes=true，4 批次 run_receipt exit=0

### Step 2：四层审计逐 EUT 判定

**有没有**：23 条 EUT 全部有测试文件和测试方法，且文件存在于仓库。

**全不全**：
- Happy Path（EUT-004, 006, 007, 010, 012, 013, 014, 015, 016, 019, 023）：覆盖锁定/非锁定/实时计算路径、枚举解析 code/numeric、纯日期格式等
- Exception（EUT-001~003, 005, 008, 009, 011, 017, 018, 020~022）：9个字段格式错误路径、起算类型非法、command/threeGuarantee null
- Boundary（EUT-004, 007, 009）：纯日期、数字 id 字符串、9字段全 null

**好不好**：
- 所有 COVERED 条目均包含 assertEquals/assertFalse/verify 等强断言
- 无单纯 assertNotNull 或 assertDoesNotThrow 作为唯一断言
- 业务语义覆盖：错误消息内容断言（等于具体中文错误文案）、时间类型解析正确值断言、老字段兼容断言

**准不准**：
- 错误消息断言的期望值来自生产代码中的硬编码字符串（如「退货开始时间格式错误」），与代码一致
- 时间类型 id 来自 StartTimeType 枚举（ACTIVATION→1, DELIVERY2C→0, DELIVERY2B→3）
- revisable 来自 RevisableType.NO.getId() 生产常量

**覆盖率**：coverage_required=false，无数据，记录为 INFO 风险。

### Step 3：Findings 判定

无 T1 MISSING 或 WRONG_TARGET，无 ERROR/WARN 级 finding。3条 INFO 为：
1. 覆盖率未量化（coverage_required=false）
2. EUT-009/018 测试共享（合理）
3. EUT-019/023 测试共享（合理）

### Step 4：结论

**PASS_WITH_RISKS**：23/23 COVERED，3条 INFO，无 BLOCKED 项。
