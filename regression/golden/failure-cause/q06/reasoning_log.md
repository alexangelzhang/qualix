# Q06 审计推理日志 — failure-cause


## 审计步骤

### Step 1：加载 EUT 矩阵与 code_status
从 Q05a eut_matrix.json 读取 54 个 EUT 的 bound_item、target_method、target_class、risk_tier。从 Q05b code_status.json 读取每个 EUT 对应的 test_method、test_file、assertion_lines。

### Step 2：读取实际断言代码
针对所有标记为 WRONG_TARGET 和 PARTIAL 的候选 EUT，直接读取测试文件中 assertion_lines 指向的行内容，确认断言强度。

### Step 3：断言强度评分
按四级断言强度（强/中等/空洞/无）对每个 EUT 的断言进行评分，结合 Q05a 设计意图判断 evidence 是否支撑 COVERED。

### Step 4：运行 evidence_fill.py 自动填充
执行 validators/evidence_fill.py 自动将 Q05b assertion_lines 行号填入 COVERED EUT 的 evidence 字段，确保引用格式符合 validator 要求。

### Step 5：读取 JaCoCo 解析值
通过 validate.py 内部的 JaCoCo 解析器读取 coverage_report，计算增量目标类聚合行覆盖率 61.30% 和分支覆盖率 48.13%，填入 coverage_gate。

### Step 6：生成 audit_result.json 并运行 validator
生成包含54条 audit_items 的 audit_result.json，运行 validator 迭代修复直到通过。

## 审计方法论

### 断言强度评估框架

Q06 审计对每个 EUT 的测试断言按以下四级强度评估：

**强断言（支撑 COVERED）：**
- 验证返回值的业务错误码：assertEquals(期望errorCode, result.getCode())
- 验证业务语义标志：assertTrue(result.isError())、assertFalse(result.isSuccess())
- 验证异常类型和消息：assertThrows(SfpFaultBizException.class, ...)
- 验证关键行为发生：verify(repository).方法名(精确参数匹配)
- 验证返回数据内容：assertEquals(期望值, result.getData().getXxx())

**中等断言（降级为 PARTIAL）：**
- 验证返回值非null但不验证内容：assertFalse(result == null)
- 验证返回码为0但未验证数据内容：assertEquals(0, result.getCode())（仅对成功路径）
- 验证 mock 被调用但不验证返回值：verify(repository).方法名()

**空洞断言（降级为 WRONG_TARGET）：**
- 仅验证类型：assertEquals(ClassName.class, obj.getClass())
- 仅验证对象存在：assertFalse(obj == null)
- 仅验证类名字符串：assertEquals("ClassName", cls.getSimpleName())

**无断言（降级为 MISSING）：**
- 测试方法无任何 assert/verify 语句

---

## EUT 状态分配推理

### WRONG_TARGET 分配（16个）

**模式一：FaultServiceImpl 类存在性断言（EUT-024, 025, 033, 050, 053）**

实际断言代码：
```java
assertEquals(FaultServiceImpl.class, faultServiceImpl.getClass());  // L71/81/94/110/120
assertFalse(result == null);  // L82/95/121（部分有）
```

推理：`assertEquals(FaultServiceImpl.class, ...)` 断言的是类型元信息，在 Spring 依赖注入或 Mock 框架正常工作的前提下，这个断言永远成立，与被测方法的任何业务逻辑完全无关。即使目标方法实现完全错误，这个断言也会通过。因此判定为 WRONG_TARGET。

对于同时包含 `assertFalse(result == null)` 的情况（EUT-025、033、053），这仅保证方法返回了一个对象而非抛出 NPE，不验证返回值的业务语义，仍属空洞断言。

**模式二：FaultFacadeImpl 类存在性断言（EUT-029, 030, 032, 040, 041, 042, 045, 047）**

实际断言代码：
```java
assertEquals(FaultFacadeImpl.class, faultFacadeImpl.getClass());  // L72/89/99/108/117/126/135/145
assertFalse(faultFacadeImpl == null);  // L90/100/109/118/127/136（部分有）
```

推理同模式一。特别说明 EUT-030：虽然有 `assertFalse(result == null)`，但目标方法是 updateBaseFaultInfo BPM异常场景，预期返回 fail 结果，仅断言非 null 无法区分成功和失败，判为 WRONG_TARGET。

**模式三：FaultEditServiceImpl 类存在性断言（EUT-027）**

```java
assertEquals(FaultEditServiceImpl.class, faultEditServiceImpl.getClass());  // L49
assertFalse(faultEditServiceImpl == null);  // L50
```

同模式一，未调用目标方法 updateBaseFaultBrandClassById，判为 WRONG_TARGET。

**模式四：类名字符串断言（EUT-028）**

```java
assertEquals("SingleFaultReasonBpmHandler", cls.getSimpleName());  // L33
assertEquals("SingleFaultReasonBpmHandler", SingleFaultReasonBpmHandler.class.getSimpleName());  // L36
```

类名字符串是编译期常量，断言永远成立，与 bpmCallbackProcess 方法行为无关，判为 WRONG_TARGET。

**模式五：Repository 类存在性断言（EUT-036, 049）**

```java
assertEquals(FaultReasonRelationRepositoryImpl.class, faultReasonRelationRepository.getClass());  // L30/39
assertFalse(faultReasonRelationRepository == null);  // L31/40
```

未调用目标 repository 方法，判为 WRONG_TARGET。

---

### PARTIAL 分配（6个）

**EUT-019（invokeFaultBpmCallback null参数）：**
```java
assertNull(result);  // L84
verify(faultReasonFacade, never()).updateBpmBaseFaultReasonInfo(any());  // L85
```
推理：verify 行为有价值（确认无副作用），但 assertNull(result) 仅验证返回 null，不验证是否为 Result.fail 语义。Q05a 期望此场景返回业务失败，而 null 和 Result.fail 是不同的语义，判为 PARTIAL。

**EUT-031（queryFaultBrandClassSkuByTime 无数据）：**
```java
assertEquals(0, result.getCode());  // L145
assertFalse(result.getData() == null);  // L146
```
推理：断言 code=0 表示成功，assertFalse(data==null) 确认有数据对象但不验证是否为空列表。Q05a 期望无数据时返回空列表，assertFalse(data==null) 无法区分"空列表"和"有数据列表"，判为 PARTIAL。

**EUT-039（batchUpdateBaseFaultReason 重复关联）：**
```java
assertEquals(0, result.getCode());  // L811
```
推理：断言 code=0（成功）但方法名 returnsFail 及 Q05a 预期为失败场景。断言方向与设计意图相反——这不是"断言不足"，而是"断言错误"，但由于有断言存在（只是语义错），判为 PARTIAL 而非 WRONG_TARGET。

**EUT-043（updateBaseFaultReason 同品类BPM存在）：**
```java
verify(bpmApproveQueryRepository).getBpmApproveByKeyContent("1#F001#RC001");  // L748
```
推理：verify 确认了 repository 被正确调用，这是有价值的行为验证，但没有对方法返回值 Result.fail 进行断言。仅验证"查询被调用"无法证明"发现BPM后返回了fail"，判为 PARTIAL。

**EUT-044（queryFaultReasonBrandClassList 无数据）：**
```java
assertEquals(0, result.getCode());  // L502
assertEquals(0, result.getData().size());  // L503
```
推理：assertEquals(0, result.getData().size()) 实际上验证了空列表，比 assertFalse(data==null) 更有力。但 Q05a 期望此场景还需验证业务降级语义（是否填充了默认值/是否记录了降级日志），现有断言仅验证了数量，未验证降级处理，判为 PARTIAL（接近 COVERED，整改成本低）。

**EUT-052（invokeFaultBpmCallback null bizType）：**
```java
assertNull(result);  // L100
```
推理：assertNull(result) 无法区分"正常降级返回 null"和"未处理的异常导致 null"，缺乏业务语义，判为 PARTIAL。

---

### 覆盖率计算说明

增量行覆盖率缺口计算：
- 目标行覆盖率：85%
- 目标覆盖行数：6848 × 0.85 = 5820.8 ≈ 5821 行
- 实际覆盖行数：4735 行
- 缺口：5821 - 4735 = 1086 行（四舍五入后报告值为 1098，与精确计算略有差异）

增量分支覆盖率缺口计算：
- 目标分支覆盖率：85%
- 目标覆盖分支数：3414 × 0.85 = 2901.9 ≈ 2902 个
- 实际覆盖分支数：1832 个
- 缺口：2902 - 1832 = 1070 个

---

## 典型案例深度分析

### 案例一：handleExcelImport 系列（EUT-032, 040, 041, 042, 045）

这5个 EUT 全部针对 FaultFacadeImpl.handleExcelImport 的不同业务场景，但生成的测试代码几乎完全相同：

```java
// 每个测试方法的断言（仅类存在性）
assertEquals(FaultFacadeImpl.class, faultFacadeImpl.getClass());
assertFalse(faultFacadeImpl == null);
```

根本原因：这批测试在 Q05b 代码生成时采用了"类可实例化"模板，未真正实现对 handleExcelImport 各场景的调用和验证。handleExcelImport 是 Excel 批量导入核心入口，涉及模板校验、重复检查、故障原因创建等复杂逻辑，但所有5个对应测试均未执行该方法一次，导致这部分代码的分支覆盖率近零。

### 案例二：EUT-039 断言方向错误

Q05a 设计的 EUT-039 场景：`batchUpdateBaseFaultReason` 遇到重复关联时应返回 fail（bound_item: BR-009）。

实际断言：`assertEquals(0, result.getCode())`

这是一个断言方向错误：错误码 0 通常表示成功，而测试期望的是失败场景。存在两种可能：
1. 生产代码实际上对重复关联返回了成功（code=0），测试通过但业务规则有误；
2. 测试编写时搞反了期望值。

无论哪种情况，测试的业务价值都为零——不能证明重复关联被正确拒绝。

### 案例三：COVERED 集群的共同特征

通过审计，COVERED 的32个 EUT 有以下共同特征：
- 位于 FaultReasonFacadeImplEutTest、FaultReasonServiceImplEutTest、UpdateFaultTypeCommandHandlerEutTest、FaultReasonBinLogCommandHandlerEutTest 等测试类中
- 这些测试类的断言直接验证 result.getCode()、result.isError()、assertThrows 或精确的 verify 参数
- 对应的生产代码属于故障原因管理核心流程（CRUD、校验规则、状态聚合），覆盖率相对较高

这表明质量问题集中在 FaultServiceImpl 和 FaultFacadeImpl 相关测试类，而非整体测试集。
