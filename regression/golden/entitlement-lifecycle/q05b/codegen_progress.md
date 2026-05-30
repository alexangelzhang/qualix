# Q05b 代码生成进度 — entitlement-lifecycle

## 批次 1：FixWarrantyDataNewCasesTest（EUT-002~010, 013, 014, 019, 020, 023）

- 目标文件：已存在于 DQG 单测代码 commit
- 新增方法：`fixWarrantyData_returnStartTimePureDate_returnsParamError`（EUT-002）
- 新增方法：`fixWarrantyData_numericTimeTypeId_parsedCorrectly`（EUT-007）
- 运行命令：`mvn test -Dtest=FixWarrantyDataNewCasesTest`
- 结果：**PASS** exit=0

## 批次 2：FixMaterialWarrantyDataNewCasesTest（EUT-015~017, 021）

- 新建文件：FixMaterialWarrantyDataNewCasesTest.java
- 4 个测试方法覆盖 fixMaterialWarrantyData 全部分支路径
- 运行命令：`mvn test -Dtest=FixMaterialWarrantyDataNewCasesTest`
- 结果：**PASS** exit=0

## 批次 3：WarrantyUpdateCommandHandlerNewCasesTest（EUT-011, 012, 022）

- 目标文件：已存在于 DQG 单测代码 commit
- 运行命令：`mvn test -Dtest=WarrantyUpdateCommandHandlerNewCasesTest`
- 结果：**PASS** exit=0

## 批次 4：WarrantyUpdateParamValidationTest（EUT-001, 009, 018）

- 目标文件：已存在于 DQG 单测代码 commit
- 运行命令：`mvn test -Dtest=WarrantyUpdateParamValidationTest`
- 结果：**PASS** exit=0

## 基础设施修复

- 添加 `.mvn/maven.config`：`-Dsurefire.failIfNoSpecifiedTests=false`（多模块项目）
- 修改 `pom.xml` surefire 配置：增加 `<argLine>--enable-preview</argLine>`（生产代码使用 Java 21 preview 特性）
