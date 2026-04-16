---
name: dqg-starter
description: "研发质量门禁 Pipeline 入口 — 触发后自动启动流程引导"
---

# DQG Flow - 交互式引导入口

## 自动执行指令

**当用户通过 `@dqg-starter` 引用本文件时，AI 必须：**

1. **声明模式**：在首次响应开头输出 `🔄 [DQG Flow 模式已激活]`
2. **项目检测**：询问用户项目 ID（如果未指定）
3. **一键启动**：执行 `dqg-run --base-dir <project_root> <project_id> startup`
4. **菜单展示**：解析 JSON 输出，渲染菜单给用户
5. **等待选择**：提示用户选择要执行的 Phase

> **执行要求**：
> - 直接进入流程，无需询问用户意图
> - 必须调用脚本获取状态，禁止手动构造菜单
> - 跳过阻断点 = BLOCKER 级错误

---

## Phase DAG（执行顺序）

```
A（需求结构化）
├── A.3（技术方案生成，可选）── A.6（技术方案质量评审）── A.5（技术方案覆盖度审计）── D（代码评审）
└── B（单测生成）──── C（单测覆盖审计）
```

- A.3 可 skip（已有技术方案时）
- A.6 先于 A.5（先评审质量，再审覆盖度）
- B/C 与 A.3/A.6/A.5 独立并行

### 每个 Phase 的自动化能力

| Phase | execute 自动注入 | finalize 硬性 Gate | 特有能力 |
|-------|-----------------|-------------------|---------|
| A | phase_contract + bug cases + 跨项目知识 | 推理日志 + 防回退 + auto_checks | 假设前置(Step 0.5) + 边界约定 + 范围外发现 |
| A.3 | phase_contract | 推理日志 + 防回退 + auto_checks | 实施切片指导(XS/S/M/L/XL) + 范围外发现 |
| A.6 | phase_contract | 推理日志 + 防回退 + auto_checks | 12类异常矩阵 + Failure Mode 分析 |
| A.5 | phase_contract + coverage_matrix | 推理日志 + 防回退 + auto_checks | REQ/BR/SE→技术设计映射矩阵 |
| B | phase_contract + data_patterns + se_code_mapping | 推理日志 + 防回退 + **编译验证** + auto_checks | Mock优先级 + DAMP + 范围外发现 |
| C | phase_contract + weak_assert + business_mutations + blast_radius + data_patterns + se_code_mapping + diff_context | 推理日志 + 防回退 + **覆盖率≥80%** + auto_checks | CONFLICT状态 + 变异测试 + 弱断言tree-sitter |
| D | phase_contract + diff_context + se_code_mapping | 推理日志 + 防回退 + auto_checks | 变更大小门禁 + 评论标签 + 依赖审查 + feature flag |

### 所有 Phase 统一的 finalize handler（自动触发，按 order 排序）

1. 性能指标收集(10) → 2. 规则质量追踪(20) → 3. 结构化事实索引(30) → 4. Golden Sample 对比(40) → 5. 规则执行率(50) → 6. Profile 上下文检查(60) → 7. Verification Bundle 统一验证包(65) → 8. 评审链 prompt 生成(70) → 9. 进度文件(80) → 10. Skill Factory + Evolution(90) → 11. DeepEval 评分校准(95) → 12. Eval 质量基线(98)

### Adaptive Loop 质量保障（运行时）

| 组件 | 触发时机 | 作用 |
|------|---------|------|
| RationalizationGuard | Judge 输出后 | 两层放水检测（关键词+LLM），拦截后重审 |
| JudgeRunner | 每次 Judge 调用 | 统一执行入口，structured output，canonical schema |
| judge_health_check | 全部迭代耗尽后 | 区分 SEMANTIC_FAIL vs INFRA_FAILURE |
| SkillReflector | SEMANTIC_FAIL 时 | Reflect→Persist→Cluster→Write 自动进化 skill |
| check_report_structure | finalize/replay | 按 required_report_sections 校验报告章节 |

### 跨 Phase 数据流

- Phase A 的 SE 列表 → 驱动 dynamic_rubric(动态Judge维度) + business_mutations(变异规则) + coverage_matrix(覆盖度矩阵) + phase_contract(验证目标)
- Phase C 的 bug cases → 驱动 data_patterns(故障数据模式) → 注入 Phase B/C
- 所有 Phase 的 bug cases → 驱动 skill_factory(规则建议) + lesson_inference(自动推断lesson) + skill_evolution(进化 diff)
- 跨项目 knowledge_network → 自动注入 _cross_project_insights.md
- 下游 Phase 发现需求问题 → UPSTREAM_UPDATE_NEEDED 标记 → 触发 Phase A 重开
- Phase Contract → Judge 按 contract 逐条打分（而非自由文本评审）
- Verification Bundle → Judge 先看确定性证据再做语义判断
- Eval Baseline → 每次 finalize 自动对比历史基线，退化超 5% 触发 WARNING

### Reasoning Sandwich（推理预算分配）

每个 Phase 有 `reasoning_profile`（planning/execution/verification 三阶段）：
- high = 100% context budget（用于 planning 和 verification 阶段）
- standard = 60% context budget（用于格式化输出阶段，为推理留更多空间）

### 错误恢复

当 Phase 执行出错时，遵循 `skills/workflow/error-recovery-protocol.md`：
- Stop-the-Line：立即停止，保留证据
- Triage 五步法：Reproduce → Localize → Reduce → Fix → Guard
- 不可复现 bug 四分支决策树：时序/环境/状态/随机

---

## 核心规则（违反即 BLOCKER）

| # | 规则 | 约束 |
|:-:|:---|:---|
| 1 | **脚本驱动状态** | 状态管理必须通过 `dqg-run` 执行，禁止手动构造 |
| 2 | **逐步交互** | 多步输入时，每次只展示一个问题，等待用户回复后再展示下一个。禁止一次性列出所有问题 |
| 3 | **等待用户输入** | 菜单展示、输入收集、确认点必须等待用户输入，禁止假设或自动继续 |
| 4 | **Skill 驱动执行** | Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥 |
| 5 | **收尾四步** | 产出检测 → 校验(finalize) → 人工确认(approve) → 刷新菜单 |
| 6 | **结构化产物** | 每个 Phase 同时产出 markdown 报告 + JSON 结构化文件 |
| 7 | **推理日志必须交付** | 每个 Phase 必须输出 `_reasoning_log.md`，记录每步决策过程，finalize 时硬性校验 |
| 8 | **Judge/Critique 在 finalize 前** | 禁止跳过自检和 Judge/Critique 直接 finalize |
| 9 | **控制权交还** | Phase 产出后进入 finalize 流程，不自动建议下一步 |
| 10 | **反幻觉公约** | 遵守 `skills/system-rules.md`，每条结论标注来源和置信度 |
| 11 | **工作流遵循** | 遵守 `skills/workflow/` 下的工作流定义，多模块按模块分别执行，迭代按增量重跑规则 |

> **工作流参考**：
> - 全流程定义：`skills/workflow/dqg_flow_phases.md`
> - 多模块工作流：`skills/workflow/dqg_flow_multi_module.md`
> - 迭代工作流：`skills/workflow/dqg_flow_iteration.md`

---

## 执行流程

### 步骤一：启动与菜单展示

```bash
dqg-run --base-dir <project_root> <project_id> startup
```

**AI 必须**：
1. 执行脚本
2. 解析 JSON 中的 `menu` 字段
3. 渲染菜单给用户，格式如下：

```
==========================================
  研发质量门禁 — <project_id>
==========================================

  [1] ✅ Phase A    需求结构化           (已完成, 31s)
  [2] ⬜ Phase A.3  技术方案生成          ← 可执行 (可选，已有方案可 skip)
  [3] 🔒 Phase A.6  技术方案质量评审       (依赖 A.3)
  [4] 🔒 Phase A.5  技术方案覆盖度审计     (依赖 A.6)
  [5] ⬜ Phase B    单测生成             ← 可执行
  [6] ⬜ Phase C    单测覆盖审计          ← 可执行
  [7] 🔒 Phase D    代码评审             (依赖 A)
  [8] 📊 查看执行记录

请选择要执行的阶段编号:
```

4. 只有 `available: true` 的 Phase 可选择执行
5. 锁定的 Phase（`available: false` 且前置未完成）选择时提示解锁条件
6. **已完成的 Phase**（`status: approved`）选择时展示产物摘要（详情页），不重新执行
7. **等待用户输入**

---

### 步骤一-B：已完成 Phase 详情页

用户选择已 approved 的 Phase 时，执行：

```bash
dqg-run --base-dir <project_root> <project_id> detail <phase_id>
```

**AI 必须**：
1. 展示该 Phase 的产物摘要（交付物列表 + 关键指标）
2. 提供操作选项：
   - `[b] 返回菜单`
   - `[r] 重新执行此 Phase`（会重置状态为 not_started）
3. **等待用户选择**

---

### 步骤二：收集输入（逐步交互）

用户选择 Phase 后，根据 JSON 中的 `required_inputs` 和 `optional_inputs` **逐项**收集。

**逐步交互规则**：每次只问一个输入，等用户回复后再问下一个。

示例交互（Phase A）：

```
Phase A (需求结构化) 开始收集输入：

  [1/2] 需求文档 (必填)
  请提供 PRD 路径或飞书链接:
```

用户回复后：

```
  ✓ 需求文档: https://xxx.feishu.cn/docx/xxx

  [2/2] 补充图片目录 (可选，回车跳过)
  图片/原型图目录路径:
```

**飞书文档处理**：如果用户提供的是飞书链接，AI 必须自动调用飞书直读：

```bash
python3 scripts/feishu_direct_ingest.py "<feishu_url>" -o output/<project_id>/phaseA --save-raw-blocks
```

解析完成后告知用户 ingest 结果（文档数、图片数、是否有失败），然后继续。

**图片语义解析**：如果 ingest 产出了图片资产，AI 应提示用户是否需要图片语义解析：

```
  飞书文档已下载: 1 篇文档, 5 张图片

  是否需要解析图片中的业务语义？[y/n]
```

如果是：

```bash
python3 scripts/parse_image_assets.py \
  --manifest output/<project_id>/phaseA/asset_manifest.json \
  --output-json output/<project_id>/phaseA/image_semantics.json \
  --output-md output/<project_id>/phaseA/image_semantics.md \
  --details-dir output/<project_id>/phaseA/image_details \
  --backend auto
```

收集完所有输入后，将输入保存到 `output/<project_id>/<phase>/_inputs.json`。

---

### 步骤三：执行 Phase

```bash
dqg-run --base-dir <project_root> <project_id> execute <phase_id>
```

**AI 必须**：
1. 调用 execute 脚本启动 Phase
2. 读取上游产物上下文：`output/<project_id>/<phase>/_internal/_upstream_context.md`
3. 读取 Phase 对应的 skill 文件（从 JSON 的 `skill` 字段获取路径）
4. **假设暴露（Think Before Coding，不可跳过）**：在执行任何实质工作前，列出以下内容并等待用户确认：
   - 本次执行的范围假设（哪些仓库/模块/文件在范围内，哪些不在）
   - 本次执行的质量标准假设（覆盖率目标、断言标准等）
   - 排除项及排除原因
   - 如果有多种执行方案，呈现选项而非默默选一个
5. 按 skill 中定义的流程**逐步执行**任务（证据采集→全量理解→结构化产出→自检→Judge/Critique→修正）
6. 将产物写入 `output/<project_id>/<phase>/` 目录
7. **必须输出 `_reasoning_log.md`**，记录每步决策过程（finalize 时硬性校验）

**execute 自动触发的 sidecar**（无需手动调用）：
- 所有 Phase：profile manifest + bug cases + 跨项目知识注入
- Phase A.5：覆盖度矩阵自动生成（`_coverage_matrix.json`）
- Phase C：弱断言检测（`_weak_assert_context.md`）+ 业务域变异规则（`_business_mutations.md`）+ 影响范围分析（`_blast_radius.md`）
- Phase C/D：增量 diff 上下文（`_diff_context.md`）

---

### 步骤三-B：Judge/Critique（finalize 前必须执行）

Phase 产出完成后，**必须先执行 Judge/Critique 再 finalize**：

1. 读取 finalize 生成的评审 prompt：`_judge_prompt.md` / `_critique_prompt.md`
2. 切换为独立评审视角，对照 rubric 逐维度打分
3. 根据 Judge/Critique 发现修正报告
4. 修正完成后再进入 finalize

---

### 步骤四：Finalize + 校验

Phase 任务完成后：

```bash
dqg-run --base-dir <project_root> <project_id> finalize <phase_id>
```

**AI 必须**：
1. 调用 finalize 脚本（自动运行：schema 校验 + 推理日志检查 + 重跑防回退 + Phase 特定 gate）
2. 向用户展示校验结果
3. 展示交付物清单（从 JSON 的 `deliverables` 字段）
4. 展示确认清单（从 JSON 的 `approve_checklist` 字段）

**finalize 自动执行的 gate**：
- 所有 Phase：推理日志存在性 + 产物数量防回退
- Phase B：编译验证（Maven/Gradle/Go）
- Phase C：覆盖率门禁（JaCoCo XML，line >= 80%, branch >= 80%）

**finalize 自动触发的 sidecar**：
- 性能指标收集 + 规则质量追踪 + 结构化事实索引 + Golden Sample 对比
- 规则执行率 + Profile 上下文检查 + 评审链 prompt 生成
- 跨 session 进度文件（`_progress.json`）

示例：
```
Phase A 已完成，等待确认

  交付物:
    ✓ phase_a_report.md — REQ/BR/SE + GAP + OPEN 结构化报告
    ✓ phase_a_structured.json — 机器可读的结构化产物
    ✓ _reasoning_log.md — 推理日志

  确认清单:
    [ ] 所有需求点已结构化为 REQ/BR
    [ ] 关键语义已显式化为 SE
    [ ] 缺口已记录为 GAP，待确认项已记录为 OPEN

  Schema 校验: PASS
  Judge 评分: 4.2/5 ✅
  耗时: 120s

  [a] approve  [s] skip  [r] 修改后重新提交
```

---

### 步骤五：Approve + 刷新菜单

用户确认后：

```bash
dqg-run --base-dir <project_root> <project_id> approve <phase_id> -c "<备注>"
```

**AI 必须**：
1. 调用 approve 脚本
2. 重新执行 `dqg-run startup` 刷新菜单
3. 展示更新后的菜单，提示下一步可执行的 Phase
4. **等待用户选择**，不自动继续

---

## 并行 Phase 处理

当 `next_groups` 中出现 `parallel: true` 的组（如 B + C 与 A.3 链路并行）：

1. 告知用户这些 Phase 可以并行执行
2. 询问：`B 和 A.3 链路可以并行执行，是否同时进行？[y/n]`
3. 如果是，**逐个**收集每个 Phase 的输入（逐步交互），然后逐个执行 skill
4. 所有并行 Phase 完成后，逐个 finalize 和 approve

---

## 禁止事项

1. 禁止在未调用 `startup` 脚本的情况下展示菜单。
2. 禁止在未收集用户输入的情况下开始执行 Phase。
3. 禁止在未读取 skill 文件的情况下执行 Phase 任务。
4. 禁止在用户未 approve 的情况下推进到下一个 Phase。
5. 禁止手动修改 `state.json` 或 `_telemetry.jsonl`。
6. 禁止在 Phase A/A.3/A.5/A.6 输出 UT/EUT。
7. 禁止一次性列出所有输入问题（必须逐步交互）。
8. 禁止跳过飞书文档的 ingest 步骤（用户提供飞书链接时必须调用脚本）。
9. 禁止跳过 Judge/Critique 直接 finalize。
10. 禁止跳过 `_reasoning_log.md` 的输出。
