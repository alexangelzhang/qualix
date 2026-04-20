# Skill Audit Report — 2026-04-16

## 概览

- 扫描范围: `dev-quality-gate/skills/`
- 实质 skill: 9 个（7 个 Phase skill + quality-judge + knowledge-base-builder）
- Facade 文件: 7 个（旧路径兼容重定向）
- 辅助文件: 2 个（system-rules.md, SKILL_TEMPLATE.md）

| 层 | 🔴 | 🟡 | 🟢 |
|---|---|---|---|
| Description 压缩 | 0 | 0 | 9 |
| 质量评估 | 0 | 0 | 9 |
| 安全问题 | 0 Critical | 0 real Warning | 9 false positive |

---

## 第一层：Description 压缩

所有项目级 skill 的 description 均在 3-12 words，全部 🟢。DQG skill 的 description 写法是全局 skill 的标杆——简洁、有 trigger 条件、有 Phase 编号。无需压缩。

| Skill | Words | 状态 |
|-------|-------|------|
| requirement-structuring (A) | 12 | 🟢 |
| tech-coverage-audit (A.5) | 9 | 🟢 |
| tech-quality-review (A.6) | 6 | 🟢 |
| tech-design-generation (A.3) | 5 | 🟢 |
| code-review (D) | 5 | 🟢 |
| unit-test-audit (C) | 6 | 🟢 |
| unit-test-generation (B) | 4 | 🟢 |
| quality-judge | 6 | 🟢 |
| knowledge-base-builder | 3 | 🟢 |

---

## 第二层：6 维质量评估

### 评分总览

| Skill | 职责 | 结构 | 指令 | 一致性 | 风险 | 引用 | 总分 |
|-------|------|------|------|--------|------|------|------|
| requirement-structuring (A) | 5 | 5 | 5 | 5 | 5 | 3 | 28 🟢 |
| tech-design-generation (A.3) | 5 | 5 | 5 | 5 | 5 | 5 | 30 🟢 |
| tech-coverage-audit (A.5) | 5 | 5 | 5 | 5 | 5 | 4 | 29 🟢 |
| tech-quality-review (A.6) | 5 | 5 | 5 | 5 | 5 | 3 | 28 🟢 |
| unit-test-generation (B) | 5 | 4 | 5 | 5 | 5 | 4 | 28 🟢 |
| unit-test-audit (C) | 5 | 5 | 5 | 5 | 5 | 5 | 30 🟢 |
| code-review (D) | 5 | 5 | 5 | 5 | 5 | 1 | 26 🟢 |
| quality-judge | 5 | 4 | 3 | 4 | 5 | 5 | 26 🟢 |
| knowledge-base-builder | 5 | 4 | 3 | 5 | 5 | 4 | 26 🟢 |

### 评分维度说明

| 维度 | 评估标准 |
|------|---------|
| 职责明确性 | skill 是否只做一件事？边界是否清晰？ |
| 结构规范性 | frontmatter 完整？步骤有序？格式一致？ |
| 指令适配性 | 指令是否足够具体让 LLM 正确执行？ |
| 内容一致性 | description 声明的能力和 body 实际内容是否匹配？ |
| 风险可控性 | 是否有危险操作？是否有用户确认环节？ |
| 脚本/引用质量 | 引用的脚本/reference 是否存在且有效？ |

### 语义-行为一致性（SkillProbe）

所有 Phase skill 的 description 与 body 高度一致，无 Over-declaration 或 Under-declaration。

唯一的 Mixed 情况：`quality-judge` description 声明"输出 precision/recall"，但 body 中未详细说明计算方式，依赖动态生成的 `_judge_prompt.md`。

### 扣分详情

#### 引用质量 — 17 个引用文件缺失

| Skill | 缺失引用 | 影响 |
|-------|---------|------|
| requirement-structuring | `references/report-template.md`, `image-semantics-mapping-template.md`, `java-ddd-tmf-baseline.md`, `go-service-baseline.md` | 执行时无法加载输出模板和技术栈基线 |
| tech-coverage-audit | `references/tech-design-coverage-template.md` | 无覆盖度报告模板 |
| tech-quality-review | `references/tech-design-quality-template.md`, `java-ddd-tmf-baseline.md`, `go-service-baseline.md` | 无质量评审模板和基线 |
| unit-test-generation | `references/eut-matrix-template.md` | 无 EUT 矩阵模板 |
| code-review | `references/code-review-template.md` + 全部 7 个 `modules/*.md` | Phase D 的模块化执行完全失效 |

缺失引用完整列表：

```
❌ requirement-structuring/SKILL.md → references/report-template.md
❌ requirement-structuring/SKILL.md → references/image-semantics-mapping-template.md
❌ requirement-structuring/SKILL.md → references/java-ddd-tmf-baseline.md
❌ requirement-structuring/SKILL.md → references/go-service-baseline.md
❌ tech-coverage-audit/SKILL.md → references/tech-design-coverage-template.md
❌ tech-quality-review/SKILL.md → references/tech-design-quality-template.md
❌ tech-quality-review/SKILL.md → references/java-ddd-tmf-baseline.md
❌ tech-quality-review/SKILL.md → references/go-service-baseline.md
❌ unit-test-generation/SKILL.md → references/eut-matrix-template.md
❌ code-review/SKILL.md → references/code-review-template.md
❌ code-review/SKILL.md → modules/00_policy_constraints_zh.md
❌ code-review/SKILL.md → modules/01_base_branch_context_zh.md
❌ code-review/SKILL.md → modules/02_intent_scope_check_zh.md
❌ code-review/SKILL.md → modules/03_java_review_checklist_zh.md
❌ code-review/SKILL.md → modules/04_diff_and_context_scan_zh.md
❌ code-review/SKILL.md → modules/05_confirm_first_fix_flow_zh.md
❌ code-review/SKILL.md → modules/06_evidence_validation_report_zh.md
```

已存在的引用（17 个，全部 OK）：

```
✅ requirement-structuring → references/structuring-rules.md
✅ requirement-structuring → references/output-templates.md
✅ tech-design-generation → references/design-templates.md
✅ tech-design-generation → references/implementation-slicing.md
✅ tech-coverage-audit → references/design-generation.md
✅ tech-quality-review → references/exception-catalog.md
✅ unit-test-generation → references/test-generation-rules.md
✅ unit-test-audit → references/audit-rules.md
✅ unit-test-audit → references/mutation-testing.md
✅ unit-test-audit → references/report-template.md
✅ code-review → references/code-quality-checklist.md
✅ code-review → references/security-checklist.md
✅ code-review → references/solid-checklist.md
✅ code-review → references/fund-safety-identification.md
✅ code-review → references/fund-safety-java-patterns.md
✅ code-review → references/fund-safety-governance.md
✅ code-review → references/review-checklist.md
```

#### 结构规范性扣分

- `unit-test-generation` Step 1.4 有重复表格（line 186-194 与 line 180-186 内容重复，第二个表格缺表头行）

#### 指令适配性扣分

- `quality-judge` 仅 41 行，过于简略，评审维度和评分标准完全依赖运行时生成的 `_judge_prompt.md`，skill 本身缺乏独立可执行性
- `knowledge-base-builder` Step 2-6 的 bash 代码块是伪代码注释，不是可执行脚本

---

## 第三层：安全扫描

0 个真实安全问题。

9 个 Warning 全部是误报——正则匹配到"Token 优化"章节标题中的 `TOKEN` 关键词。

所有 Phase skill 都有明确的安全设计：
- confirm-first 机制（产物修改须经人工确认）
- 禁止自动 commit/push
- 禁止调用外部平台 API（Phase D）
- 禁止手动编辑状态文件

---

## Top 5 改进建议

### 1. 补齐 17 个缺失引用文件（P0）

尤其是 `code-review/modules/` 下的 7 个模块文件，Phase D 的模块化执行流程完全依赖这些文件。建议检查是否在某次重构中遗漏了迁移，或者路径映射需要更新。

### 2. 修复 unit-test-generation Step 1.4 的重复表格（P1）

line 186-194 是 line 180-186 的重复，且缺少表头行 `| 指标 | 要求 | 达标情况 |`，会导致 LLM 解析混乱。

### 3. 统一 baseline 引用路径（P1）

`java-ddd-tmf-baseline.md` 和 `go-service-baseline.md` 在多个 skill 中被引用，但只在部分 skill 的 references/ 下存在。建议放到共享位置（如 `skills/shared/references/`）并统一引用路径，避免每个 skill 都要维护一份副本。

### 4. 增强 quality-judge skill 的独立可执行性（P2）

当前 41 行过于简略，建议将评审维度、评分标准、输出 schema 直接写入 skill，减少对运行时动态生成的依赖。

### 5. knowledge-base-builder 的 Step 脚本实化（P2）

将伪代码注释替换为可执行的 grep/find 命令模板，或明确标注"由 Agent 自行决定扫描策略"。

---

*审计方法: SkillReducer (description 压缩) + Skill-Insight (6 维质量评估) + SkillProbe (安全扫描 + 语义一致性)*
