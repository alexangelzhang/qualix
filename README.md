# dev-quality-gate

> 研发质量门禁 — 从需求到代码的全链路防漏 Pipeline

[![Agent索引](https://img.shields.io/badge/Agent%E7%B4%A2%E5%BC%95-AGENTS.md-orange)](AGENTS.md)
[![Roadmap](https://img.shields.io/badge/Roadmap-ROADMAP.md-blue)](ROADMAP.md)

由 6 个 AI Agent 驱动，覆盖需求结构化、技术方案审计、单测生成与审计、代码评审全生命周期。每个 Phase 有独立的 skill、结构化数据契约和质量门禁。

---

## 快速入口

| 角色 | 你关心什么 | 推荐入口 |
|:---|:---|:---|
| **使用者** | 如何快速开始？ | [30 秒上手](#30-秒上手) → [Pipeline 总览](#pipeline-总览) |
| **管理者/PM** | 能带来什么价值？ | [为什么需要 DQG](#为什么需要-dqg) → [Pipeline 总览](#pipeline-总览) |
| **开发者** | 如何扩展或贡献？ | [AGENTS.md](AGENTS.md) → [项目结构](#项目结构) |

---

## 为什么需要 DQG

| 痛点 | 表现 | DQG 解法 |
|:---|:---|:---|
| 需求遗漏 | PRD 到代码层层衰减，上线后发现漏需求 | Phase A 结构化提取 + 全链路 ID 追踪 |
| 技术方案与需求脱节 | 技术方案写了但没人逐条比对需求 | Phase A.5 逐条覆盖度审计 |
| 单测形式主义 | 覆盖率达标但测的不是业务场景 | Phase B 需求驱动生成 + Phase C 变异测试 |
| 代码评审靠经验 | 评审无结构、无证据、无追踪 | Phase D 结构化评审 + confirm-first |
| AI 幻觉 | AI 编造接口、字段、逻辑 | 反幻觉公约：来源追溯 + 置信度标注 |

---

## 30 秒上手

在 Claude Code / Cursor / Codex / Gemini 等 AI IDE 中：

```
@dqg-starter
```

Agent 会自动：
1. 检测项目状态
2. 收集你需要提供的输入（PRD 链接、技术方案、代码仓库等）
3. 按依赖关系推进 Phase，可并行的自动并行
4. 每个 Phase 完成后展示交付物和确认清单，等你 approve

## Pipeline 总览

```
A ──→ A.5 ──→ A.6      (A.5 和 A.6 可并行)
│
├──→ B ──→ C
│
└──→ D
```

| Phase | 名称 | 你需要提供 | 交付物 |
|-------|------|-----------|--------|
| A | 需求结构化 | PRD 或飞书需求文档 | REQ/BR/SE + GAP + OPEN 结构化清单 |
| A.5 | 技术方案覆盖度审计 | 技术方案文档 + (可选)代码仓库 | 覆盖度矩阵 + GAP/OPEN 闭环状态 |
| A.6 | 技术方案质量评审 | 技术方案文档 | 架构/接口/数据/异常/性能评审报告 |
| B | 单测生成 | 代码仓库 + 目标模块路径 | EUT 矩阵 + 单测代码 |
| C | 单测覆盖审计 | 代码仓库(含单测) + (可选)覆盖率报告 | 审计报告 + 变异测试结果 |
| D | 代码评审 | 代码仓库 + 评审分支名 | 评审报告 + 覆盖缺口摘要 |

每个 Phase 的执行流程：

```
收集输入 → execute → 加载 skill 执行 → 产出交付物 → finalize(校验) → judge/critique(可选) → approve(人工确认) → 下一个 Phase
```

## 安装

```bash
pip install -e ".[dev]"
```

## 使用方式

### 方式一：AI IDE（推荐）

在 Claude Code / Cursor / Codex / Gemini 等 AI IDE 中引用 `@dqg-starter`，Agent 自动编排全流程。

支持的 AI IDE 及对应指令文件：

| 工具 | 指令文件 |
|------|---------|
| Claude Code CLI | `CLAUDE.md` |
| OpenAI Codex CLI / opencode | `AGENTS.md` |
| Google Gemini CLI | `GEMINI.md` |
| Cursor | `.cursor/rules/dqg.mdc` |
| IntelliJ IDEA | `AGENTS.md` |

### 方式二：CLI 手动操作

```bash
# 查看项目状态
dqg-run PROJ status

# 逐步执行
dqg-run PROJ execute A          # 启动 Phase A
dqg-run PROJ finalize A         # 校验产物
dqg-run PROJ approve A          # 确认通过

# 质量进化（finalize 后自动生成 prompt 文件）
dqg-run PROJ judge A            # LLM-as-Judge 独立评审
dqg-run PROJ critique A         # Self-Critique 自我批评 → 生成 v2
dqg-run PROJ preference A       # RLAIF 偏好比较 v1 vs v2

# 全自动模式（交互式，每个 Phase 暂停等 approve）
dqg-run PROJ auto
dqg-run PROJ auto --model claude-opus-4-1m    # 指定模型
dqg-run PROJ auto --skip A.6                  # 跳过某 Phase

# 查看执行记录
dqg-run PROJ log

# 独立校验
dqg-validate PROJ --all
dqg-validate PROJ --phase A

# 度量采集
dqg-metrics PROJ

# Bug 案例库
python -m dqg.bug_cases                       # 查看案例库报告
python -m dqg.import_bug_cases <ingest.json>  # 从飞书 Bitable 批量导入
```

### 方式三：Quick Start Demo

```bash
bash examples/mini-prd/run_demo.sh
```

一键体验 Phase A 的完整流程（execute → finalize → approve），使用脱敏的示例 PRD。

## 项目结构

```
dev-quality-gate/
├── dqg_starter.md              # AI IDE 入口 skill（@dqg-starter 触发）
├── SKILL.md                    # Pipeline 路由器（Phase 总览 + 依赖关系）
├── AGENTS.md                   # Agent 角色索引（Codex/opencode/IntelliJ 通用）
├── CLAUDE.md                   # Claude Code 专用指令
├── GEMINI.md                   # Gemini CLI 专用指令
├── .cursor/rules/dqg.mdc      # Cursor 规则
├── skills/                     # Phase skill + 通用规则 + 工作流
│   ├── requirement-structuring.md    # Phase A
│   ├── tech-coverage-audit.md        # Phase A.5
│   ├── tech-quality-review.md        # Phase A.6（含链路追踪）
│   ├── unit-test-generation.md       # Phase B
│   ├── unit-test-audit.md            # Phase C
│   ├── code-review.md               # Phase D（链路级评审）
│   ├── quality-judge.md             # LLM-as-Judge 评审 skill
│   ├── system-rules.md              # 通用规则（含 TMF 链路追踪规则）
│   └── workflow/                    # 工作流定义
│       ├── dqg_flow_phases.md       # 全流程（每个 Phase 的完整生命周期）
│       ├── dqg_flow_multi_module.md # 多模块（按模块拆分、并行、汇总）
│       └── dqg_flow_iteration.md    # 迭代（增量重跑、收敛判断）
├── src/dqg/                    # Python package
│   ├── state_machine.py        # Phase 状态机（gate + 依赖 + 并行）
│   ├── runner.py               # dqg-run CLI（pipeline 入口）
│   ├── context_loader.py       # 上游产物自动加载 + 智能分块
│   ├── model_registry.py       # 模型感知 + token budget
│   ├── cross_phase_check.py    # 跨 Phase ID 引用校验
│   ├── telemetry.py            # 执行记录 + 可观测性
│   ├── judge.py                # LLM-as-Judge 评审 prompt 生成
│   ├── critique.py             # Self-Critique + RLAIF 融合闭环
│   ├── skill_tracker.py        # 规则级质量追踪 + 案例相关性匹配
│   ├── bug_cases.py            # Bug 案例库管理 + 归因 + 修复建议
│   ├── import_bug_cases.py     # 从飞书 Bitable 批量导入 bug 案例
│   ├── validate.py             # schema 校验 CLI
│   ├── schemas/                # 6 个 Phase 的 Pydantic 数据契约
│   ├── orchestrator.py         # 旧版编排器（兼容）
│   ├── collect_metrics.py      # 度量采集
│   └── feishu_ingest_modules/  # 飞书文档抓取（docx + bitable）
├── modules/                    # Phase 详细规则（skill 引用）
├── profiles/                   # 可切换 profile（baseline + 阈值 + 风险词典）
├── regression/                 # 基准回放集 + 回放结果
│   └── failure-library/cases/  # Bug 案例库（87 条，按 Phase 分类）
├── references/                 # 参考文件 + 模板
│   ├── risk-and-exception-catalog.md  # 风险与异常分类目录（Java DDD+TMF）
│   └── java-ddd-tmf-baseline.md       # Java 技术栈基线
├── templates/                  # 代码生成模板
├── examples/mini-prd/          # Quick Start Demo
├── tests/                      # 129 个 pytest 用例
├── pyproject.toml              # 工程配置（ruff + pytest + hatch）
└── output/                     # 项目产出目录（output/<project_id>/<phase_dir>/）
```

## 技术栈适配

默认 profile 为 `java-ddd-tmf`，当前已内置：

- `java-ddd-tmf`
- `go-service`

使用方式：

```bash
# 新项目接入时直接选 profile
dqg-run PROJ --profile java-ddd-tmf execute A
dqg-run PROJ --profile go-service auto
```

选中的 profile 会持久化到项目状态，并在 `A.5/A.6/B/C/D` 自动注入：

- baseline 文档
- 风险词典
- 质量阈值

同时在各 Phase 目录写入：

- `_profile.json`：结构化 profile 元数据
- `_profile_context.md`：可直接粘贴到报告头部的 `PROFILE_CONTEXT` 区块

例如：`output/<project>/phaseB/_profile.json`、`output/<project>/phaseB/_profile_context.md`

推荐报告模板（均包含 `PROFILE_CONTEXT` 区块）：

- Phase B：`references/eut-matrix-template.md`
- Phase C：`references/ut-audit-template.md`
- Phase D：`references/code-review-template.md`

如需扩展新技术栈，只需新增 `profiles/<profile-id>/profile.json` 和对应 baseline 文档，无需改 Python 代码。

## 质量进化闭环

DQG 借鉴 OpenSpace 的自进化思路，实现了三层质量进化机制：

**LLM-as-Judge**: `finalize` 后自动生成 `_judge_prompt.md`，由 AI IDE 执行独立评审，输出 precision/recall 估计和问题列表。

**Self-Critique + RLAIF**: Phase 执行后自我批评生成 v2 修正版本，再通过偏好比较判定哪个更好。有效的 critique 自动沉淀为 bug case。

**Bug 案例库**: 87 条真实 bug 案例（从飞书 Bitable 批量导入），按 Phase 分类，执行时基于相关性匹配自动注入为反例，token 节省 77%。

```bash
# 质量进化命令
dqg-run PROJ judge A            # 独立评审
dqg-run PROJ critique A         # 自我批评 → v2
dqg-run PROJ preference A       # v1 vs v2 偏好比较

# Bug 案例库
python -m dqg.bug_cases         # 查看报告
python -m dqg.import_bug_cases <ingest.json>  # 从飞书导入
```

## 质量保障

```bash
# lint
ruff check src/ tests/

# 测试
pytest tests/ -v

# 全量校验
ruff check src/ tests/ && pytest tests/ -q
```

## 可观测与告警

轻量看板（日报/周报）和可观测告警可通过 `dqg-observe` 生成：

```bash
# 生成日报（JSON + Markdown）
dqg-observe report --period daily

# 生成周报，并按项目/Phase 过滤
dqg-observe report --period weekly --project rights-platform --phase A.6

# 每日任务：生成日报 + 写入历史指标仓 + 告警输出（建议配合 cron）
dqg-observe daily
```

输出目录：

- 报告：`observability/reports/<daily|weekly>/*.json|*.md`
- 指标仓：`observability/metrics_history.jsonl`
- 告警：`observability/alerts/*.json|*.md`
- Prometheus：`observability/prometheus/*.prom`（`dqg-observe daily` 自动产出）

当前指标覆盖：

- `Phase 通过率`
- `平均处理时长`
- `GAP 闭环率`
- `BLOCK 数`（A.6 `CRITICAL_GAP` + Phase D `BLOCKER`）

当前告警规则：

- `BLOCK_SPIKE`
- `PHASE_FAILURE_RATE`
- `FAILURE_LIBRARY_REGRESSION`（失败样例回归退化）

周报会额外聚合失败样例库趋势（如果已执行过 `dqg-regression run`）：

- `误报`
- `漏报`
- `边界输入`
- `弱文档输入`

## 飞书文档抓取

支持 docx 文档和多维表格（Bitable）两种类型的 Wiki 节点：

```bash
# 抓取飞书文档（docx / wiki）
python scripts/feishu_direct_ingest.py "<feishu_url>" -o output/<project_id>/phaseA

# 抓取飞书多维表格（bitable）— 自动识别，无需额外参数
python scripts/feishu_direct_ingest.py "<bitable_wiki_url>" -o output/<project_id>/phaseA
```

性能优化：图片并发下载（8 workers）、引用文档并发抓取（4 workers）、单文档内 API 调用并发。

## Feishu 回放快照回归

用于验证 `feishu_ingest` 重构前后产物是否一致，重点比对以下文件：

- `ingest.json`
- `asset_manifest.json`
- `dependency_graph.json`
- `aggregate_ingest.json`
- `plain_text.txt`

首次生成或更新快照：

```bash
DQG_FEISHU_TEST_URL="https://mi.feishu.cn/docx/xxx" \
DQG_FEISHU_SNAPSHOT_CASE="sample-doc" \
DQG_UPDATE_SNAPSHOTS=1 \
pytest tests/integration/test_feishu_ingest_snapshot.py -q
```

日常回归校验：

```bash
DQG_FEISHU_TEST_URL="https://mi.feishu.cn/docx/xxx" \
DQG_FEISHU_SNAPSHOT_CASE="sample-doc" \
pytest tests/integration/test_feishu_ingest_snapshot.py -q
```

说明：

- 未提供 `DQG_FEISHU_TEST_URL` 时，真实回放测试会自动跳过
- 快照基线默认存放在 `tests/fixtures/feishu_ingest_snapshots/`
- 回放时会自动规范化时间戳、绝对路径等易波动字段，减少无意义 diff

## 基准回放集

用于校验平台级输出是否发生新增、回归或语义偏移：

```bash
# 跑全量基准回放集
dqg-regression run

# 只跑某个样本
dqg-regression run --case rights-platform
```

当前内置样本：

- `rights-platform`：权益中心平台化改造金标准快照
- `mrs`：中型改造样本
- `api-addition-demo`：接口新增样本
- `refactor-demo`：重构样本
- `failure-library/*`：失败样例库（误报 / 漏报 / 边界输入 / 弱文档输入）

回放结果会输出到 `regression/runs/<timestamp>/summary.json|.md`，并按文件分类：

- `新增`：基线中没有、当前输出新增
- `回归`：基线中存在、当前输出缺失
- `偏移`：文件仍存在，但内容发生变化

若任一回放 case 不通过，`dqg-regression run` 会返回非 0，可直接用于规则改动后的回归门禁。

失败样例库趋势统计：

```bash
# 周维度统计误报/漏报趋势
dqg-regression trend --period weekly
```

相关产物：

- 样例库：`regression/cases/failure-library/`
- 历史：`regression/failure-library/history.jsonl`
- 周趋势：`regression/failure-library/trends/weekly/summary.json|.md`
