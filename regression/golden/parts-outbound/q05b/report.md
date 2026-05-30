# Q05b Java 单测代码生成报告

## 结论

`BLOCKED`。本阶段已完成 EUT-009 / EUT-022 的实现方案和目标测试补丁，但未能写入目标 Java 仓库，因此没有任何 EUT 可标记为 `passes:true`。

## 机器产物

- `q05b/code_status.json`：46 条 Q05a EUT 均已登记，当前 `done=0/46`。
- `q05b/semantic_coverage_plan.json`：记录 EUT-009 / EUT-022 的语义批次和覆盖率证据风险。
- `q05b/signature_index.json`：记录本次专项涉及的局部生产签名。
- `q05b/eut009_022_target_tests.patch`：目标 Java 仓库测试补丁。

## 索赔/预授权专项

- EUT-009：计划新增 `PartsOutboundMrOrderDetailProviderImplTest#queryPartRepair_claimPreauthKeepsPartNumberDecimal`，证明索赔/预授权相关配件维修详情不会把 `numDecimal=1.50` 取整或截断。
- EUT-022：计划新增 `PartsOutboundMrDetailPerfectServiceImplTest#detailMrPerfect_claimPreauthKeepsHourAndPartNumDecimal`，证明 SOC/App 详情对象里的工时和配件数量都保留 `1.50`。

## 构建与运行风险

目标 Java 仓库位于当前 workspace writable_roots 之外；两次申请写入 car-mrs/soc-gw 均被审批器内部错误拒绝（codex-auto-review is not a valid model ID），因此 Q05b 不能安全修改测试代码。

manifest 未提供 JaCoCo `coverage_report`，因此不能生成真实覆盖率 checkpoint；覆盖率必须在目标测试写入并运行 Maven/Jacoco 后补齐。

## 下一步

恢复目标仓库写权限后，应用 `q05b/eut009_022_target_tests.patch`，运行对应 Maven 测试，再由 `validators/run_test_batch.py` 生成 run_receipts，并继续实现其余 EUT。
