# Qualix Skill 标准模板

> 所有 Phase skill 必须包含以下标准节（顺序可调整，但节不可缺失）。
> 新建 skill 时复制此模板，已有 skill 逐步对齐。

```markdown
---
name: <skill-name>
description: "<Phase X: 一句话描述>"
trigger: "<触发条件>"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - AskUserQuestion
---

# Phase X: <名称>

## 概述
一段话说明本 Phase 做什么、为什么需要、产出是什么。

## 触发条件
- 前置 Phase 已 approved
- 必要输入已收集

## 技术栈基线
按项目 profile 选择：
- `java-ddd-tmf` → `references/java-ddd-tmf-baseline.md`
- `go-service` → `references/go-service-baseline.md`

## 上下文加载原则（Token 优化）
1. 优先读取 `_upstream_context.md`
2. 图片语义已预解析到 `image_semantics.md`
3. Phase Q01 结构化产物是唯一的需求基线

## 执行流程

### Step 0: 输入确认与范围界定
### Step 1: ...
### Step N: 自检
### Step N+1: Judge/Critique
### Step N+2: 修正

## Anti-Rationalization（禁止偷懒）

| 常见借口 | 为什么不能接受 | 正确做法 |
|---------|--------------|---------|
| "..." | "..." | "..." |

## 红线规则（违反即 FAIL）
1. ...
2. ...

## 验证标准（Verification）

每条标准必须是可机器检查的，对应 finalize_checks 的某个 gate。

| 验证项 | 检查方式 | 阻断级别 |
|--------|---------|---------|
| 推理日志存在 | finalize_checks: _reasoning_log.md 存在且 > 100 字符 | BLOCKED |
| 产物数量不回退 | finalize_checks: 对比 _prev_counts.json | REGRESSION |
| Schema 校验通过 | schemas/phase_x.py 验证 structured JSON | BLOCKED |
| ... | ... | ... |

## 输出模板
### 报告结构
### 结构化 JSON

## 禁止事项
1. ...
2. ...
```
