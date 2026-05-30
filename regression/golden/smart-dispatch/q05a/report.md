# Q05a EUT 矩阵设计报告

## 结论

Q05a 产物已完成初版设计，结论为 `PASS_READY_FOR_VALIDATION`。本阶段只设计 EUT，不生成或修改 Java 测试代码。矩阵共 641 条 EUT，覆盖 Q01 后端可测需求、真实生产 Java diff、branch_inventory 中的 happy/exception/boundary/concurrency/defense 分支。

## 机器产物索引

| 产物 | 说明 |
|---|---|
| `q05a/code_index.json` | 108 个真实生产 Java diff、101 个当前可扫描类。 |
| `q05a/eut_matrix.json` | EUT 矩阵、diff 分类、Q01 映射、non_testable 列表。 |
| `q05a/branch_inventory.json` | 方法级分支清单，复杂方法含覆盖策略和场景估算。 |
| `q05a/business_outcomes.json` | 每个分支的可断言业务后果。 |
| `q05a/eut_matrix.md` | 人可读 EUT 明细。 |
| `q05a/reasoning_log.md` | Q05a 推理和范围决策记录。 |

## 范围说明

- 默认 `origin/master...HEAD` 仅发现测试 diff，无法支撑生产代码 Q05a，因此本阶段使用 `origin/feature_init...HEAD` 作为生产实现 baseline。
- 真实生产 Java diff 共 108 个文件，其中纳入 EUT 设计 44 个文件，排除 64 个文件，scope conflict 0 个。
- 排除项主要为已删除旧实现、DTO/model/interface/mapper、纯协议/启动配置和 UI/外部系统规则。

## 覆盖分布

| 路径类型 | 数量 |
|---|---:|
| Happy Path | 271 |
| Exception | 131 |
| Boundary | 236 |
| Concurrent | 3 |

## 高风险复杂方法

| 类 | 方法 | 策略 |
|---|---|---|
| EngineerSaturationCalculateFillStrategy | doApply/calculateSaturation/resolveOrderLimit | 覆盖空候选、缺配置、单/多品类历史遗留、区域瀑布、旺季、appointDay 和并发查询。 |
| EngineerProbabilityRankStrategy | fillDisplayMatchProbability | 覆盖单候选、多候选、0 饱和度平滑、100% 饱和度归零、并列排序和 null 指标。 |
| WorkloadConfigServiceImpl | importFromExcel/validateImportRow/matchConfig/enrichJsonWithNames | 覆盖导入行校验、重复键、批量 upsert、失败报告、日志名称富化、区域优先级和旺季匹配。 |

## 不可测项

non_testable 共 37 项，集中在 CDP VIP 识别、PC/App UI 展示、菜单、工单工作流释放节点、地图慧同步和容量合同指标。每项已在 `eut_matrix.json.non_testable_items` 中给出证据。

## 下一步

Q05b 必须先基于本矩阵运行 `coverage_plan.py`、`build_signature_index.py`，再按 branch/outcome/EUT 写强断言 Java 单测；禁止用 assertNotNull 或类名断言支撑 COVERED。
