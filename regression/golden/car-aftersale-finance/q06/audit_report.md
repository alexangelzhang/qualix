# Q06 Java 单测覆盖审计报告

## 结论

Q06 已审计 Q05a 的 36 条 EUT，全部能追溯到 Q01 的 REQ/BR/SE 和 Q05b 的 Java 测试方法。当前结论为 `PASS_WITH_WAIVED_RISK`。

JaCoCo 增量门禁已经达标：行覆盖率 91.54%（1364/1490），分支覆盖率 85.07%（490/576）。coverage 已达标；旧版本失效与 BI 只同步生效版本缺少实现证据，但用户已明确要求本轮忽略，作为已接受风险留痕，不再阻断。

本报告不展示全仓全量行/分支覆盖率，因为本流程只关心 Q05a 目标类的增量覆盖率。

## 术语说明

- `REQ-*` 是需求点，说明业务目标；`BR-*` 是业务规则，说明必须满足的分支规则；`SE-*` 是关键语义，说明必须能被验证的业务不变量。
- `EUT-*` 是 Executable Unit Test，即一条可落地到 Java 单测的业务场景，不等同于一个测试方法，但必须能追到测试方法。
- `T1/T2/T3` 是风险等级，不是技术优先级。T1 表示不测会影响状态、权限、审批、数据一致性、金额/Excel 或外部同步；T2 表示重要但爆炸半径较小。
- `B-*` 是代码路径编号，只用于追溯 Java 分支；报告中不能只展示 `B-*`，必须同时说明它对应的业务场景。
- `O-*` 是业务后果编号，只用于把代码路径绑定到可断言的业务结果；报告中不能只展示 `O-*`，必须说清楚不覆盖会造成什么后果。

## 增量门禁结果

| 指标 | covered/total | 当前值 | 阈值 | 结论 | 说明 |
|---|---:|---:|---:|---|---|
| 增量行覆盖率 | 1364/1490 | 91.54% | 85% | PASS | Q05a 目标类新增/相关代码整体已超过门槛。 |
| 增量分支覆盖率 | 490/576 | 85.07% | 85% | PASS | 刚过线，仍建议补缓冲分支。 |
| Q05b EUT 审计 | 36/36 | 100% | 100% | PASS | 每条 EUT 都能追到测试方法和断言行。 |
| PIT mutation | 未启用 | - | mutation_required=false | WARNING | 当前只有规则和解析能力，未提供 PIT XML/CSV。 |

## 为什么分支覆盖率比行覆盖率低

行覆盖只关心某一行是否执行过；分支覆盖会把 `if`、`||`、`&&`、三元表达式、`switch/catch` 等拆成多个真假路径。同一行代码执行过，不代表这行里的每个条件组合都被覆盖。因此分支覆盖率通常明显低于行覆盖率，特别是权限、Excel、状态机这种条件密集代码。

| 根因 | 在本项目中的表现 | 当前影响 |
|---|---|---|
| Excel 分流密集 | 单元格类型、公式缓存、日期、空值、字符串/数值比较都会拆分支。 | `FinanceExpenseExcelUtils` 分支覆盖低于行覆盖。 |
| 权限和通知组合多 | 总部/区域/门店、通知接收人、发送状态和幂等过滤都有短路组合。 | `JobHandler`、`ProviderImpl` 仍有缓冲分支可补。 |
| 状态机小分母敏感 | 某些类只有 2 个 branch，漏 1 个就显示 50%。 | `RejectedToPendingStatusTransition` 单类比例低，但聚合已达标。 |
| JaCoCo 计数更细 | `||`、`&&` 的每个真假组合都会计入 branch counter。 | 分支覆盖刚过 85%，后续改动容易回落。 |

## 目标类覆盖拆分

| 类 | 行覆盖率 | 分支覆盖率 | 未覆盖根因 |
|---|---:|---:|---|
| `FinanceExpenseExcelUtils` | 94.57% | 81.12% | Excel 单元格类型、公式缓存、数值/字符串比较、日期月份分支密集，分支覆盖天然比行覆盖低。 |
| `FinanceExpenseJobHandler` | 86.50% | 81.03% | 通知对象、发送状态、导出权限和异常短路组合多，仍有缓冲区分支可补。 |
| `FinanceExpenseProviderImpl` | 83.98% | 80.00% | 权限入口和参数转换有短路分支，小分母下分支缺口更显眼。 |
| `FinanceExpenseGatewayImpl` | 97.37% | 78.57% | 主表字段转换分支较少，少量边界未覆盖会明显拉低分支比例。 |
| `RejectedToPendingStatusTransition` | 94.23% | 50.00% | 只有 2 个 branch，漏 1 个就是 50%，属于小分母敏感。 |
| `FinanceExpenseServiceImpl` | 96.50% | 91.94% | 状态、附件、权限、提交一致性等核心分支已覆盖到位。 |
| `FinanceExpenseStatusEventFactory` | 100.00% | 100.00% | 已覆盖注册和未注册迁移。 |
| `FinanceExpenseDetailGatewayImpl` | 91.30% | 100.00% | 空列表保护已覆盖。 |
| `FinanceExpenseSnapshotGatewayImpl` | 100.00% | 100.00% | 快照保存路径已覆盖。 |
| `FinanceExpenseNoticeRecordGatewayImpl` | 100.00% | 100.00% | 通知记录保存路径已覆盖。 |

## Findings

| ID | 严重级别 | 具体风险 | 后果 | 建议 |
|---|---|---|---|---|
| FINDING-001 | PASS | JaCoCo exact target_class 口径增量行覆盖率 91.54%、增量分支覆盖率 85.07%，达到 85/85 门槛。 | 覆盖率门禁已达标，主要价值是防止后续目标类变化后误用旧覆盖率。 | 继续以 combined_jacoco.csv 作为 Q06 机器账本；Q05a target_class 变化后必须重新合并并校验。 |
| FINDING-002 | WARNING | 当前 manifest 中 mutation_required=false，未提供 PIT XML/CSV；本轮不阻断，但 T1 目标类仍建议补 mutation report。 | 没有 mutation 证据时，无法证明关键断言能杀死条件反转、返回值篡改等变异。 | 后续开启 mutation_required 并提供 PIT XML/CSV，用 validator 校验 KILLED/SURVIVED/NO_COVERAGE。 |
| FINDING-003 | WAIVED | 旧版本失效与 BI 只同步生效版本缺少实现证据，但用户已明确要求本轮忽略。 | 作为已接受风险留痕；本轮不再阻断 Q06。 | 后续若重新纳入范围，再补 BI/旧版本有效性证据和对应 EUT。 |

## 下一步

| 优先级 | 动作 | 为什么 |
|---|---|---|
| 已豁免 | 旧版本失效和 BI 生效版本同步本轮不再补证据。 | 用户已明确要求忽略；保留风险记录即可。 |
| P1 | 为 T1 目标类提供 PIT XML/CSV。 | 证明强断言能杀死关键变异，而不只是执行到代码。 |
| P1 | 按 `semantic_coverage_plan.json` 补缓冲分支。 | 分支覆盖率 85.07% 刚过线，后续小改动容易回落。 |
