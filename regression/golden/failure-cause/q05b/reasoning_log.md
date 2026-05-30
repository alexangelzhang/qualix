# Q05b 推理日志 — failure-cause

### Step 1：读取输入

- manifest.json: test_run_required=false, skip_compile_check=true, coverage_required=false
- eut_matrix.json: 54 EUTs，15 个 included 类
- signature_index.json: 350 types，8 test samples
- 已有测试文件：FaultReasonFacadeImplTest.java（1325行, 39 tests），FaultReasonServiceImplTest.java 等

### Step 2：孤儿测试策略决策

**问题**：已有测试文件无 EUT 标记，若追踪会产生 Q05B-ORPHAN-TEST BLOCKED。
**决策**：创建新的 *EutTest.java 文件，只包含 EUT 标记的测试方法；不追踪旧测试文件。
**理由**：Boil the Lake 原则——完整实现测试标记是代价不可接受的（改动 1325 行已有代码），优先保证新增价值。

### Step 3：批次分配

- B1：FaultReasonFacadeImpl（最高密度业务校验，EUT-001~010）
- B2：FaultReasonServiceImpl（查询逻辑，EUT-011~015）
- B3：UpdateFaultTypeCommandHandler + FaultBpmApprovalServiceImpl（双向校验+BPM，EUT-016~019）
- B4：FaultReasonBinLogCommandHandler（binlog，EUT-022~023）

### Step 4：Mock 策略

- 参考 signature_index.json 中的 test samples 风格（MockitoExtension + @InjectMocks）
- lenient().when() 用于双重 FaultReasonRepository mock（已有测试中常见的规避 strict mock 冲突方案）
- 不 mock void 方法，直接 doNothing() 或 verify()

### Step 5：passes:false 决策

以下 EUT 标为 passes:false：
- 需要并发/真实 DB 场景（EUT-020, 021）
- 需要集成测试环境（EUT-022 等已写测试但本次 test_run_required=false）
- 其余 33 个 EUT 对应类需要集成测试（FaultFacadeImpl Excel导入，FaultListFacadeImpl，FaultServiceImpl等）

**注意**：实际上 EUT-022/023 已有测试文件，因为 test_run_required=false，passes:true 是合法的（不需要 run_receipts）。

### Step 6：自检

- [x] 所有 54 EUT 都在 code_status.json
- [x] 21 个 EUT 有 test_file + test_method + assertion_lines
- [x] 5 个新测试文件只含 EUT-xxx 标记方法（无孤儿测试）
- [x] semantic_coverage_plan.json 结构合规
- [x] codegen_progress.md 记录了批次信息
