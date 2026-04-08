# dev-quality-gate Roadmap

> 统一平台化规划文档（持续更新）

## 1. 规划目标

本路线图用于把 `dev-quality-gate` 从“可跑通流程的工具集合”推进到“可规模化复制的平台能力”。

核心目标：

1. 规则改动可回归、可度量、可告警
2. 技术栈切换可配置、可插拔、低接入成本
3. 报告与门禁标准化，可接 CI/PR 自动治理
4. 运营指标可持续沉淀，支持周维度经营分析

---

## 2. 状态图例

- `已完成`：已上线并通过测试/烟测  
- `进行中`：已实现核心能力，待扩大覆盖或接入  
- `规划中`：尚未实现，已定义触发条件与验收口径

---

## 3. 平台能力主线

## A. 回归基线与失败样例库

**定位**：解决“规则改动是否引入误报/漏报回归”。

**当前状态**：`已完成（v1）`

已落地：

- `dqg-regression run` 一键回放基线样例  
- 基线样例集：`rights-platform`、`mrs`、接口新增、重构样例  
- 失败样例库：`regression/cases/failure-library/`  
- 失败样例元数据：`trigger_condition / error_type / fix_strategy / regression_case`  
- 命令返回码门禁：任一回归失败返回非 0  
- 周趋势统计：`dqg-regression trend --period weekly`

验收结论（当前）：

- “每次规则改动必须通过失败样例回归”已具备技术基础  
- “漏报/误报趋势可量化（周维度）”已落地

后续增强（P1）：

- 扩充失败样例覆盖深度（按 Phase × error_type）
- 增加失败样例标签体系（严重级别、业务域、规则版本）

---

## B. 规则与基线 Profile 插件化

**定位**：解决“新项目接入需要改代码”。

**当前状态**：`已完成（v1）`

已落地：

- profile 注册：`java-ddd-tmf`、`go-service`
- `dqg-run --profile ...` 切换基线  
- Profile 自动注入上下文（baseline/risk/thresholds）  
- 各 Phase 自动产物：`_profile.json`、`_profile_context.md`  
- 报告模板统一包含 `PROFILE_CONTEXT`

验收结论（当前）：

- “新项目接入仅需选 profile + 输入源配置”已达成  
- “不改代码可切换至少 2 套基线”已达成

后续增强（P1）：

- 增加 profile schema 校验（发布前校验）  
- profile 版本化与兼容策略（如 `go-service@v2`）

---

## C. 可观测、趋势与告警

**定位**：解决“质量门禁结果不可运营”。

**当前状态**：`进行中`

已落地：

- 日报/周报：`dqg-observe report --period daily|weekly`  
- 指标仓：`observability/metrics_history.jsonl`  
- 告警规则：`BLOCK_SPIKE`、`PHASE_FAILURE_RATE`  
- Prometheus 快照导出  
- 周报聚合失败样例趋势（误报/漏报/边界/弱文档）  
- 新告警：`FAILURE_LIBRARY_REGRESSION`（失败样例回归退化）

仍需推进（P1）：

- 审计命中率、修复闭环时长口径  
- 告警噪声治理（误报率、阈值自适配）  
- 周报到治理动作的闭环（负责人、修复 SLA）

2026-04-08 进展补充：

- `estimate_tokens()` 已改为线性扫描，避免中文串反复 `replace()` 导致的 O(n^2) 估算开销
- Judge / Critique / Experiment 已切换为 relevance-matched bug case 注入，不再固定取前 N 条 open cases
- `agent-run` / `adaptive` / `perf_tracker` 已兼容 `_internal/` + `ingest/` 新布局，优先读取真实产物路径径
- `perf_tracker` 已为上下文/报告/结构化 JSON/skill 文件增加按路径 + mtime + size 的 token cache，避免重复统计
- finalize prompt 生成已去重，Judge / Critique / Review Chain 复用同一份构造结果
- `agent-run` / `adaptive` 已切换为有效上下文去重读取：当 `_upstream_context.md` 存在时，不再重复注入 `_profile_context.md` / `_bug_cases.md` / `_diff_context.md`
- `write_phase_profile_manifest()` 已切换为 relevance-matched bug case manifest；无相关案例时会清理陈旧 `_bug_cases.md`，避免旧案例残留注入
- `load_profile_context()` 已增加基于路径 + mtime 的进程内缓存，重复 Phase 执行不再反复全文读取 baseline / risk catalog
- `load_context()` 新增流式上下文写盘能力，`_upstream_context.md` 落盘不再先构造整块 `full_text`；同时改用轻量 `relevance_seed` 驱动 bug case relevance matching
- `load_context()` 已切换为 retrieval-first evidence pack：`_upstream_context.md` 输出固定为 Pack 概览 + 证据摘要 + 关键引用；Phase A 会优先使用当前输入证据，bug case relevance seed 会排除 profile / memory / 已注入 bug cases，避免空上下文误注入和重复放大
- `chunk_processor.py` 已为 `_split_large_chunk()` / `_compact_chunk()` 增加局部 token cache，重复段落与压缩中间态不再反复 `estimate_tokens()`
- Judge / Critique / Experiment 的 bug case relevance 输入已统一改为 excerpt/seed 模式，避免从报告、结构化 JSON、skill 全文中反复拼接大文本
- `judge` / `critique` / `experiment` 的 bug case relevance 输入已改为 excerpt/seed 复用，避免把报告、结构化 JSON、skill 全文直接喂给相关性匹配
- `judge` / `critique` / `experiment` 的 relevance 输入已改为 excerpt/seed 复用，避免把大文件全文直接塞进 bug case matching
- `adaptive` 的 multi-judge vote 已改为并行执行，支持 judge model 去重、单 Judge 失败容错和结果顺序稳定，降低串行投票等待时间
- `semantic_cache` / `MemoryLayer.search()` 已切到版本感知 cache namespace；`cache_invalidate()` 支持按 `project_id`、`result_type`、`cache_version` 精确失效
- `MemoryLayer.index_phase()` 已支持按关键输入签名增量索引；未变化跳过重建，变化后重建事实索引/知识节点，并联动清理项目级 fact search cache
- `adaptive_loop` 已复用 `Agent.query_cache`，重复 Worker/Judge/Fixer/Critique 路径可直接命中缓存，补齐应用层 LLM result cache 主执行链路
- FTS5 中文检索已改为边界感知分词 + identifier subtoken，fact/text/image/code 统一使用 MATCH builder 与轻量 post-filter，降低中文单字误命中
- Phase C `execute` 新增 `_internal/_weak_assert_context.{json,md}`，把 `assertNotNull` / `verify-only` / `assertThrows-only` 等 `WRONG_TARGET` 候选前置暴露给审计流程
- 架构级优化路线图已单列：`ARCHITECTURE_OPTIMIZATION_ROADMAP.md`，覆盖高/中/低优先级与两项 P0（应用层 LLM result cache、retrieval-first evidence pack）

---

## D. CI/PR 质量门禁集成

**定位**：解决“质量规则只在本地执行，无法组织级落地”。

**当前状态**：`规划中`

目标能力：

- CI 中执行 `dqg-regression run` 与关键 Phase 校验  
- PR 阶段输出结构化质量结论（通过/有风险/阻断）  
- 失败原因分层（内容质量 vs 报告规范）

建议落地顺序：

1. 本地脚本标准化（make target）
2. GitHub/GitLab CI 模板化
3. PR Comment 模板化输出
4. 阻断级规则灰度启用

验收标准：

- 主干分支规则改动必须经过失败样例回归  
- PR 可见门禁结果与关键证据链接  
- CI 失败可快速定位到具体 case/phase

---

## E. 报告规范与治理门禁

**定位**：解决“报告格式不一致导致治理成本上升”。

**当前状态**：`进行中（提醒模式）`

已落地：

- `finalize` 对缺失 `PROFILE_CONTEXT` 给出提醒

规划项（P1）：

- `--strict-profile-context` 严格模式  
- 默认提醒，不阻断；严格模式下阻断  
- 可接 CI 做报告规范门禁

触发条件：

1. 模板使用稳定（至少 3 类报告）
2. 提醒频繁出现，形成共性问题
3. 团队明确需要 CI 级规范收敛

---

## 4. 里程碑路线（统一）

### P0（已完成/可用）

- 2026-04-08：修复 bug case 相关性匹配的冗余 I/O，`bug_cases.py` 预载 `_input_excerpt` 后由 `case_selector.py` 复用；同时清理 `store.py` 兼容 facade 的 `_row_to_dict` 无意义自赋值
- 回归基线 + 失败样例库 + 周趋势
- Profile 插件化（2 套基线）
- 可观测日报/周报 + 基础告警
- 报告 `PROFILE_CONTEXT` 规范化产物
- 目录结构重构（`output/<project>/<phase>/`）
- 飞书抓取优化（图片/文档并发、bitable 支持）
- Bug 案例库（87 条，按 Phase 分类，相关性匹配注入）
- LLM-as-Judge 自动评审（1-5 Likert 量表，RAGAS rubric 标准）
- Self-Critique + RLAIF 融合闭环
- 规则级质量追踪 + 自动修复闭环
- 多平台支持（Claude Code / Codex / Gemini / Cursor / IntelliJ）
- SQLite 统一存储层
- Streamlit 可视化看板
- 增量分析模式（git diff）
- 异常矩阵扩展（Java DDD+TMF，364 行）
- Skill 自动迭代实验引擎（沙箱模式）
- `dqg init` 初始化 + 看板自动启动
- Judge/Critique 前置（finalize 前执行，不是 finalize 后）
- 推理日志（`_reasoning_log.md`）强制交付 + finalize 硬性校验
- 重跑防回退（产物数量减少自动告警）
- Golden Sample 标杆对比（finalize 时自动对比达标率）
- 规则执行率追踪（11 条规则逐条检测，持久化到 SQLite）
- Token 消耗追踪 + 性能报告（输入/输出明细、成本估算、改进建议）
- 性能报告 token 统计缓存（路径 + mtime + size，避免重复 I/O）
- 图片压缩（800px）+ 分级解析（board 深度/image 浅度）
- 图片语义缓存（SQLite FTS5 中文 n-gram 分词，后续引用不读图片）
- 文本语义缓存（按章节分段 FTS5 索引，按需检索替代读全文）
- 文档摘要自动生成（纯规则提取，零 LLM 调用，压缩 80%）
- 语义缓存（相同查询直接返回，零 token）
- 结构化事实索引（REQ/BR/SE/GAP/OPEN → FTS5）
- 需求版本追踪（Zep 时序模式，自动标记新增/修改/删除/过期）
- 跨项目知识网络（A-MEM 模式，自动建立跨项目相似链接）
- 统一记忆层 API（`MemoryLayer`，一个入口搜索事实/图片/文本/代码）
- `wiki_layer` 恢复并采用 excerpt/limit 策略，避免把 Phase A 文本和 `.dqg-wiki` 全文直接塞进 prompt
- 代码智能搜索（业务概念→代码关键词映射 + Java 结构索引 FTS5）
- 需求粒度标准（Story + AC 分层模型）
- BR 细节要求（禁止概括性描述，必须包含字段/枚举/校验/提示）
- 图片解析 P0 必做（状态机/流程图必须转 Mermaid）
- 所有 6 个 Phase skill 统一执行流程（证据采集→全量理解→产出→自检→Judge/Critique→修正→finalize）
- `.claude/commands/` + `.gemini/commands/` slash command 支持
- Multi-Agent Phase 1（Orchestrator + Worker/Judge/Critique 独立 prompt + DAG 并行调度）
- Multi-Agent Phase 2（模型无关 Agent Framework，Claude/DeepSeek/Qwen/Gemini/Kimi/Codex 自动 fallback，`dqg-run agent-run`）
- Multi-Agent Phase 3（自适应循环：Judge 不通过自动修正重试 + 多 Judge 投票取共识，`dqg-run adaptive`）

### P1（下一阶段）

已完成（本轮架构优化）：

- `adaptive` 多 Judge 并行投票（去重重复 model、单 Judge 失败容错、投票结果顺序稳定）
- 版本感知 cache namespace + 定向失效（`semantic_cache` / `MemoryLayer.search`）
- 增量索引 / 变更感知知识层（`MemoryLayer.index_phase` 跳过未变化重建，`finalize` 统一接入）

仍待推进：

- CI/PR 门禁模板化接入（GitHub Action）
- 飞书 Bot 通知（Phase 完成/失败推送）
- 失败样例库扩容与标签化
- 误报/漏报/命中率/闭环时长四类运营口径完善
- `--strict-profile-context` 灰度上线
- 团队聚合看板（跨项目 Phase 通过率、GAP 闭环率趋势）
- PyPI 发布（`pip install dev-quality-gate`）
- 断点续跑（Phase 失败后从断点继续）
- DAG Scheduler 增强（Phase 间自动并行执行，不只是生成 prompt）
- LSP 集成（代码智能，jedi/Java LSP）

### P2（平台化规模阶段）

- **DeepEval 集成** — 引入 DeepEval 作为自动化评分引擎，替代 prompt-based judge
- 代码 Embedding + 语义搜索（替代 FTS5 n-gram）
- 指标正式入库（Prometheus/ClickHouse）
- Dashboard 分层（管理视图/研发视图）
- 告警接 IM/值班链路
- 规则与 profile 的版本治理平台化
- VS Code / IntelliJ 插件（Phase 结果编辑器内高亮）
- 渐进式采用（支持只跑单个 Phase 的单个维度）

---

## 5. 依赖关系（跨主线）

1. C（可观测）依赖 A（失败样例库）提供高质量趋势源
2. D（CI/PR）依赖 A+B+E 的标准化产物
3. E（严格门禁）应晚于模板稳定，否则会影响接入效率
4. P2 的平台化投入，应以 P1 的真实使用数据为前置证据

---

## 6. 近期执行建议（未来 2-4 周）

1. 每周固定运行一次 `dqg-observe report --period weekly` 并复盘 failure library 趋势
2. 每次规则改动在合并前强制执行 `dqg-regression run`
3. 先选 1 条 CI 流水线试点接入，再逐步推广
4. 将告警命中项纳入周会闭环（责任人 + 截止时间）
