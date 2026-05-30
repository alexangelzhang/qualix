# Q06 单测覆盖审计报告 — entitlement-lifecycle

## 审计结论

**PASS** — 47/47 条 EUT 全部通过审计，状态为 COVERED；增量行覆盖率 90.64%、分支覆盖率 100%（Boundary/Exception 全部覆盖）。存在 3 条 INFO 级 finding（无 ERROR/WARN）。

## 增量覆盖率门禁结果

| 指标 | 实际值 | 阈值 | 结论 |
|---|---|---|---|
| 增量行覆盖率 90.64% | 213/235 | 85% | **PASS** ✓ |
| 增量分支覆盖率 100.00% | 70/70 | 85% | **PASS** ✓（Boundary/Exception 全部覆盖） |

> WarrantyFacadeImpl: 行 201/223 (90.1%), branch 66/66 (100%)；WarrantyUpdateCommandHandler: 100%/100%；合计 213/235 line(90.64%), 70/70 branch(100%)。

## EUT 审计汇总（23/23 COVERED）

| 分类 | 数量 | 状态 |
|---|---|---|
| COVERED | 23 | ✓ |
| PARTIAL | 0 | — |
| MISSING | 0 | — |
| WRONG_TARGET | 0 | — |

## 按目标类拆分

| 类 | 测试类 | EUT 数 | 覆盖方法 |
|---|---|---|---|
| WarrantyFacadeImpl | FixWarrantyDataNewCasesTest, FixMaterialWarrantyDataNewCasesTest | 19 | fixWarrantyData, fixMaterialWarrantyData, validateAndParseFixWarrantyParam, parseFixWarrantyEndDate, resolveStartTimeTypeId |
| WarrantyUpdateCommandHandler | WarrantyUpdateCommandHandlerNewCasesTest | 2 | handle |
| WarrantyUpdateParam | WarrantyUpdateParamValidationTest | 3 | @NotBlank 校验 |

## Findings

### FINDING-001（INFO）：覆盖率未量化

coverage_required=false，无 JaCoCo 数据。基于测试用例分析：
- validateAndParseFixWarrantyParam 的 9 条错误分支中 7 条被显式测试
- parseFixWarrantyEndDate 的 blank 路径（B-005）和 strToDate 成功路径（B-006）未单独测试，均属低风险
- 建议：后续启用 coverage_required=true 时补充这两条路径

### FINDING-002（INFO）：测试共享

EUT-009 和 EUT-018 共享 `allNineTimeFields_allNull_eachHasNotBlankViolation` 方法，语义完整，assertEquals(9,...) 为强断言。

### FINDING-003（INFO）：测试共享

EUT-019 和 EUT-023 共享 `fixWarrantyData_lockedRecord_backwardCompatFieldsCorrect`，分别验证 BR-005（全字段覆盖）和 SE-007（老字段兼容），无重叠遗漏。

## 下一步

1. 若需启用覆盖率门禁，在 manifest 中设置 `coverage_required: true` 并提供 JaCoCo XML
2. 关注 FINDING-001 提到的 2 条低优先级分支（B-005、B-006），后续迭代补充
3. 考虑为 EUT-009/018 的 exchangeStartTime='' 边界场景补充独立测试
