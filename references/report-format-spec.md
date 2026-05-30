# 报告格式规范（Report Format Specification）

> 本文件定义 Qualix 所有 Phase 报告产物的格式规范。`report_quality_checks.py` 基于这些规范做确定性检测。
> 所有 SKILL.md 和模板文件引用本规范，修改格式要求时只改本文件。

## 0. PROFILE_CONTEXT 章节

每份报告必须包含 `## PROFILE_CONTEXT` 章节，声明本次评审/审计使用的 profile、baseline 和阈值。

### 格式

标题必须严格为 `## PROFILE_CONTEXT`，不加编号、不加后缀：

```markdown
## PROFILE_CONTEXT

| 项 | 值 |
|---|---|
| Profile | java-ddd-tmf |
| ... | ... |
```

错误示例（会触发 WARNING）：
- `## 1. PROFILE_CONTEXT — 技术栈基线` — 不要加编号和后缀
- `### PROFILE_CONTEXT` — 必须是二级标题 `##`

## 1. 来源标注（Source Annotation）

每条结论行（包含 COVERED/PARTIAL/MISSING/IMPLICIT/风险/问题/建议等判定性词汇的行）必须附带来源标注。

### 格式

```
[来源: 文件名:行号]
```

### 示例

```markdown
| SE-001 | 幂等控制 | PARTIAL | 幂等检查存在但无分布式锁 [来源: tech_design_quality_review.md:160] | HIGH |
```

```markdown
- ARCH-001: BPM 创建与本地状态写入顺序颠倒 [来源: MrOrderMainService.java:2283]
```

### 规则

- `文件名` 可以是报告文件名、代码文件名、或 PRD 文件名
- `行号` 是该文件中的行号；如果是代码方法，可用 `类名#方法名` 替代行号
- 表格中的来源标注放在映射证据/备注列中
- 非表格行的来源标注放在句末
- 引用上游 Phase 产物时格式: `[来源: phase_a_structured.json:REQ-001]`
- 引用代码时格式: `[来源: MrOrderMainService.java:2283]` 或 `[来源: MrOrderMainService#earlyDeliveryAuthStoreProcessCreate]`

## 2. 推理日志（Reasoning Log）

每个 Phase 必须输出 `_reasoning_log.md`，记录关键决策过程。

### Step 标记

推理日志必须使用 `### Step N` 格式标记执行步骤，与 SKILL.md 中的 Step 编号对应。

```markdown
### Step 0: 输入准备与范围确认

（推理内容...）

### Step 1: REQ 级覆盖扫描

（推理内容...）
```

### 最低要求

- 至少 3 个 `### Step N` 标记
- 至少 10 行实质内容（不含标题和分隔线）
- 必须引用 SKILL.md 的 Step 编号，证明按 skill 流程执行

### 内容要求

每个 Step 记录：
- 关键判定的推理过程（为什么标 COVERED/PARTIAL/MISSING）
- 与历史反例的对照验证
- 修正记录（Critique 后的变更）

## 3. 置信度标注（Confidence Tagging）

Q01/Q03/Q04 Phase 的报告中，每条覆盖判定/质量判定必须标注置信度。

### 格式

使用 `HIGH` / `MEDIUM` / `LOW`（大小写不敏感）。

### 适用范围

- REQ/SE 覆盖状态表：置信度列
- BR 覆盖状态表：置信度列（或在备注中标注）
- GAP/OPEN 闭环状态表：置信度列

## 4. 自检清单格式检查项

所有 SKILL.md 的自检清单（Step 6 或等效步骤）必须包含以下格式检查项：

```markdown
- [ ] 每条结论行有 `[来源: 文件名:行号]` 标注（参见 references/report-format-spec.md §1）
- [ ] 推理日志使用 `### Step N` 标记且 ≥ 3 个（参见 references/report-format-spec.md §2）
- [ ] 推理日志引用了 SKILL.md 的 Step 编号
```
