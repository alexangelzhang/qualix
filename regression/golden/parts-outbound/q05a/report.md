# Q05a EUT 矩阵设计报告

## 结论

Q05a 已完成 parts-outbound 的 EUT 设计，当前矩阵共 46 条 EUT。PRD 6.6 中“索赔/预授权”没有遗漏：Q01 中对应 `BR-004`、`BR-009`、`SE-007`、`SE-008`；本阶段把 `BR-009/SE-008` 绑定到 `MrOrderDetailProviderImpl.queryPartRepair` 和 `MrDetailPerfectServiceImpl.detailMrPerfect` 的小数数量展示透传链路。`proretail-claim` 仓库本次 `origin/master...HEAD` 无生产 Java diff，因此不能生成索赔仓内的 diff EUT；预授权“工单入口 vs 质量技术入口来源区分”缺少字段/枚举证据，已作为不可自动后端验证风险记录。

## 机器产物索引

- `q05a/code_index.json`：100 个真实生产 Java diff 文件。
- `q05a/eut_matrix.json`：46 条 EUT，含 assertion_blueprint。
- `q05a/branch_inventory.json`：19 个目标方法分支清单。
- `q05a/business_outcomes.json`：66 个业务后果映射。

## 覆盖分布

- 编辑入口：报价单/工单同类校验、服务行动、服务项组套。
- 展示入口：报价单、工单详情、退款详情、索赔/预授权相关详情、车辆档案/端侧详情。
- 退款约束：可退数量上限、真小数仅全额退款、整数使用数量保持部分退款。
- 价格拦截：支持小数配件单价必须为整数元，服务行动候选列表过滤，后端提交拒绝。
- 范围隔离：押金二期、6.2 门店计划背景、预授权来源字段缺口。

## 索赔/预授权专项说明

- `BR-009/SE-008` 已设计 `EUT-009` 和 `EUT-022`，断言 `partNumberDecimal/numDecimal=1.50`，防止索赔/预授权相关展示链路把小数数量取整或截断。
- `BR-004/SE-007` 未生成后端自动 EUT，原因是本次 Java diff 没有预授权来源字段或流程分支，且 `proretail-claim` 无 Java diff。该项进入 `non_testable_items`，Q05b 前需要产品或研发补充来源字段/枚举。

## 不可测项

- `BR-003/SE-002`：前端加减按钮步长与默认值。
- `BR-004/SE-007`：预授权来源区分缺字段证据。
- `BR-006/BR-010/SE-009`：押金/提前交车延期二期。
- `REQ-005/SE-010`：6.2 门店计划背景，本次无预测/补货算法 diff。

## 下一步

进入 Q05b 时优先实现 T1 EUT：小数数量精度、unsupported decimal 拦截、非整数元价格拦截、退款全额约束，以及索赔/预授权展示小数数量的字段透传断言。
