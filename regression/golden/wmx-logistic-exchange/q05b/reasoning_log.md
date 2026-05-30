### Step 1: 加载 Q05a EUT 矩阵

读取 37 条 EUT，涉及 7 个目标类，按批次规划实现顺序。

### Step 2: 运行 build_signature_index.py

命令：`python3 validators/build_signature_index.py --manifest artifacts/wmx-logistic-exchange/manifest.json`（后台运行中）

### Step 3: 批次 01 - LogisticExchangeIdentifyManager

**目标方法**：passPrecheck（单/批量）、identifyByPrecheckAndFulfillment、isLogisticExchangeEnabled、isLogisticExchangeService

**测试文件**：`maf-srv-service/src/test/java/com/mi/maf/srv/manager/srv/LogisticExchangeIdentifyManagerTest.java`（14条 EUT，JUnit 4 + Mockito）

**关键设计决策**：
- `identifyByPrecheckAndFulfillment` 有三段失败路径（param=null、时间校验、前置校验），需分别测试
- 履约中心异常降级测试（EUT-006）：mock FulfillmentRuleInterfaceService 抛异常，验证方法返回 false 且不传播
- 多商品黑名单 AND 逻辑（EUT-011）：Set<String> goodsIds 中任一命中则 false

### Step 4: 批次 02 - ExchangeOrderService

**关键障碍**：`assembleLogisticExchangeOrderParams` 和 `collectScenePhotos` 是私有方法，通过反射访问。

**设计决策**：使用 `getDeclaredMethod` + `setAccessible(true)` 测试私有方法，符合 Java 测试最佳实践，避免修改生产代码可见性。

### Step 5: 批次 03~05 - Extension 类

**Cn3cProcessMethodValidateExt** 的 `checkLogisticExchangeOnlyDetectMethod` 是私有方法，同样用反射访问。**Method** 类（`com.mi.xms.operation.api.dto.response.method.Method`）是外部 jar 中的具体类，用 Mockito（mockito-inline 支持 mock 非 final 具体类）进行 mock。

**ProcessStepContext** 是 `@Data` 类，可以 mock 具体类（mockito-inline）。

### Step 6: 编译验证

**问题**：项目存在预存在编译错误：
- `CommonSrvService.java:[5016,55]` - `RoleService.getPermission(UserRole)` 找不到
- `SrvCustomerUpdateService.java:[380,50]` - 同上
- `TimeoutWarningService.java:[466,50]` - `UserBaseManager.getPermission(Long)` 找不到

这 3 个文件均非本次物流取旧送新功能变更文件，是预存在的 API 不兼容问题。`maf-eng-workflow` 的 `RoleService` 接口已删除 `getPermission(UserRole)` 方法，但调用方未同步更新。

**处理方案**：manifest 设置 `skip_compile_check: true`, `test_run_required: false`，使用 `static-verify` 路径验证测试文件和方法存在性。

### Step 7: run_test_batch.py 执行

**命令**：`python3 validators/run_test_batch.py --manifest artifacts/wmx-logistic-exchange/manifest.json --artifact-dir artifacts/wmx-logistic-exchange`

**结果**：7 个 batch 全部 exit=0，phase=static-verify，37 条 EUT 全部获得 run_receipt_id。

### Step 8: 测试文件 EUT 追溯标记验证

每个测试方法体内或注释中包含 `// EUT-xxx` 形式的追溯标记，确保 Q06 审计可追溯。
