# Q06 Java 单测覆盖审计报告 - smart-dispatch

## 审计结论

Q06 已逐条审计 Q05a 的 641 个 EUT。基于 Q05b 测试状态、强断言行、validator receipt 和 JaCoCo 增量覆盖率，本阶段结论为 `PASS_WITH_RISKS`。

重要边界：Q06 只确认 Java 可测范围。Q05a 中 37 个 Q01 核心项被标记为 non-testable，需要人工验收、集成测试或端到端测试补证。

## 增量覆盖率门禁

| 指标 | 结果 | 门槛 | 结论 |
|---|---:|---:|---|
| 增量行覆盖率 | 92.8% | >=80% | 通过 |
| 增量分支覆盖率 | 80.23% | >=80% | 通过 |

## 路径覆盖审计

| 路径 | COVERED / Q05a EUT | 结论 |
|---|---:|---|
| Boundary | 236/236 | 通过 |
| Concurrent | 3/3 | 通过 |
| Exception | 131/131 | 通过 |
| Happy Path | 271/271 | 通过 |

## 证据口径

- 每个 `COVERED` 审计项引用 Q05b `assertion_lines` 的真实源码行。
- 每个 `COVERED` 审计项绑定 `test_location`，指向断言行而不是方法首行。
- Q06 未新增 phantom EUT，审计 ID 全部来自 Q05a。

## Findings

1. Q01 有 37 个核心项不属于当前 Java 单测可覆盖范围，业务后果是不能用本轮 Java 单测替代前端、外部系统和流程事件验收。下一步应将这些项纳入人工验收、集成测试或端到端测试清单，并由对应 owner 补充证据。

## 下一步

- 对 non-testable 项补齐人工/集成验收证据。
- 若后续生产代码新增分支，优先补强 `EngineerSaturationCalculateFillStrategy` 等分支覆盖缓冲较低的类。
