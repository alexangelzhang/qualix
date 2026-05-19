---
name: dqg-execution-guide
description: "DQG Phase 执行指南 — 用户选择 Phase 后按需加载"
---

# DQG Phase 执行指南

> 启动逻辑见 `.claude/commands/dqg-starter.md`。

## Phase DAG

```
Q01（需求结构化）
├── Q02（技术方案生成，可选）── Q03（技术方案质量评审）── Q04（技术方案覆盖度审计）── Q07（代码评审）
└── Q05a（EUT矩阵设计）→ Q05b（单测代码生成）──── Q06（单测覆盖审计）
```

Q02 可 skip（已有技术方案时）；Q05a/Q05b/Q06 与 Q02/Q03/Q04 独立并行。

### Phase 自动化能力

| Phase | execute 自动注入 | finalize 硬性 Gate | 特有能力 |
|-------|-----------------|-------------------|---------|
| Q01 | phase_contract + bug cases + 跨项目知识 | 推理日志 + 防回退 + auto_checks | 假设前置 + 边界约定 + 范围外发现 |
| Q02 | phase_contract | 推理日志 + 防回退 + auto_checks | 实施切片指导(XS/S/M/L/XL) + 范围外发现 |
| Q03 | phase_contract | 推理日志 + 防回退 + auto_checks | 12类异常矩阵 + Failure Mode 分析 |
| Q04 | phase_contract + coverage_matrix | 推理日志 + 防回退 + auto_checks | REQ/BR/SE→技术设计映射矩阵 |
| Q05 | phase_contract + data_patterns + se_code_mapping | 推理日志 + 防回退 + **编译验证** + auto_checks | Mock优先级 + DAMP + 范围外发现 |
| Q06 | phase_contract + weak_assert + business_mutations + blast_radius + data_patterns + se_code_mapping + diff_context | 推理日志 + 防回退 + **覆盖率≥80%** + auto_checks | CONFLICT状态 + 变异测试 + 弱断言检测 |
| Q07 | phase_contract + diff_context + se_code_mapping | 推理日志 + 防回退 + auto_checks | 变更大小门禁 + 评论标签 + 依赖审查 |

### 跨 Phase 数据流

- Q01 SE 列表 → dynamic_rubric + business_mutations + coverage_matrix + phase_contract
- Q06 bug cases → data_patterns → 注入 Q05/Q06
- 所有 Phase bug cases → skill_factory + lesson_inference + skill_evolution
- 跨项目 knowledge_network → 自动注入 `_cross_project_insights.md`
- 下游 Phase 发现需求问题 → UPSTREAM_UPDATE_NEEDED → 触发 Q01 重开

---

## 核心规则（违反即 BLOCKER）

| # | 规则 |
|:-:|:---|
| 1 | **脚本驱动状态** — 状态管理必须通过 `dqg-run`，禁止手动构造 |
| 2 | **逐步交互** — 多步输入时每次只展示一个问题，等待回复后再展示下一个 |
| 3 | **等待用户输入** — 菜单展示、输入收集、确认点必须等待用户输入 |
| 4 | **Skill 驱动执行** — Phase 任务必须读取对应 skill 文件执行 |
| 5 | **收尾四步** — 产出检测 → finalize → approve → 刷新菜单 |
| 6 | **结构化产物** — 每个 Phase 同时产出 markdown 报告 + JSON 结构化文件 |
| 7 | **推理日志必须交付** — 每个 Phase 必须输出 `_reasoning_log.md`，finalize 硬性校验 |
| 8 | **自动质量闭环** — 自检→Judge/Critique→修正 AI 内部完成，仅评分 < 3.5 或 CRITICAL 问题时暂停 |
| 9 | **控制权交还** — Phase 产出后进入 finalize，不自动建议下一步 |
| 10 | **反幻觉公约** — 每条结论标注来源和置信度 |

---

## 执行流程

### 步骤一：收集输入（逐步交互）

根据 JSON 中的 `required_inputs` 和 `optional_inputs` **逐项**收集，每次只问一个，等回复后再问下一个。

**飞书文档**：用户提供飞书链接时必须自动调用：
```bash
python3 scripts/feishu_direct_ingest.py "<feishu_url>" -o output/<project_id>/phaseA --save-raw-blocks
```

**图片语义解析**：ingest 产出图片时询问是否解析，如是：
```bash
python3 scripts/parse_image_assets.py \
  --manifest output/<project_id>/phaseA/asset_manifest.json \
  --output-json output/<project_id>/phaseA/image_semantics.json \
  --output-md output/<project_id>/phaseA/image_semantics.md \
  --details-dir output/<project_id>/phaseA/image_details \
  --backend auto
```

收集完毕后保存到 `output/<project_id>/<phase>/_inputs.json`。

### 步骤二：执行 Phase

```bash
dqg-run --base-dir <project_root> <project_id> execute <phase_id>
```

#### Orchestrator 模式（推荐，长任务必须）

主 Agent 作为 Orchestrator，**禁止自己执行 Phase skill**。必须通过 Agent tool 派发 SubAgent：

1. 读取 `dqg-run execute` 输出的上下文路径和 skill 路径
2. 构造 SubAgent prompt（包含：目标、上下文路径、skill 路径、产出要求）
3. 通过 Agent tool 派发 SubAgent 执行，自己等待结果
4. SubAgent 完成后，主 Agent 只做结果验收（检查产出文件是否存在）

SubAgent prompt 模板：
```
你是 DQG Phase {phase_id} 的执行 Agent。

目标：按 skill 流程完成 Phase {phase_id}（{phase_name}）的全部产出。

上下文：
- 上游证据：output/{project_id}/{phase_dir}/_internal/_upstream_context.md
- Phase Skill：{skill_path}（必须读取并严格按流程执行）
- 产出目录：output/{project_id}/{phase_dir}/

执行要求：
1. 先读取 skill 文件，理解完整流程
2. 读取上游证据
3. 按 skill 流程逐步执行（证据采集→全量理解→结构化产出）
4. 输出 _reasoning_log.md
5. 自动质量闭环（自检→Judge/Critique→修正）
6. 产出 markdown 报告 + JSON 结构化文件

禁止：跳过 skill 中的任何 STOP 检查点、跳过 _reasoning_log.md、输出 UT/EUT（Q01-Q04）
```

**为什么用 Orchestrator 模式**：主 Agent 持有完整 pipeline 计划（state.json + Phase DAG），如果同时执行 Phase skill（读 3000 行技术方案 + 逐维度评审），上下文被撑满，后续 Phase 调度质量下降。SubAgent 有独立上下文，执行完只返回结果，不污染主 Agent。

#### 直接执行模式（简单 Phase 或调试时）

当 Phase 任务简单（如 Q01 只需结构化一份 PRD），或需要调试时，主 Agent 可直接执行：

1. 读取上游产物：`output/<project_id>/<phase>/_internal/_upstream_context.md`
2. 读取 Phase 对应 skill 文件（从 JSON 的 `skill` 字段获取路径）
3. **假设暴露（不可跳过）**：列出范围假设、质量标准假设、排除项，等待用户确认
4. 按 skill 流程执行（证据采集→全量理解→结构化产出）
5. 输出 `_reasoning_log.md`（finalize 硬性校验）
6. 自动质量闭环（自检→Judge/Critique→修正），仅评分 < 3.5 或 CRITICAL 时暂停

#### 模式选择规则

**手动模式（用户通过 /dqg-starter 菜单交互）：一律直接执行，不派 SubAgent。** 主会话直接读取 skill 文件执行，可以实时验证每一步产出。SubAgent 有独立 context，产出质量不可控。

**自动模式（DAG 批量执行 / 无人值守）：按下表选择。**

| 条件 | 模式 |
|------|------|
| 技术方案 > 1000 行，或 Phase 涉及逐条审计（Q03/Q04/Q06） | Orchestrator（必须） |
| 需要读取代码仓库（Q05/Q07） | Orchestrator |
| PRD < 500 行的简单 Q01 | 直接执行（可选） |
| 调试或重跑单个 Phase | 直接执行（可选） |

#### 并行调度（多 Phase 同时可执行时）

当 `dqg-run status` 显示多个 Phase 可执行（如 Q02 + Q05 都 available），Orchestrator 应并行派发：

**判断规则**：同一批 available phases 之间没有互相依赖（A 不在 B 的 depends_on 里，B 也不在 A 的 depends_on 里），即可并行。

**并行 Phase DAG 示例**：
```
Q01 完成后 → Q02 + Q05 可并行
Q02 完成后 → Q03（Q05 可能仍在执行，不阻塞）
Q03 完成后 → Q04
Q04 完成后 → Q07（需等 Q05/Q06 链路也完成）
```

**Orchestrator 并行派发方式**：

```
# 在同一条消息中发起多个 Agent tool 调用（Claude Code 原生支持并行 tool call）
Agent(prompt="执行 Phase Q02...", subagent_type="general-purpose")
Agent(prompt="执行 Phase Q05...", subagent_type="general-purpose")
```

每个 SubAgent 在独立上下文中执行，互不干扰。主 Agent 等待所有并行 SubAgent 完成后，逐个 finalize + approve，再检查下一批可执行 Phase。

**CLI 并行（无人值守模式）**：
```bash
dqg-run --base-dir <project_root> <project_id> dag --max-parallel 2
```
DAG 调度器自动识别并行组，ThreadPoolExecutor 并发执行。

**注意事项**：
- 并行 Phase 共享同一个 output 目录，但各自写不同的 phase 子目录，不冲突
- finalize 必须串行（state.json 是共享资源），并行执行完后逐个 finalize
- 如果一个并行 Phase 失败，不影响其他并行 Phase 继续执行

### 步骤三：Finalize

```bash
dqg-run --base-dir <project_root> <project_id> finalize <phase_id>
```

展示：校验结果 + 交付物清单（`deliverables` 字段）+ 确认清单（`approve_checklist` 字段）。

### 步骤四：Approve + 刷新菜单

```bash
dqg-run --base-dir <project_root> <project_id> approve <phase_id> -c "<备注>"
```

approve 后重新执行 `dqg-run startup` 刷新菜单，**等待用户选择**，不自动继续。

---

## 禁止事项

1. 未调用 `startup` 脚本时展示菜单
2. 未收集用户输入时开始执行 Phase
3. 未读取 skill 文件时执行 Phase 任务
4. 用户未 approve 时推进到下一个 Phase
5. 手动修改 `state.json` 或 `_telemetry.jsonl`
6. 在 Q01/Q02/Q04/Q03 输出 UT/EUT
7. 一次性列出所有输入问题（必须逐步交互）
8. 跳过飞书文档的 ingest 步骤
9. 跳过 Judge/Critique 直接 finalize
10. 跳过 `_reasoning_log.md` 的输出
