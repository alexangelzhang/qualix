# Q05b 一次性测试批次计划

## 结论

本计划把 Q01/Q05a 业务语义覆盖和 JaCoCo 增量覆盖率作为同等最高优先级。先按本计划写测试，再统一运行目标测试，避免多轮猜测式补测。

## 增量覆盖账本

| 指标 | 当前 covered/total | 当前覆盖率 | 阈值需要 | 带缓冲目标 | 硬缺口 | 缓冲缺口 |
|---|---:|---:|---:|---:|---:|---:|
| 增量行覆盖 | 6479/6848 | 94.61% | 5821 | 5824 | 0 | 0 |
| 增量分支覆盖 | 2969/3414 | 86.97% | 2902 | 2910 | 0 | 0 |

## 优先补测批次

| 优先级 | 类 | EUT | 路径分布 | missed branch | hard deficit | 说明 |
|---:|---|---|---|---:|---:|---|
| 1 | `FaultListFacadeImpl` | EUT-026, EUT-031 | Exception:1, Happy Path:1 | 153 | 40 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 2 | `FaultReasonFacadeImpl` | EUT-001, EUT-002, EUT-003, EUT-004, EUT-005, EUT-006, EUT-007, EUT-008, EUT-009, EUT-010, EUT-020, EUT-021, EUT-037, EUT-038, EUT-039, EUT-043, EUT-044, EUT-046 | Boundary:3, Concurrent:1, Exception:10, Happy Path:4 | 6 | 5 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 3 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 2 | 2 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 4 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 119 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 5 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 1 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 6 | `FaultReasonFacadeImpl` | EUT-001, EUT-002, EUT-003, EUT-004, EUT-005, EUT-006, EUT-007, EUT-008, EUT-009, EUT-010, EUT-020, EUT-021, EUT-037, EUT-038, EUT-039, EUT-043, EUT-044, EUT-046 | Boundary:3, Concurrent:1, Exception:10, Happy Path:4 | 45 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 7 | `FaultServiceImpl` | EUT-024, EUT-025, EUT-033, EUT-050, EUT-053 | Boundary:4, Exception:1 | 92 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 8 | `FaultEditServiceImpl` | EUT-027 | Happy Path:1 | 1 | 1 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 9 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 10 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 11 | `FaultFacadeImpl` | EUT-029, EUT-030, EUT-032, EUT-040, EUT-041, EUT-042, EUT-045, EUT-047 | Boundary:1, Exception:4, Happy Path:3 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 12 | `FaultEditServiceImpl` | EUT-027 | Happy Path:1 | 24 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 13 | `FaultReasonServiceImpl` | EUT-011, EUT-012, EUT-013, EUT-014, EUT-015, EUT-034, EUT-048, EUT-051, EUT-054 | Boundary:5, Exception:1, Happy Path:3 | 0 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |
| 14 | `FaultBpmApprovalServiceImpl` | EUT-018, EUT-019, EUT-052 | Boundary:1, Exception:1, Happy Path:1 | 2 | 0 | 同时存在语义 EUT 与 JaCoCo 分支/行覆盖缺口或缓冲不足 |

## 写测试规则

- REQ/BR/SE/EUT 语义覆盖和 JaCoCo 增量覆盖率同为最高优先级，任何一边不满足都不能把批次视为完成。
- 先生成本计划，再写 Java 测试；禁止写完测试后才第一次计算覆盖率缺口。
- 默认按类批量写测试，统一运行目标测试命令，避免每条 EUT 单独编译。
- 补测目标不只追平阈值，应至少满足 line_buffer_target 和 branch_buffer_target，避免刚过线后因小改动回退。
- 报告只展示增量目标覆盖率；全仓全量覆盖率不是本流程关注指标。
