# Q05a Reasoning Log

### Step 1: 范围判断

Q05a 以 Q01 的 6.6 工单相关修改为需求基线，并以四个本地仓库 origin/master...HEAD 的生产 Java diff 为代码基线。code_index 识别 100 个生产 Java diff 文件；proretail-claim 无生产 Java diff。

### Step 2: 索赔/预授权复核

复核 PRD 6.6 和 Q01 后，确认索赔/预授权涉及两类语义：一是预授权编辑和来源区分，对应 BR-004/SE-007；二是索赔/预授权展示小数数量，对应 BR-009/SE-008。展示链路有 car-mrs 和 soc-gw 的 numDecimal/partNumberDecimal diff，可设计 EUT；来源区分未在 Java diff 中出现字段或枚举，因此记录为外部澄清风险。

### Step 3: 变更 Java 实现类覆盖

- `car-mrs-domain/src/main/java/com/xiaomi/cnzone/car/mrs/domain/service/QuoteService.java`：由 EUT-001, EUT-002, EUT-003, EUT-004, EUT-007, EUT-014, EUT-015, EUT-017, EUT-023, EUT-024, EUT-039 覆盖。
- `car-mrs-domain/src/main/java/com/xiaomi/cnzone/car/mrs/domain/service/impl/MrRefundServiceImpl.java`：由 EUT-010, EUT-011, EUT-012, EUT-013, EUT-018, EUT-019, EUT-024, EUT-025, EUT-026, EUT-027 覆盖。
- `car-mrs-domain/src/main/java/com/xiaomi/cnzone/car/mrs/domain/service/MrItemSetService.java`：由 EUT-016, EUT-021, EUT-028, EUT-036, EUT-037, EUT-038 覆盖。
- `car-aftersale-action-domain/src/main/java/com/xiaomi/cnzone/caraftersaleaction/domain/action/core/factory/ActionAggregateFactory.java`：由 EUT-005, EUT-020, EUT-028, EUT-029, EUT-030, EUT-031, EUT-032 覆盖。
- `car-aftersale-action-domain/src/main/java/com/xiaomi/cnzone/caraftersaleaction/domain/ssu/service/SsuItemService.java`：由 EUT-020, EUT-022, EUT-028, EUT-033, EUT-039, EUT-040, EUT-042 覆盖。
- `car-mrs-app/src/main/java/com/xiaomi/cnzone/car/mrs/app/provider/impl/MrOrderDetailProviderImpl.java`：由 EUT-006, EUT-009, EUT-022, EUT-034, EUT-043 覆盖。
- `soc-gw-domain/src/main/java/com/xiaomi/cnzone/car/soc/gw/domain/service/impl/MrDetailPerfectServiceImpl.java`：由 EUT-008, EUT-009, EUT-022, EUT-024, EUT-034, EUT-035, EUT-044 覆盖。
- `car-mrs-domain/src/main/java/com/xiaomi/cnzone/car/mrs/domain/util/NumberUtil.java`：由 EUT-041, EUT-045, EUT-046 覆盖。

### Step 4: 排除说明

未纳入 included_diff_files 的文件均在 eut_matrix.json.target_modules.excluded_diff_files 逐项记录。多数为 DTO/BO/Entity 字段承载、converter/gateway 透传或配件计划相邻链路；Q05b 可结合覆盖率计划补充字段透传单测。
