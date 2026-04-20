# Trace-Reflect 报告 — DQG 项目级 Skill

*基于 skill-audit-report-2026-04-16.md 审计发现的 Reflective Mutation*

## Session 概况

- 审计对象: `dev-quality-gate/skills/` 下 9 个 skill
- 审计发现: 17 个引用缺失、1 处重复表格、2 个 skill 指令不足
- 涉及 skill: requirement-structuring, tech-design-generation, tech-coverage-audit, tech-quality-review, unit-test-generation, unit-test-audit, code-review, quality-judge, knowledge-base-builder

## 轨迹分类

### T± 0.5 — 引用缺失是最大质量风险

审计发现 17 个引用文件缺失，其中 code-review (Phase D) 的 7 个 modules 文件全部缺失。这意味着 Phase D 的模块化执行流程在实际运行时会断裂——skill 指令说"先读取 `modules/00_policy_constraints_zh.md`"，但文件不存在。

### T+ 1.0 — 核心 Phase skill 质量高

requirement-structuring、unit-test-audit、tech-design-generation 三个 skill 结构完整、指令具体、Anti-Rationalization 表格有效。这是成功模式。

### T± 0.5 — 共享资源重复引用无统一管理

`java-ddd-tmf-baseline.md` 和 `go-service-baseline.md` 在 4 个 skill 中被引用，但只在部分 skill 的 references/ 下存在。没有共享引用机制。

---

## 失败轨迹分析

### 失败诊断 1: code-review 模块化执行完全失效

**第一轮：现象**
- SKILL.md 第 160-167 行定义了 7 个模块化执行步骤，每步引用一个 `modules/*.md` 文件
- 7 个文件全部不存在

**第二轮：根因**
- 归因: **环境/上下文问题** — 大概率是某次重构（从旧的扁平结构迁移到 `SKILL.md + references/` 结构时）遗漏了 modules 目录的迁移
- code-review 是所有 Phase skill 中最复杂的（305 行），模块化拆分是合理设计，但迁移不完整
- SKILL.md body 中已经包含了完整的评审维度和 checklist（第 96-141 行），modules 文件可能是更细粒度的执行指令

**第三轮：修复方向**
- 选项 A: 补齐 7 个 modules 文件（需要从旧版本或 git history 恢复）
- 选项 B: 如果 modules 内容已经内联到 SKILL.md body 中，删除 modules 引用，改为直接执行
- 需要先确认 git history 中是否存在过这些文件

### 失败诊断 2: baseline 文件散落无统一管理

**第一轮：现象**
- `java-ddd-tmf-baseline.md` 在 requirement-structuring、tech-quality-review 中缺失，但在 unit-test-audit、code-review 中存在
- 同一个文件在不同 skill 的 references/ 下各存一份（或不存）

**第二轮：根因**
- 归因: **Skill 定义缺陷** — 没有共享引用机制，每个 skill 独立维护 references/，导致同一文件需要 N 份副本
- 新增 skill 时容易忘记复制 baseline 文件

**第三轮：修复建议**
- 建立 `skills/shared/` 目录存放跨 Phase 共享资源
- 各 skill 引用改为相对路径 `../shared/java-ddd-tmf-baseline.md`

### 失败诊断 3: unit-test-generation Step 1.4 重复表格

**第一轮：现象**
- line 180-186 是设计矩阵自检表格（正确版本，有表头）
- line 188-194 是同一表格的重复（缺表头行，且多了 `达标情况` 列）
- 紧接着 line 195 又重复了一遍"设计矩阵是 Phase C 审计的基准"这句话

**第二轮：根因**
- 归因: **环境/上下文问题** — 大概率是某次编辑时复制粘贴残留，未清理

---

## Reflective Mutation

### Mutation 1: 修复 unit-test-generation 重复表格

**诊断摘要**: Step 1.4 有重复表格和重复说明文字，缺表头行会导致 LLM 解析混乱

```diff
--- a/skills/unit-test-generation/SKILL.md
+++ b/skills/unit-test-generation/SKILL.md
@@ -185,12 +185,1 @@
 | 路径均衡 | Happy ≥ 40% / Exception ≥ 30% / Boundary+防御 ≥ 30% | WARNING |
 
-> **设计矩阵是 Phase C 审计的基准**——Phase C 对照设计矩阵检查"设计了但没实现"和"实现了但没设计"。
-|------|------|------|
-| REQ 覆盖率 | 100%（每条 REQ 至少 1 个用例） | X/Y |
-| BR 覆盖率 | ≥ 80%（含校验/限制的 BR 100%） | X/Y |
-| SE 覆盖率 | 100%（有效 SE） | X/Y |
-| 变更文件覆盖率 | P0 100% / P1 ≥ 80% / P2 ≥ 50% | X/Y |
-| 路径均衡 | Happy ≥ 40% / Exception ≥ 30% / Boundary ≥ 15% / 防御 ≥ 15% | X/X/X/X |
-
-> **设计矩阵是 Phase C 审计的基准**——Phase C 审计时对照设计矩阵检查"设计了但没实现"和"实现了但没设计"。
+> **设计矩阵是 Phase C 审计的基准**——Phase C 对照设计矩阵检查"设计了但没实现"和"实现了但没设计"。
```

- **修改理由**: line 186-195 是 line 180-186 的残留副本，表头缺失且列定义不一致（多了 `X/Y` 占位符）
- **预期效果**: 消除重复，保留唯一正确版本
- **风险评估**: 低 — 纯删除冗余内容

### Mutation 2: quality-judge 增强独立可执行性

**诊断摘要**: 当前仅 41 行，完全依赖运行时生成的 `_judge_prompt.md`，缺乏独立可执行性

```diff
--- a/skills/quality-judge.md
+++ b/skills/quality-judge.md
@@ -28,6 +28,30 @@
 4. 对照原始输入逐条验证，不能只看输出自洽性
 
 ## 评审流程
 
 1. 读取 `_judge_prompt.md` 获取评审维度和评分标准
 2. 读取 Phase 输出文件（report + structured JSON）
 3. 读取上游产物（PRD/技术方案/代码）作为 ground truth
 4. 逐维度评分，列出具体扣分项
 5. 输出结构化 JSON 到 `_judge_result.json`
+
+## 通用评审维度（当 _judge_prompt.md 不存在时使用）
+
+| 维度 | 权重 | 评分标准 |
+|------|------|---------|
+| 完整性 | 30% | 上游产物的每条 REQ/BR/SE 是否在输出中有对应处理 |
+| 准确性 | 30% | 每条结论是否有原文证据支撑，是否存在幻觉 |
+| 结构规范 | 20% | 是否包含 skill 定义的所有必须章节，格式是否一致 |
+| 自检质量 | 20% | Judge/Critique 是否执行，发现的问题是否已修正 |
+
+## 输出 Schema
+
+```json
+{
+  "phase": "A/A.5/A.6/B/C/D",
+  "score": {
+    "completeness": 0-5,
+    "accuracy": 0-5,
+    "structure": 0-5,
+    "self_check": 0-5
+  },
+  "total": 0-20,
+  "verdict": "PASS / PASS_WITH_RISKS / FAIL",
+  "deductions": [
+    { "dimension": "...", "issue": "...", "evidence": "...", "points": -N }
+  ],
+  "false_negatives": ["漏掉的 REQ/BR/SE ID 列表"],
+  "false_positives": ["错误标记的 ID 列表"]
+}
+```
```

- **修改理由**: 当 `_judge_prompt.md` 不存在或生成异常时，skill 无法独立执行
- **预期效果**: 提供 fallback 评审维度和输出 schema，确保任何情况下可执行
- **风险评估**: 低 — 只增加 fallback 内容，有 `_judge_prompt.md` 时仍优先使用

### Mutation 3: 建立共享引用目录

**诊断摘要**: baseline 文件在 4 个 skill 中被引用，散落在各自 references/ 下，部分缺失

```diff
--- /dev/null
+++ b/skills/shared/README.md
@@ -0,0 +1,5 @@
+# 共享引用
+
+跨 Phase skill 共享的 reference 文件。各 skill 通过 `../shared/` 相对路径引用。
+
+- `java-ddd-tmf-baseline.md` — Java DDD+TMF 技术栈基线（Phase A/A.5/A.6/B/C/D 共用）
+- `go-service-baseline.md` — Go 服务技术栈基线
```

各 skill 的引用路径统一修改（以 requirement-structuring 为例）：

```diff
--- a/skills/requirement-structuring/SKILL.md
+++ b/skills/requirement-structuring/SKILL.md
@@ -56,8 +56,8 @@
 优先读取当前项目的 profile 上下文：
-- `java-ddd-tmf` 使用 `references/java-ddd-tmf-baseline.md`
-- `go-service` 使用 `references/go-service-baseline.md`
++ `java-ddd-tmf` 使用 `../shared/java-ddd-tmf-baseline.md`
++ `go-service` 使用 `../shared/go-service-baseline.md`
```

同样修改: tech-quality-review, unit-test-audit, unit-test-generation, code-review

- **修改理由**: 同一文件在 4 个 skill 中被引用，当前散落在各自 references/ 下（部分缺失），维护成本高
- **预期效果**: 单一来源，新增 skill 不需要复制 baseline 文件
- **风险评估**: 中 — 需要同时修改 4+ 个 skill 的引用路径，且 context_loader 如果有路径硬编码需要同步更新

---

## 改进建议汇总（按优先级）

| 优先级 | 建议 | 关联 Mutation | 复杂度 |
|--------|------|--------------|--------|
| P0 | 确认 code-review modules 文件来源（查 git history），恢复或删除引用 | — | 中 |
| P0 | 修复 unit-test-generation 重复表格 | Mutation 1 | 低 |
| P1 | 建立 shared/ 共享引用目录 + 迁移 baseline 文件 | Mutation 3 | 中 |
| P1 | 补齐缺失的 template 文件（report-template、coverage-template、quality-template、eut-matrix-template） | — | 高 |
| P2 | 增强 quality-judge 独立可执行性 | Mutation 2 | 低 |

---

*方法: Trace2Skill (轨迹分类) + Skill-Insight (归因分析) + GEPA (Reflective Mutation)*
*审计报告来源: skill-audit-report-2026-04-16.md*
