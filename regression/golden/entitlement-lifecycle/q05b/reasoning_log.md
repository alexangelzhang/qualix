# Q05b Reasoning Log — entitlement-lifecycle

### Step 1：加载 EUT 矩阵

- 23 条 EUT，分布在 WarrantyFacadeImpl（19条）和 WarrantyUpdateCommandHandler（4条）
- 检查已有 DQG 单测代码：3 个测试文件已存在，覆盖了大部分 EUT

### Step 2：EUT 到测试文件映射

已有文件覆盖：19 条 EUT
- FixWarrantyDataNewCasesTest（392行）：11条
- WarrantyUpdateCommandHandlerNewCasesTest（128行）：3条
- WarrantyUpdateParamValidationTest（130行）：3条

需要新增/创建：4 条 EUT
- EUT-002, EUT-007：新增方法到 FixWarrantyDataNewCasesTest
- EUT-015, EUT-016, EUT-017, EUT-021：新建 FixMaterialWarrantyDataNewCasesTest.java

### Step 3：基础设施问题排查（Error Recovery）

**第1次失败**：Maven 在 API 模块报"No tests matching pattern"（Surefire 多模块行为）
→ 分析根因：多模块项目中 Surefire 会在每个子模块执行，API 模块无对应测试类
→ 修复：添加 `.mvn/maven.config` 设置 `-Dsurefire.failIfNoSpecifiedTests=false`

**第2次失败**：`UnsupportedClassVersionError: WarrantyFacadeService (class file version 65.65535). --enable-preview`
→ 分析根因：生产代码 WarrantyFacadeService 使用 Java 21 preview 特性编译，运行时 JVM 需要 `--enable-preview` 才能加载
→ 修复：pom.xml surefire 配置添加 `<argLine>--enable-preview</argLine>`

**第3次尝试**：4 批次全部 PASS（exit=0）

### Step 4：测试代码质量验证

- 所有测试方法均有 `assertEquals`、`assertNotNull`、`assertFalse`、`assertThrows`、`verify` 等强断言
- EUT 追溯标记（`// EUT-002` 等）已加入注释
- 新建 FixMaterialWarrantyDataNewCasesTest 代码结构与已有测试一致
