# AGENTS.md

## 项目概述

dev-quality-gate（DQG）是研发质量门禁框架，由 7 个 AI Agent 驱动，覆盖从需求到代码的全链路防漏。

## 入口

- `/dqg-starter` — 快速启动（command 文件自包含启动逻辑）
- `dqg-run <project_id> startup` — CLI 启动

### CLI 命令结构

两个入口：`dqg`（全局命令，无需 project_id）和 `dqg-run`（项目命令）。

```
dqg                              # 全局命令
├── init / dashboard / version / experiment / cache

dqg-run <project_id>             # 项目命令
├── phase:   execute / finalize / approve / skip / reset / auto / dag
├── review:  judge / critique / preference / golden
├── query:   status / next / detail / log / startup
├── ops:     metrics / observe / regression
├── tools:   wiki-compile / wiki-lint / orchestrate / cache
├── agent:   agent-run / adaptive
└── setup:   init / doctor / update / version
```

Phase ID 统一使用 Q01-Q07（旧 ID A/A.3/A.5/A.6/B/C/D 仍兼容）。

## Phase 流程

| Phase | 名称 | Skill 文件 | 依赖 | 备注 |
|-------|------|-----------|------|------|
| Q01 | 需求结构化 | `skills/requirement-structuring.md` | 无 | |
| Q02 | 技术方案生成 | `skills/tech-design-generation.md` | Q01 | 可选，已有技术方案时 skip |
| Q03 | 技术方案质量评审 | `skills/tech-quality-review.md` | Q02 | 先评审质量 |
| Q04 | 技术方案覆盖度审计 | `skills/tech-coverage-audit.md` | Q03 | 再审覆盖度 |
| Q05 | 单测生成 | `skills/unit-test-generation.md` | Q01 | |
| Q06 | 单测覆盖审计 | `skills/unit-test-audit.md` | Q01 | |
| Q07 | 代码评审 | `skills/code-review.md` | Q01 | |

## Phase DAG

```
Q01（需求结构化）
├── Q02（技术方案生成，可选）── Q03（技术方案质量评审）── Q04（技术方案覆盖度审计）── Q07（代码评审）
└── Q05（单测生成）──── Q06（单测覆盖审计）
```

Q02 可 skip（已有技术方案时）。Q03 先于 Q04。Q05/Q06 与 Q02/Q03/Q04 独立并行。

## 执行方式

每个 Phase 的执行步骤（强制，不可跳步）：

1. 启动: `dqg-run <project_id> execute <phase>`
2. 读取对应 skill 文件，按 Step 0-6 顺序执行
3. 产物 + 推理日志写入 `output/<project_id>/<phase_dir>/`（worktree 环境自动重定向到主仓库，避免产物随 worktree 清理丢失）
4. 自检: 对照 gate checklist 逐项检查
5. Judge/Critique: 切换批评者视角审视输出
6. 修正: 根据发现修正报告
7. 校验: `dqg-run <project_id> finalize <phase>`（PhaseGuardrail 统一门控）
8. 确认: `dqg-run <project_id> approve <phase>`

### Orchestrator 模式

长任务（Q03/Q04/Q06 等）主 Agent 作为 Orchestrator，禁止自己执行 skill，必须通过 SubAgent 派发。主 Agent 只负责：读 state → 决定下一个 Phase → 构造 SubAgent prompt → 收集结果。详见 `dqg_starter.md` 步骤二。

### 并行调度

同一批 available phases 无互相依赖时可并行执行（如 Q02 + Q05）。Orchestrator 同时派发多个 SubAgent，各 Phase 写不同子目录不冲突。CLI 模式: `dqg-run <project_id> dag --max-parallel 2`。

### RunStatus（执行结果分类）

Phase 执行结果用 5 值枚举区分 infra failure 和 logic failure（`runtime/result.py: RunStatus`）：

| 值 | 含义 | 计入质量评分 |
|----|------|------------|
| ok | 正常完成 | 是 |
| timeout | 网络/LLM 超时 | 否（infra） |
| adapter_crashed | Worker/Judge 适配器崩溃 | 否（infra） |
| parse_failed | LLM 输出无法解析 | 是（logic） |
| tainted | 结果被污染（rationalization/hallucination） | 是（logic） |

infra failure 的 Phase 不计入 Judge 质量评分，避免基础设施故障污染质量指标。

### DAG Preflight（执行前预检）

DAG 调度器在执行每个 Phase 前自动运行 Preflight（`runtime/preflight.py`），任一 FAIL 项阻断执行：

| 检查项 | 说明 | 失败级别 |
|--------|------|---------|
| checkpoint | 检查可恢复的 checkpoint | RESUMED/PASS |
| artifacts | 当前 Phase 产物文件存在性 | WARNING |
| dependencies | 上游依赖 Phase 已完成 | FAIL |
| upstream_artifacts | 上游 Phase 核心产物（report + structured JSON）存在且非空 | FAIL |
| cascade_failure | 上游 run_status 为 tainted/parse_failed 时级联阻断 | FAIL |
| contract | Phase contract 存在性 | WARNING |

### 上下文自动注入

Phase 执行时自动注入以下增强上下文（`context/loading/upstream_collector.py`）：

| 来源 | 说明 |
|------|------|
| Critique Gene | 历史高置信度 Critique 结晶的评审基因，模式匹配后注入 |
| Skill Crystal | 历史高分执行的成功模式结晶，同 Phase 复用 |
| Profile L0 | baseline + risk catalog 的压缩版元规则（~50% 压缩比） |
| Bug Cases | 相关性匹配的历史失败案例 |

上游产物加载带增量检测（`context/loading/file_snapshot.py`）：sha256 + mtime 快照比对，未变更的上游 Phase 跳过重读。

## 必须交付物（每个 Phase）

| 文件 | 说明 |
|------|------|
| `phase_*_report.md` | 结构化报告（Markdown） |
| `phase_*_structured.json` | 机器可读 JSON |
| `_reasoning_log.md` | 推理日志（每步决策过程） |
| `_critique.json` | Judge/Critique 结果 |
| `_internal/_prompt_manifests/*.json` | Prompt Harness 追踪信息（prompt hash、section hash、section sources、资产 hash、组装顺序、角色、schema） |
| `_internal/_prompt_policy.json` | Prompt Policy Gate 结果（manifest/hash/schema/evidence contract） |
| `_perf_metrics.json` | 性能指标 |

## 工作规范

### 语言
- 用中文交流，技术术语保持英文（context window, skill, DDD, TMF）

### 执行规则
- 状态管理必须通过 CLI，禁止手动编辑 state.json
- Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥
- 每条评审结论必须标注来源 `[来源: 文件名:行号]` 和置信度 `High/Medium/Low`
- DDD+TMF 项目禁止孤立分析单个类，必须追踪完整调用链路后再下结论

### 技术方案设计准则
- AI 亲和性原则：技术方案必须完整到 AI 可直接编码和写单测
- 完整性标准：完整 DTO + Provider interface + Gateway interface + 错误码 + 流程图 + 伪代码
- 架构选型务实：不引入过重框架，优先轻量方案
- 涉及金额计算的需求必须有资金安全专项设计

### 强制执行原则（违反即 BLOCKER）
- **推理日志必须交付**: 每个 Phase 必须输出 `_reasoning_log.md`，finalize 时硬性校验
- **Judge/Critique 在 finalize 前执行**: 禁止跳过
- **重跑禁止从零重写**: 必须在旧版基线上增量修改
- **图片 P0 必解析**: 状态机/流程图必须转为 Mermaid
- **BR 禁止概括性描述**: 必须包含完整字段、枚举值、校验规则、提示文案
- **GAP 必须有风险等级**（P0/P1/P2），**OPEN 必须有决策方**
- **SE 必须有判定依据**: 表格格式，包含 ID/绑定/语义/判定依据

### 统一执行流程（所有 Phase 适用）
```
证据采集 → 全量理解（图片先行）→ 结构化产出 → 自检 → Judge/Critique → 修正 → finalize
```

### 代码规范
- Python: ruff lint + format，target Python 3.11+
- 测试: pytest，运行 `pytest tests/ -q` 验证
- 全量检查: `ruff check src/ tests/ && pytest tests/ -q`

### 代码铁律（违反即打回）

**常量管理**
- 所有硬编码值必须定义在 `constants.py`，禁止就地硬编码

**JSON 操作**
- 读: `json_utils.load_json(path)` / `load_json_strict(path)`
- 写: `json_utils.save_json(path, data)`
- 禁止裸写 `json.loads` / `json.dumps`

**异常处理**
- 自定义异常继承 `exceptions.DQGError`
- 禁止静默吞异常（`except: pass`）

**日志**
- `from dqg.log import get_logger; log = get_logger(__name__)`
- 禁止裸用 `import logging`

**模块组织**
- 单文件不超过 400 行，单函数不超过 80 行
- 新模块必须放入对应子包，禁止在 `src/dqg/` 根目录新增 .py 文件

**存储层**
- 业务模块通过 `from dqg.store import ...`，禁止直接 import `store.core`

**路径构建**
- Phase 产物路径通过 `state_machine.phase_dir()` / `phase_dir_by_id()` 构建

**重构纪律**
- 每次重构后必须跑 `pytest tests/ -q` 确认零破坏

### 禁止事项
- 禁止在 Phase Q01/Q02/Q04/Q03 输出 UT/EUT
- 禁止自动 commit/push 代码
- 禁止编造不存在的接口、字段、逻辑
- 禁止一次性列出所有输入问题（必须逐步交互）

## 产出规范

### Schema/ID/字段命名查证（违反即 BLOCKER）

产出任何结构化 schema 数据（ID 格式、字段命名、枚举值、JSON 结构）前，**禁止自己发明格式**，必须按优先级查证：

1. **Schema 定义**（最权威）：`src/dqg/schemas/phase_*.py` 里的 pydantic `Field(pattern=...)` 就是法定格式。样例不在 schema 不代表它对。
2. **SKILL.md 样例**：SKILL 里的 JSON 样例是契约，不是示意。
3. **references / templates**：`references/report-template.md`、SKILL.md 指向的 Format spec 文件必读。
4. **已有项目产物**：`output/*/Q<phase>/phase_*_structured.json`（已通过校验的成品）、`tests/test_*_schema*.py` / `tests/fixtures/`。
5. **真正的新场景**：以上 4 步都没有才能自己定。原则：① 先问用户（多解不自决）；② 从最保守的约定开始（三位数字、扁平编号）；③ 在 `_reasoning_log.md` 显式声明"此项目首次引入 X 约定"。

**触发信号（立即停手）**：脑子里闪过"这样看起来更清晰"、"加个前缀更好"、"我觉得应该"——这是发明前兆。99% 是你没搜到，不是真没有。

**典型反例**：xiaoshu-chuku Q01 产出 `BR-001-01` 嵌套 ID，schema 要求 `^(REQ|BR)-\d+$`，触发 43 条 validation errors。根因是自己发明了"子 BR 带父号看起来更清晰"的格式，没查 `src/dqg/schemas/phase_q01.py` 和 `output/kind-care/Q01/phase_a_structured.json`（扁平 BR-001 ~ BR-146 就在眼前）。

## 文档同步铁律

代码变更后必须同步更新相关文档。`completion_gate.py` 会根据变更范围自动检测需要更新哪些文件并阻断提醒。

映射关系（由 `doc_sync_check.py` 维护）：

| 变更范围 | 需要检查的文档 |
|---------|--------------|
| Phase 注册/流程 (`phase_registry`, `state_machine`) | AGENTS.md, README.md, ROADMAP.md, dqg_starter.md |
| Runtime 结果/状态 (`result.py`, `dag_scheduler.py`) | AGENTS.md, ROADMAP.md |
| Runtime Preflight (`preflight.py`) | AGENTS.md, ROADMAP.md |
| CLI 命令 (`cli.py`, `runner.py`, `commands/`) | README.md, AGENTS.md |
| Dashboard (`reporting/dashboard/`) | README.md |
| Observe (`reporting/observability*`) | README.md, ROADMAP.md |
| Runtime/Quality 架构 | ROADMAP.md, AGENTS.md |
| Prompt Harness (`prompting/`, prompt writer) | README.md, ROADMAP.md, docs/architecture.md, AGENTS.md |
| Skill 文件 (`skills/`) | AGENTS.md |
| Profile (`profiles/`, `core/profiles.py`) | README.md, ROADMAP.md, docs/architecture.md |

原则：
- 文档中禁止硬编码易变数据（测试数量、模块列表等），用泛化描述替代
- 可自动化的部分由脚本同步，不可自动化的部分由 hook 提醒
- 不是每次变更都要更新所有文档，按映射关系精准同步

代码文件在架构变更时也需检查：`phase_registry.py`、`constants.py`、`handler_utils.py`、`handlers_execute.py`、`handlers_finalize.py`、`handlers_detection.py`、`skill_reflector.py`、`skill_auto_merge.py`、`harness_ablation.py`。

> **违反此铁律 = 技术债。completion_gate 会自动拦截未同步的变更。**

## 铁律强制执行机制

三层自动化执行，覆盖 47 条规则中的绝大部分：

| 层级 | 机制 | 覆盖范围 | 触发时机 |
|------|------|---------|---------|
| 第一层 | `report_quality_checks.py` (finalize handler) | 来源标注/ID 格式/GAP 风险等级/OPEN 决策方/置信度/推理日志质量 | finalize 时自动运行 |
| 第一层 | `finalize_checks.py` (硬性 gate) | 推理日志存在性/重跑防回退/Schema 合规/编译验证/覆盖率门禁 | finalize 时自动运行，BLOCKED 级阻断 |
| 第一层 | `phase_constraints.py` (Phase Contract) | 每个 Phase 的硬性指标约束（Q01 REQ 数/Q03 CRITICAL 数/Q04 覆盖率等），指标解析失败视为约束失败 | approve 时自动运行，`--force` 无法绕过 |
| 第一层 | `lifecycle.py` (required handler) | required handler 失败→BLOCKED 阻断 finalize，依赖死锁报错而非降级 | finalize handler 执行时 |
| 第一层 | `handlers_flow_integrity.py` (流程完整性) | 产物存在性/core_arrays 非空/judge-critique 闭环，critique 缺失为 CRITICAL | finalize pre(order=5) + post(order=76) |
| 第二层 | `semantic_guardrail.py` (PhaseGuardrail) | BR 概括性描述/覆盖度虚高/跨 Phase 越权/P0 未闭环 | finalize 后 guardrail 并发执行 |
| 第二层 | `rationalization_guard.py` | Judge 放水检测/过严误报检测 | adaptive loop judge 阶段 |
| 汇总层 | `gate_verdict.py` (GateVerdict) | 所有检查结果汇入 `_gate_verdict.json`，HARD/SOFT 二级分类，approve 统一读取 | finalize 末尾自动构建，approve 时读取决策 |
| 第三层 | `git_safety_guard.py` (PreToolUse hook) | git push/force push/--no-verify 拦截 | 每次 Bash 调用前 |
| 第三层 | `completion_gate.py` (Stop hook) | git clean/文档同步/goal-tracker | 响应结束前 |

## 多平台支持

| 工具 | 指令文件 |
|------|---------|
| Claude Code CLI | `CLAUDE.md` |
| OpenAI Codex CLI / opencode | `AGENTS.md`（本文件）|
| Google Gemini CLI | `GEMINI.md` |
| Cursor | `.cursor/rules/dqg.mdc` |

## 深度参考（按需加载）

以下内容从本文件拆分，仅在特定场景需要时读取：

| 文件 | 内容 | 何时需要 |
|------|------|---------|
| `docs/multi-agent-architecture.md` | Agent 角色 + 三阶段架构 + 投票规则 | 使用 `agent-run` / `adaptive` / `dag` 命令时 |
| `docs/architecture.md` | 包结构 + 设计模式 + Common Tasks | 开发 DQG 框架本身时 |
| `docs/performance-changelog.md` | 性能优化历史 | 排查性能问题或了解演进历史时 |

## Claude-Reflect Learnings

<!-- Auto-generated by claude-reflect. Do not edit this section manually. -->

### 执行流程
- 所有 Phase 统一执行流程：证据采集→全量理解→结构化产出→自检→Judge/Critique→修正→finalize
- 推理日志 `_reasoning_log.md` 是必须交付物，finalize 时硬性校验
- 干完活后必须同步更新 ROADMAP.md、CLAUDE.md、AGENTS.md

### 知识库
- 知识库按代码仓库建，不按需求项目建
- 统一用 `.toon` 格式（面向 AI Agent 的结构化知识表示）

### 质量保障
- 技术方案生成后必须 Multi-Agent 互审（Eng Review + Req Alignment）

<!-- End claude-reflect section -->

## 文档维护约定

- `Claude-Reflect Learnings` 由 `claude-reflect` 生成，禁止手工把本轮改动直接写进该区块
- 需要补充 learnings 时，先更新 `.claude/memory/` 源文件，再走生成流程刷新

*最后更新：2026-04-30*

> 通用工作规则见 `RULES.md`。
