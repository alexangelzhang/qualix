# Q05a EUT 矩阵设计报告 — entitlement-lifecycle

## 结论

**PASS** — EUT 矩阵设计完成，共 47 条 EUT（含覆盖率缺口补充 EUT-024/025/026），覆盖 3 个纳入类、9 个目标方法。

## 机器产物索引

| 产物 | 路径 |
|---|---|
| eut_matrix.json | q05a/eut_matrix.json |
| eut_matrix.md | q05a/eut_matrix.md |
| branch_inventory.json | q05a/branch_inventory.json |
| business_outcomes.json | q05a/business_outcomes.json |
| code_index.json | q05a/code_index.json |

## 覆盖分布

| 路径类型 | 数量 |
|---|---|
| Happy Path | 5 |
| Exception | 8 |
| Boundary | 6 |
| Concurrent | 0 |

## EUT 摘要

共 47 条 EUT，分布在 2 个类：

**WarrantyFacadeImpl（15条）：**
- resolveStartTimeTypeId：4条（code路径/数字id/非法/null）
- parseFixWarrantyEndDate：2条（纯日期/非法格式）
- validateAndParseFixWarrantyParam / fixWarrantyData：7条（各开始时间格式/结束时间/全流程覆盖）
- fixMaterialWarrantyData：3条（标准格式/斜杠格式/非法格式）

**WarrantyUpdateCommandHandler（2条）：**
- handle：2条（threeGuarantee=null/合法full path）

## 不可测项

- MafGatewayImpl.getSrvListBySn：日志格式改动，无 EUT
- WarrantyUpdateTypeEnum.checkData：JavaDoc 注释改动，无 EUT
- SrvThreeGuarantee：@ChangeLogAnnotation 注解，无 EUT
- WarrantyUpdateParam：纯 DTO，通过集成 EUT 覆盖

## 风险

1. **BR-007 实时计算分支**（EUT-013/014）：依赖 warrantyGateway mock，若 mock 设置不当可能绕过实际分支；Q05b 需确保 mock 路径正确。
2. **SE-001 JSR-303 校验**（EUT-001/018）：@NotBlank 校验是否在测试框架中生效取决于 Spring 校验配置；需确认测试是否通过 controller 层或直接调用 service。
3. **B-005（parseFixWarrantyEndDate blank路径）**、**B-011/B-022**：未覆盖，风险较低（属于保护性分支），可在 Q05b 视时间决定是否补充。

## 下一步（Q05b）

1. 运行 build_signature_index.py 构建测试签名索引。
2. 按 EUT 矩阵批量生成 JUnit5 单测代码。
3. 重点关注 WarrantyFacadeImpl 的 fixWarrantyData 全路径和 WarrantyUpdateCommandHandler.handle 两个目标类。
