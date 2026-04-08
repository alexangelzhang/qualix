---
name: unit-test-generation
description: "Phase B: TDD 需求驱动单测设计与代码生成"
trigger: "用户明确进入单测环节，要求从需求生成测试大纲和单测代码"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase B: 单测生成

从 Phase A 的结构化需求驱动单测设计，而非从代码反推。

## 前置依赖

- Phase A 产出（REQ/BR/SE）

## 技术栈基线

按项目 profile 选择：

- `java-ddd-tmf` → `references/java-ddd-tmf-baseline.md`
- `go-service` → `references/go-service-baseline.md`

## 上下文加载原则（Token 优化）

1. 优先读取 `_upstream_context.md`，不要回读原始 PRD 文档或 `plain_text.txt`。
2. 图片语义已预解析到 `image_semantics.md`，直接引用文本结论，不要重新读取图片文件。
3. Phase A 结构化产物是唯一的需求基线，不要回溯飞书原文。

## 执行流程

读取 `skills/modules/07_phase_b_ut_generator_zh.md` 并按其中定义的 3 个 Step 执行：

1. **契约模型与场景树解构**（EUT 建模）
2. **架构上下文代码脚手架生成**
3. **单测强断言约束代码实现**

## 产物

- EUT 矩阵（`eut_matrix.md`）
- 单测代码（基于 `templates/DomainStepTest.java.tmpl` 和 `templates/DomainAbilityTest.java.tmpl`）
- 建议以 `references/eut-matrix-template.md` 作为 EUT 报告骨架，并在报告头保留 `PROFILE_CONTEXT`

### Step 4: 自检（提交前强制检查）

完成 Step 1-3 后，逐项核对以下清单，全部通过方可继续：

- [ ] EUT 矩阵覆盖了所有 REQ/BR/SE
- [ ] 单测代码使用强断言（非仅执行流程）
- [ ] 异常路径有对应测试
- [ ] 每个测试用例标注了关联的 REQ/BR/SE ID
- [ ] 如果是重跑：新版是旧版超集
- [ ] 推理日志 `_reasoning_log.md` 已同步输出

### Step 5: Judge/Critique（提交前自我评审）

- **Judge**：对照 Phase A 产物验证 EUT 矩阵覆盖完整性
- **Critique**：假设有遗漏，重点检查异常路径、边界值、并发场景的测试覆盖
- 记录在报告末尾「自我评审记录」章节

### Step 6: 修正

根据 Step 4 自检和 Step 5 Judge/Critique 发现的问题，逐项修正后重新通过自检清单。

## 通过标准

- EUT 矩阵完整覆盖 Phase A 产出的所有 REQ/BR/SE
- 单测代码编译通过、断言有效
- 自检清单全部通过
- Judge/Critique 已执行且问题已修正
- 推理日志已输出

## 关键约束

- 测试从需求生成，不从代码反推
- 强断言：状态变更、副作用（Mockito.verify）、数据库写入
- 禁止"仅执行流程"的弱断言
- 每个 EUT 必须绑定 SE/REQ/BR

## 禁止事项

- 禁止跳过自检和 Judge/Critique 直接 finalize
- 禁止重跑时从零重写
