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

## 核心规则（违反即 BLOCKER）

| # | 规则 | 约束 |
|:-:|:---|:---|
| 1 | **脚本驱动状态** | 状态管理必须通过 `dqg-run` 执行，禁止手动构造 |
| 2 | **逐步交互** | 多步输入时，每次只展示一个问题，等待用户回复后再展示下一个。禁止一次性列出所有问题 |
| 3 | **等待用户输入** | 菜单展示、输入收集、确认点必须等待用户输入，禁止假设或自动继续 |
| 4 | **Skill 驱动执行** | Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥 |
| 5 | **收尾四步** | 产出检测 → 校验(finalize) → 人工确认(approve) → 刷新菜单 |
| 6 | **结构化产物** | 每个 Phase 同时产出 markdown 报告 + JSON 结构化文件 |
| 7 | **控制权交还** | Phase 产出后进入 finalize 流程，不自动建议下一步 |
| 8 | **反幻觉公约** | 遵守 `skills/system-rules.md`，每条结论标注来源和置信度 |
| 9 | **工作流遵循** | 遵守 `skills/workflow/` 下的工作流定义，多模块按模块分别执行，迭代按增量重跑规则 |

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
  [2] ⬜ Phase A.5  技术方案覆盖度审计     ← 可执行
  [3] ⬜ Phase A.6  技术方案质量评审       ← 可执行 (可与 A.5 并行)
  [4] ⬜ Phase B    单测生成             ← 可执行
  [5] ⬜ Phase C    单测覆盖审计          ← 可执行
  [6] ⬜ Phase D    代码评审             ← 可执行
  [7] 📊 查看执行记录

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
2. 读取上游产物上下文：`output/<project_id>/<phase>/_upstream_context.md`
3. 读取 Phase 对应的 skill 文件（从 JSON 的 `skill` 字段获取路径）
4. 按 skill 中定义的流程**逐步执行**任务
5. 将产物写入 `output/<project_id>/<phase>/` 目录

---

### 步骤四：Finalize + 校验

Phase 任务完成后：

```bash
dqg-run --base-dir <project_root> <project_id> finalize <phase_id>
```

**AI 必须**：
1. 调用 finalize 脚本（自动运行 schema 校验 + 跨 Phase ID 引用检查）
2. 向用户展示校验结果
3. 展示交付物清单（从 JSON 的 `deliverables` 字段）
4. 展示确认清单（从 JSON 的 `approve_checklist` 字段）

示例：
```
Phase A 已完成，等待确认

  交付物:
    ✓ phase_a_report.md — REQ/BR/SE + GAP + OPEN 结构化报告
    ✓ phase_a_structured.json — 机器可读的结构化产物

  确认清单:
    [ ] 所有需求点已结构化为 REQ/BR
    [ ] 关键语义已显式化为 SE
    [ ] 缺口已记录为 GAP，待确认项已记录为 OPEN

  Schema 校验: PASS
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

当 `next_groups` 中出现 `parallel: true` 的组（如 A.5 + A.6）：

1. 告知用户这些 Phase 可以并行执行
2. 询问：`A.5 和 A.6 可以并行执行，是否同时进行？[y/n]`
3. 如果是，**逐个**收集每个 Phase 的输入（逐步交互），然后逐个执行 skill
4. 所有并行 Phase 完成后，逐个 finalize 和 approve

---

## 禁止事项

1. 禁止在未调用 `startup` 脚本的情况下展示菜单。
2. 禁止在未收集用户输入的情况下开始执行 Phase。
3. 禁止在未读取 skill 文件的情况下执行 Phase 任务。
4. 禁止在用户未 approve 的情况下推进到下一个 Phase。
5. 禁止手动修改 `_state.json` 或 `_telemetry.jsonl`。
6. 禁止在 Phase A/A.5/A.6 输出 UT/EUT。
7. 禁止一次性列出所有输入问题（必须逐步交互）。
8. 禁止跳过飞书文档的 ingest 步骤（用户提供飞书链接时必须调用脚本）。
