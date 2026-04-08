---
name: dev-quality-gate
version: 3.0.0
description: "研发质量门禁：从需求到代码的全链路防漏管线，包含 6 个独立 Phase"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# 研发质量门禁

全链路防漏管线，6 个 Phase 各司其职。

## 入口

全流程编排入口：`dqg_starter.md`（在 AI IDE 中 `@dqg-starter` 触发）。

单个 Phase 也可独立触发，见下方路由规则。

## Phase 总览

| Phase | Skill | 职责 | 触发条件 |
|-------|-------|------|---------|
| A | `skills/requirement-structuring.md` | PRD → REQ/BR/SE + GAP + OPEN | 用户提供 PRD 或需求文档 |
| A.5 | `skills/tech-coverage-audit.md` | 技术方案 vs 需求覆盖度审计 | 已有 Phase A 产出 + 用户提供技术方案 |
| A.6 | `skills/tech-quality-review.md` | 技术方案自身质量评审 | 用户明确要求评审技术方案质量 |
| B | `skills/unit-test-generation.md` | 需求驱动单测设计与代码生成 | 用户明确进入单测环节 |
| C | `skills/unit-test-audit.md` | 单测覆盖审计 + 变异测试 | 用户要求审计单测质量 |
| D | `skills/code-review.md` | 预落地代码结构化评审 | 用户要求代码评审或合并前检查 |

## Phase 依赖关系

```
A ──→ A.5 ──→ A.6      (A.5 和 A.6 可并行)
│
├──→ B ──→ C
│
└──→ D
```

## 路由规则

1. 用户提供 PRD/需求文档 → `skills/requirement-structuring.md`
2. 用户提供技术方案 + 已有 Phase A → `skills/tech-coverage-audit.md`
3. 用户要求评审技术方案质量 → `skills/tech-quality-review.md`
4. 用户要求生成单测 → `skills/unit-test-generation.md`
5. 用户要求审计单测 → `skills/unit-test-audit.md`
6. 用户要求代码评审 → `skills/code-review.md`

无法判断时，询问用户当前处于哪个阶段。

## 工作流定义

| 工作流 | 文件 | 说明 |
|--------|------|------|
| 全流程 | `skills/workflow/dqg_flow_phases.md` | 每个 Phase 的完整生命周期、前置条件、产物校验、放行条件 |
| 多模块 | `skills/workflow/dqg_flow_multi_module.md` | 按模块拆分、并行执行、结果汇总、跨模块检查 |
| 迭代 | `skills/workflow/dqg_flow_iteration.md` | 问题修复后增量重跑、代码更新后部分重跑、收敛判断 |

## CLI 工具

```bash
dqg-run <project_id> status        # 状态看板
dqg-run <project_id> next          # 下一步
dqg-run <project_id> auto          # 全自动模式
dqg-run <project_id> log           # 执行记录
dqg-validate <project_id> --all    # 全量校验
dqg-metrics <project_id>           # 度量采集
```

## 技术栈基线

优先使用当前项目 `profile`（见 `output/<project>_phase*/_profile.json` 或状态看板中的 Profile）对应的基线与阈值：

- `java-ddd-tmf` → `references/java-ddd-tmf-baseline.md`
- `go-service` → `references/go-service-baseline.md`

若未提供 profile，再回退到 Java 默认基线。

## 度量与反馈

详见 `references/metrics-and-feedback.md`。
