# AGENTS.md

## 项目概述

dev-quality-gate（DQG）是研发质量门禁框架，由 7 个 AI Agent 驱动，覆盖从需求到代码的全链路防漏。

## 入口

- 全流程引导: 读取 `dqg_starter.md` 开始
- CLI 启动: `python -m dqg.runner <project_id> startup`

## Phase 流程

| Phase | 名称 | Skill 文件 | 依赖 | 备注 |
|-------|------|-----------|------|------|
| A | 需求结构化 | `skills/requirement-structuring.md` | 无 | |
| A.3 | 技术方案生成 | `skills/tech-design-generation.md` | A | 可选，已有技术方案时 skip |
| A.6 | 技术方案质量评审 | `skills/tech-quality-review.md` | A.3 | 先评审质量 |
| A.5 | 技术方案覆盖度审计 | `skills/tech-coverage-audit.md` | A.6 | 再审覆盖度 |
| B | 单测生成 | `skills/unit-test-generation.md` | A | |
| C | 单测覆盖审计 | `skills/unit-test-audit.md` | A | |
| D | 代码评审 | `skills/code-review.md` | A | |

## 执行方式

每个 Phase 的执行步骤（强制，不可跳步）：

1. 启动: `python -m dqg.runner <project_id> execute <phase>`
2. 读取对应 skill 文件，按 Step 0-6 顺序执行
3. 产物 + 推理日志写入 `output/<project_id>/<phase_dir>/`
4. 自检: 对照 gate checklist 逐项检查
5. Judge/Critique: 切换批评者视角审视输出
6. 修正: 根据发现修正报告
7. 校验: `python -m dqg.runner <project_id> finalize <phase>`（硬性校验推理日志+防回退）
8. 确认: `python -m dqg.runner <project_id> approve <phase>`

## 必须交付物（每个 Phase）

| 文件 | 说明 |
|------|------|
| `phase_*_report.md` | 结构化报告（Markdown） |
| `phase_*_structured.json` | 机器可读 JSON |
| `_reasoning_log.md` | 推理日志（每步决策过程） |
| `_critique.json` | Judge/Critique 结果 |
| `_perf_metrics.json` | 性能指标（Token/成本/改进建议） |

## Agent 角色

| 角色 | 职责 | Context | 模型建议 |
|------|------|---------|---------|
| Worker Agent | 按 skill 执行 Phase 任务，输出报告+JSON+推理日志 | 独立：只看输入材料+skill | Opus（最强推理） |
| Architect Agent | Phase A.3 专用：基于需求生成技术方案（HLD+LLD+DTO+流程图） | 独立：需求产物+代码仓库+知识库 | Opus（深度设计） |
| Judge Agent | 独立评审产物准确性，打分+找问题 | 独立：只看产物，看不到 Worker 推理过程 | Sonnet（平衡） |
| Critique Agent | 假设有遗漏主动找问题 | 独立：看产物+Judge 结果 | Opus（深度推理） |
| Preference Agent | 比较 v1 vs v2 偏好 | 独立：看两个版本 | Sonnet |
| Orchestrator | DAG 调度 + 并行编排 + 自适应循环 | 全局视图 | Haiku（轻量） |

## Multi-Agent 架构（三个阶段）

### Phase 1: Prompt 隔离模式

生成独立 prompt 文件，在当前 session 中用 subagent 执行。适合日常使用。

```bash
# 显示并行执行计划（哪些 Phase 可以并行）
dqg-run <project> orchestrate <phase> --plan

# 生成 Worker/Judge/Critique 三个独立 prompt 文件
dqg-run <project> orchestrate <phase>
```

生成的文件：
- `_worker_prompt.md` — Worker Agent 读取执行
- `_judge_prompt_v2.md` — Judge Agent 读取评审（看不到 Worker 推理日志）
- `_critique_prompt_v2.md` — Critique Agent 读取批评

执行方式：主 session spawn 三个 subagent，依次执行 Worker → Judge → Critique。

源码: `src/dqg/multi_agent.py`

### Phase 2: 真独立 Agent 模式

通过 API 调用真正独立的 LLM 实例，支持不同模型+自动 fallback。适合 CI/CD 集成。

```bash
# 默认配置（Claude 主力 + DeepSeek 备用）
dqg-run <project> agent-run <phase>

# 自定义模型
dqg-run <project> agent-run <phase> \
  --primary claude-opus-4-6 \
  --fallback deepseek-chat \
  --judge-model claude-sonnet-4-6

# 国内环境（Claude 被墙时）
dqg-run <project> agent-run <phase> \
  --primary deepseek-chat \
  --fallback qwen-plus
```

支持的模型：

| 厂商 | 模型 | 环境变量 |
|------|------|---------|
| Anthropic | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o, o4-mini, codex-mini | `OPENAI_API_KEY` |
| Google | gemini-2.5-pro, gemini-2.5-flash | `GOOGLE_API_KEY` |
| DeepSeek | deepseek-chat, deepseek-coder | `DEEPSEEK_API_KEY` |
| 阿里 | qwen-plus, qwen-max | `DASHSCOPE_API_KEY` |
| Moonshot | kimi-chat, moonshot-v1-8k | `MOONSHOT_API_KEY` |

Fallback 机制：主模型调用失败（网络/限流/被墙）→ 自动切换备用模型 → 结果标记为 `fallback`。

源码: `src/dqg/agent_framework.py`

### Phase 3: 自适应循环模式

Judge 不通过 → 自动触发 Worker 修正 → 再次 Judge → 循环直到通过或达上限。支持多 Judge 并行投票（去重重复 model，单 Judge 失败不阻断）。

```bash
# 默认配置（最多 3 轮，2 个 Judge 投票）
dqg-run <project> adaptive <phase>

# 自定义配置
dqg-run <project> adaptive <phase> \
  --primary claude-opus-4-6 \
  --judge-models claude-sonnet-4-6,deepseek-chat \
  --max-iter 3 \
  --threshold 3.5 \
  --fallback qwen-plus
```

自适应循环流程：
```
Iter 1: Worker 执行 → 多 Judge 投票 → 不通过？→ Critique 找问题
Iter 2: Worker 根据反馈修正 → 多 Judge 投票 → 不通过？→ Critique
Iter 3: Worker 再次修正 → 多 Judge 投票 → 通过/达上限
```

投票规则：
- 全部 PASS → 共识 PASS
- 过半 FAIL → 共识 FAIL
- 其他 → PASS_WITH_CONCERNS
- 均分 ≥ threshold → 通过

产出文件：
- `_judge_iter1.json` / `_judge_iter2.json` — 每轮投票结果
- `_adaptive_summary.json` — 循环总结（迭代次数/最终判定/模型使用/耗时）

源码: `src/dqg/adaptive_loop.py`

## Phase 间 DAG

```
A（需求结构化）
├── A.3（技术方案生成，可选）── A.6（技术方案质量评审）── A.5（技术方案覆盖度审计）── D（代码评审）
└── B（单测生成）──── C（单测覆盖审计）
```

A.3 可 skip（已有技术方案时）。A.6 先于 A.5（先评审质量，再审覆盖度）。B/C 与 A.3/A.6/A.5 独立并行。

## Multi-Agent 编排

三个 Agent 通过文件交换数据，context 完全隔离：

```
Worker 写入 → phase_a_report.md + _reasoning_log.md
                    ↓（Judge 只读报告，看不到推理日志）
Judge 写入  → _judge_result.json
                    ↓
Critique 写入 → _critique.json
```

## 统一记忆层

所有 Agent 共享 `MemoryLayer`（SQLite 后端）：
- `mem.search("并发")` — 统一搜索事实/图片/文本/代码
- `mem.index_phase(proj, phase)` — 索引 Phase 产物（关键输入未变化时跳过重建）
- 项目级 fact search cache 按输入版本自动 namespace，索引变化后自动失效
- `mem.build_links()` — 构建跨项目知识链接
- `mem.get_insights(proj, phase)` — 获取历史经验
- `mem.search_code("幂等")` — 业务概念→代码关键词智能搜索

## CLI 命令一览

```bash
python -m dqg.runner <project_id> status          # 状态看板
python -m dqg.runner <project_id> execute <phase>  # 启动 Phase
python -m dqg.runner <project_id> finalize <phase> # 校验产物（硬性校验推理日志+防回退）
python -m dqg.runner <project_id> approve <phase>  # 确认通过
python -m dqg.runner <project_id> skip <phase>     # 跳过 Phase
python -m dqg.runner <project_id> judge <phase>    # LLM-as-Judge 评审
python -m dqg.runner <project_id> critique <phase> # Self-Critique 自我批评
python -m dqg.runner <project_id> preference <phase> # RLAIF 偏好比较
python -m dqg.runner <project_id> golden <phase>   # Golden Sample 对比
python -m dqg.runner <project_id> golden <phase> --save  # 保存为标杆
python -m dqg.runner <project_id> orchestrate <phase>    # Multi-Agent Phase 1: 生成独立 prompt
python -m dqg.runner <project_id> orchestrate <phase> --plan  # 显示并行执行计划
python -m dqg.runner <project_id> agent-run <phase>      # Multi-Agent Phase 2: 真独立 Agent 执行
python -m dqg.runner <project_id> adaptive <phase>       # Multi-Agent Phase 3: 自适应循环+多Judge投票
python -m dqg.runner <project_id> auto             # 全自动推进
python -m dqg.runner <project_id> log              # 执行记录
python -m dqg.runner <project_id> next             # 下一步
```

## 质量进化闭环

`finalize` 后自动生成三个 prompt 文件到 phase 目录：

| 文件 | 用途 | 触发命令 |
|------|------|---------|
| `_judge_prompt.md` | 独立评审（打分 + 问题列表） | `judge <phase>` |
| `_critique_prompt.md` | 自我批评（找遗漏 → 生成 v2） | `critique <phase>` |
| `_preference_prompt.md` | v1 vs v2 偏好比较 | `preference <phase>` |

反馈飞轮: 执行 → 自我批评 → 修正 → 偏好比较 → 有效 critique 自动沉淀为 bug case → 下次执行时注入为反例

## Bug 案例库

```bash
python -m dqg.bug_cases                    # 查看案例库报告
python -m dqg.bug_cases --phase C          # 按 Phase 过滤
python -m dqg.bug_cases --status open      # 按状态过滤
python -m dqg.import_bug_cases <ingest.json>  # 从飞书 Bitable 批量导入
```

案例库路径: `regression/failure-library/cases/{phaseA,phaseA5,phaseA6,phaseC}/`


## 性能治理近况

- 2026-04-08: `agent-run` / `adaptive` 已切换为有效上下文去重读取；当 `_upstream_context.md` 已存在时，不再重复注入 `_profile_context.md` / `_bug_cases.md` / `_diff_context.md`
- 2026-04-08: `write_phase_profile_manifest()` 已切换为 relevance-matched bug case manifest；无相关案例时会清理陈旧 `_bug_cases.md`，避免旧案例残留注入
- 2026-04-08: `load_profile_context()` 已增加基于路径 + mtime 的进程内缓存，重复 Phase 执行不再反复全文读取 baseline / risk catalog
- 2026-04-08: `LoadedContext` 已新增流式写盘 helper，`cmd_execute` / `cmd_auto` 写 `_upstream_context.md` 时不再先构造整块 `full_text`；同时改用轻量 `relevance_seed` 作为 bug case relevance matching 的种子
- 2026-04-08: `load_context()` 已完成 retrieval-first evidence pack 收口，`_upstream_context.md` 固定输出 Pack 概览 + 证据摘要 + 关键引用；Phase A 优先使用当前输入证据，bug case seed 会排除 profile / memory / 已注入 bug cases，避免空上下文误注入和重复放大
- 2026-04-08: `chunk_processor.py` 已为 `_split_large_chunk()` / `_compact_chunk()` 增加局部 token cache，重复段落与压缩中间态不再反复 `estimate_tokens()`
- 2026-04-08: Judge / Critique / Experiment 的 bug case relevance 输入已统一切到 excerpt/seed 模式，避免从报告、结构化 JSON、skill 全文中反复拼接大文本
- 2026-04-08: `judge` / `critique` / `experiment` 的 bug case relevance 输入已改为 excerpt/seed 复用，避免把报告、结构化 JSON、skill 全文直接喂给相关性匹配
- 2026-04-08: `adaptive_loop` 的 multi-judge vote 已并行化，支持重复 judge model 去重、单 Judge 失败容错和投票结果顺序稳定
- 2026-04-08: `semantic_cache` / `MemoryLayer.search()` 已切到版本感知 cache namespace，支持按项目/类型/版本精确失效
- 2026-04-08: `MemoryLayer.index_phase()` 已支持关键输入签名增量索引；`finalize` 统一接入，未变化跳过重建，变化后自动清理项目级 fact search cache
- 2026-04-08: `adaptive_loop` 已接通 `Agent.query_cache`，重复 multi-judge / critique / fixer 路径不再重复调用 LLM；FTS5 中文检索已升级为边界感知分词 + identifier subtoken，并在 fact/text/image/code 统一复用 query builder 与 post-filter；Phase C `execute` 新增 `_internal/_weak_assert_context.{json,md}`，提前暴露 weak assert 候选

## 工作规范

### 语言
- 用中文交流，技术术语保持英文（context window, skill, DDD, TMF）

### 执行规则
- 状态管理必须通过 CLI，禁止手动编辑 state.json
- Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥
- 每条评审结论必须标注来源 `[来源: 文件名:行号]` 和置信度 `High/Medium/Low`
- DDD+TMF 项目禁止孤立分析单个类，必须追踪完整调用链路后再下结论

### 技术方案设计准则
- Phase 顺序重构：A → A.3（可选）→ A.6 → A.5 → B → C → D（先生成方案，再评审质量，最后审覆盖度）
- AI 亲和性原则：技术方案必须完整到 AI 可直接编码和写单测，check 时也要从 AI 亲和性维度审查
- 完整性标准：完整 DTO + Provider interface + Gateway interface + 错误码 + StatusTransition + 配置项 + 流程图 + 伪代码
- 架构选型务实：不引入过重框架（如 TMF），优先轻量方案（如策略模式）
- 外部系统未提供接口时：基于业务需求推导接口需求清单，列出待确认技术细节
- 技术方案补充维度（参考飞书模板）：接口协议清单（含工时）+ 外部依赖 + 部署灰度 + 影响范围 + 可观测性
- 涉及金额计算的需求必须有资金安全专项设计

### 强制执行原则（违反即 BLOCKER）
- **推理日志必须交付**: 每个 Phase 必须输出 `_reasoning_log.md`，记录每步决策过程，finalize 时硬性校验
- **Judge/Critique 在 finalize 前执行**: 禁止跳过自检和 Judge/Critique 直接 finalize
- **重跑禁止从零重写**: 必须在旧版基线上增量修改，新版必须是旧版超集
- **图片 P0 必解析**: 状态机/流程图必须转为 Mermaid，无法解析标为 GAP P0 阻断
- **BR 禁止概括性描述**: 必须包含完整字段、枚举值、校验规则、提示文案，细到能写测试用例
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
- 所有 Phase ID、目录名、文件名映射、数字阈值、LLM 定价必须定义在 `constants.py`，禁止就地硬编码
- `state_machine.py` 的 `PHASE_DEFS` 是 Phase 元数据的权威来源

**JSON 操作**
- 读: `json_utils.load_json(path)` / `load_json_strict(path)`
- 写: `json_utils.save_json(path, data)`
- 序列化: `json_utils.dump_json_str(data)`
- 禁止裸写 `json.loads` / `json.dumps`

**异常处理**
- 自定义异常继承 `exceptions.DQGError`，按类型用 `PhaseError` / `ValidationError` / `StorageError` / `ConfigError` / `LLMError`
- 禁止静默吞异常（`except: pass`）

**日志**
- `from dqg.log import get_logger; log = get_logger(__name__)`
- 禁止裸用 `import logging`

**模块组织**
- 单文件不超过 400 行，单函数不超过 80 行
- 新模块必须放入对应子包，禁止在 `src/dqg/` 根目录新增 .py 文件
- 拆分模块时用 facade 模式保持向后兼容

**存储层**
- 业务模块通过 `from dqg.store import ...`，禁止直接 import `store.core`
- 业务层禁止写 raw SQL

**路径构建**
- Phase 产物路径通过 `state_machine.phase_dir()` / `phase_dir_by_id()` 构建
- 文件名通过 `constants.STRUCTURED_JSON_MAP` / `constants.REPORT_MAP` 获取

**重构纪律**
- 每次重构后必须跑 `pytest tests/ -q` 确认零破坏
- 移动文件时在旧位置留 facade，确认所有调用方迁移后再删除

### 输出目录结构
- 产物路径: `output/<project_id>/<phase_dir>/`
- 状态文件: `output/<project_id>/state.json`

### 质量保障体系
- finalize 时自动输出: 性能报告、Golden Sample 对比、规则执行率、结构化事实索引、需求版本追踪、评审链 prompt
- Bug 案例库 (`regression/failure-library/cases/`) 自动注入为 skill 反例
- 有效 critique 自动沉淀为 bug case，形成反馈飞轮

### 统一记忆层（MemoryLayer）
- 事实存储: REQ/BR/SE/GAP/OPEN → SQLite FTS5 索引
- 图片/文本/语义缓存 + 代码搜索 + 需求版本追踪 + 跨项目知识网络
- 用法: `from dqg.memory.memory_layer import MemoryLayer; mem = MemoryLayer(Path('output'))`

### 关键文件
- `dqg_starter.md` — AI IDE 入口 skill
- `SKILL.md` — Pipeline 路由器
- `skills/system-rules.md` — 通用规则（含 TMF 链路追踪）
- `skills/quality-judge.md` — LLM-as-Judge 评审 skill
- `skills/tech-design-generation.md` — Phase A.3 技术方案生成 skill（资深架构师 Agent）
- `skills/workflow/*.md` — 工作流定义
- `skills/knowledge-base-builder.md` — 知识库构建 skill
- `src/dqg/constants.py` — 全局常量（铁律：所有硬编码值的唯一来源）
- `src/dqg/core/state_machine.py` — Phase 状态机 + PHASE_DEFS
- `references/risk-and-exception-catalog.md` — 风险与异常分类目录（Java DDD+TMF）
- `regression/failure-library/cases/` — Bug 案例库（按 Phase 分类）

### Common Tasks → Files

| 要做什么 | 看哪里 |
|----------|--------|
| 加新 Phase / 改 Phase 流转 | `core/state_machine.py`（PHASE_DEFS）→ `constants.py`（PHASE_DIR_MAP）→ `skills/` 对应 .md |
| 加新 CLI 命令 | `commands/` 新建 .py → `core/cli.py` 注册 |
| 改 LLM 调用逻辑 | `agents/llm_backends.py` → `agents/agent.py` → `agents/adaptive_loop.py` |
| 改质量评审链 | `quality/judge.py` / `critique.py` / `review_chain.py` |
| 改 Bug 案例匹配 | `tracking/case_selector.py` → `tracking/bug_cases.py` |
| 改上下文加载/压缩 | `context/context_loader.py` → `context/chunk_processor.py` |
| 改存储 schema | `store/core.py`（DDL）→ `store.py`（facade） |
| 改缓存/索引 | `cache/fact_cache.py` / `image_cache.py` / `text_cache.py` / `semantic_cache.py` |
| 改性能统计 | `reporting/perf_tracker.py` → `reporting/telemetry.py` |
| 加新数据源 | `ingest/` 新建子目录 |
| 改常量/阈值 | `constants.py`（唯一来源） |

### 禁止事项
- 禁止在 Phase A/A.3/A.5/A.6 输出 UT/EUT
- 禁止自动 commit/push 代码
- 禁止编造不存在的接口、字段、逻辑
- 禁止一次性列出所有输入问题（必须逐步交互）

## 飞书文档抓取

```bash
python scripts/feishu_direct_ingest.py "<feishu_url>" -o output/<project_id>/phaseA
```

支持 docx 和多维表格（bitable）类型的 Wiki 节点。图片并发下载（8 workers），引用文档并发抓取（4 workers）。

## 多平台支持

| 工具 | 指令文件 |
|------|---------|
| Claude Code CLI | `CLAUDE.md` |
| OpenAI Codex CLI / opencode | `AGENTS.md`（本文件）|
| Google Gemini CLI | `GEMINI.md` |
| Cursor | `.cursor/rules/dqg.mdc` |
| IntelliJ IDEA | `AGENTS.md`（本文件）|

## 文档维护约定

- `Claude-Reflect Learnings` 由 `claude-reflect` 生成，禁止手工把本轮改动直接写进该区块
- 需要补充 learnings 时，先更新 `.claude/memory/` 源文件，再走生成流程刷新 `CLAUDE.md` / `AGENTS.md`

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

## Architecture

**项目类型**：CLI 框架 + AI Agent Pipeline
**主要语言**：Python 3.11+
**入口点**：`src/dqg/core/runner.py`（CLI）、`src/dqg/core/cli.py`（pyproject entry）、`dqg_starter.md`（AI IDE）

### 包结构
| 子包 | 职责 | 关键模块 |
|------|------|---------|
| `core/` | 状态机 + CLI 入口 + Profile | state_machine.py, runner.py, cli.py, profiles.py |
| `store/` | SQLite 统一存储（facade + 8 子模块） | core.py (schema), telemetry.py, experiments.py |
| `cache/` | FTS5 缓存/索引层 | fact_cache.py, image_cache.py, text_cache.py, semantic_cache.py, code_search.py |
| `memory/` | 记忆/知识层 | memory_layer.py, knowledge_network.py, version_tracker.py, wiki_layer.py |
| `agents/` | Multi-Agent 框架 | llm_backends.py, agent.py, agent_orchestrator.py, multi_agent.py, adaptive_loop.py |
| `quality/` | 质量评审链 | judge.py, critique.py, review_chain.py, golden_sample.py, rule_compliance.py |
| `tracking/` | Bug 案例 + 回归 + 实验 | bug_cases.py, bug_case_generator.py, case_selector.py, regression.py |
| `context/` | 上下文加载 + 分块压缩 | context_loader.py, chunk_processor.py, diff_context.py |
| `reporting/` | 性能/指标/可观测 | perf_tracker.py, telemetry.py, collect_metrics.py, observability.py |
| `ingest/` | 文档抓取（可扩展） | feishu/ (飞书特定), common.py, error_strategy.py |
| `media/` | 图片处理 | parse_images.py, image_preprocess.py |
| `services/` | 业务服务层 | phase_service.py, orchestrator.py |
| `commands/` | CLI 命令 | phase.py, query.py, review.py, agents.py |
| `schemas/` | Phase 数据契约 | phase_a.py, phase_a3.py, phase_a5.py ~ phase_d.py |

### 根目录工具模块
| 文件 | 职责 |
|------|------|
| `constants.py` | 全局常量（Phase 映射、路径、阈值、定价） |
| `json_utils.py` | 统一 JSON 操作 |
| `exceptions.py` | 异常层次 |
| `log.py` | 统一日志配置 |
| `path_utils.py` | 路径工具 |
| `text_utils.py` | 文本工具（中文分词、常量 re-export） |
| `store.py` | 存储层 facade（re-export store/ 子包） |
| `skill_tracker.py` | 质量追踪 facade（re-export quality/ + tracking/） |
| `agent_framework.py` | Agent 框架 facade（re-export agents/） |

### 数据目录
| 目录 | 职责 |
|------|------|
| `profiles/` | 技术栈 profile（每个含 profile.json + baseline.md） |
| `references/` | 通用模板 + 共享知识（risk-catalog、report-template 等） |
| `regression/` | Bug 案例库 + Golden Sample + 测试 fixtures |
| `skills/` | 7 个 Phase 的 skill prompt |
| `output/` | 项目产物目录 |

### 设计模式
- **状态机**：Phase 流转（not_started → in_progress → pending_review → approved），`core/state_machine.py`
- **Plugin 式 Skill**：每个 Phase 对应一个 .md skill 文件，执行时动态加载
- **SQLite 统一存储**：所有缓存/索引/遥测/状态共用一个 DB，FTS5 中文 n-gram 分词
- **Facade 模式**：大模块拆分后保留 facade re-export，保持向后兼容
- **Multi-Agent**：三阶段（prompt 隔离 → 独立 API → 自适应循环），6 家模型 14 个模型
- **测试**：pytest，`tests/` 目录

### 外部依赖
- **存储**：SQLite（内置，零部署）
- **LLM API**：Anthropic / OpenAI / Google Gemini / DeepSeek / Qwen / Moonshot（按需）
- **飞书 API**：文档抓取（larkkit，可选）
- **可视化**：Streamlit（dashboard，可选）

*最后更新：2026-04-08*
