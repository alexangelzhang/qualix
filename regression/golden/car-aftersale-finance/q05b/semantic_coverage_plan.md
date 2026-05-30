# Q05b 一次性测试批次计划

## 结论

本计划把 Q01/Q05a 业务语义覆盖和 JaCoCo 增量覆盖率作为同等最高优先级。先按本计划写测试，再统一运行目标测试，避免多轮猜测式补测。

## 增量覆盖账本

| 指标 | 当前 covered/total | 当前覆盖率 | 阈值需要 | 带缓冲目标 | 硬缺口 | 缓冲缺口 |
|---|---:|---:|---:|---:|---:|---:|
| 增量行覆盖 | 1364/1490 | 91.54% | 1267 | 1270 | 0 | 0 |
| 增量分支覆盖 | 490/576 | 85.07% | 490 | 498 | 0 | 8 |

## 优先补测批次

| 优先级 | 类 | EUT | 路径分布 | missed branch | hard deficit | 说明 |
|---:|---|---|---|---:|---:|---|
| 1 | `FinanceExpenseExcelUtils` | EUT-019, EUT-020 | Exception:1, Happy Path:1 | 37 | 8 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 2 | `FinanceExpenseJobHandler` | EUT-001, EUT-002, EUT-003, EUT-006, EUT-021, EUT-029, EUT-031, EUT-032, EUT-033, EUT-034, EUT-035 | Boundary:2, Exception:1, Happy Path:8 | 22 | 5 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 3 | `FinanceExpenseProviderImpl` | EUT-028, EUT-030 | Exception:1, Happy Path:1 | 8 | 2 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 4 | `FinanceExpenseGatewayImpl` | EUT-025 | Boundary:1 | 3 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 5 | `RejectedToPendingStatusTransition` | EUT-015 | Happy Path:1 | 1 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 6 | `FinanceExpenseServiceImpl` | EUT-004, EUT-005, EUT-007, EUT-008, EUT-009, EUT-010, EUT-011, EUT-012, EUT-013, EUT-014, EUT-016, EUT-017, EUT-018, EUT-036 | Boundary:2, Exception:6, Happy Path:6 | 15 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 7 | `FinanceExpenseStatusEventFactory` | EUT-022, EUT-023 | Exception:1, Happy Path:1 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 8 | `FinanceExpenseDetailGatewayImpl` | EUT-026 | Boundary:1 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |

## 写测试规则

- REQ/BR/SE/EUT 语义覆盖和 JaCoCo 增量覆盖率同为最高优先级，任何一边不满足都不能把批次视为完成。
- 先生成本计划，再写 Java 测试；禁止写完测试后才第一次计算覆盖率缺口。
- 默认按类批量写测试，统一运行目标测试命令，避免每条 EUT 单独编译。
- 补测目标不只追平阈值，应至少满足 line_buffer_target 和 branch_buffer_target，避免刚过线后因小改动回退。
- 报告只展示增量目标覆盖率；全仓全量覆盖率不是本流程关注指标。
