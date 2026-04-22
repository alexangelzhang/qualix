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
- Dashboard 打通：observe 告警入 SQLite，总览页合并展示，新增"可观测性"页面
- finalize 后自动触发 observe 日报更新，保持 dashboard 数据实时

2026-04-22 新增：

- 铁律三层强制执行机制：
  - 第一层：确定性检测（`report_quality_checks.py`，finalize handler order=55）— 来源标注/ID 格式/GAP 风险等级/OPEN 决策方/置信度/推理日志质量 6 项正则检测
  - 第二层：语义 guardrail（`semantic_guardrail.py`，`ReportSemanticGuardrail`）— BR 概括性描述/覆盖度虚高/跨 Phase 越权/P0 未闭环 4 项语义检测
  - 第三层：行为 hook（`git_safety_guard.py`，PreToolUse）— git push/force push/--no-verify 拦截
- 文档同步自动化（`doc_sync_check.py` + `completion_gate.py` 集成）— 按变更范围精准映射需要更新的文档
- RunStatus 5 值枚举（`runtime/result.py`）— ok/timeout/adapter_crashed/parse_failed/tainted，区分 infra failure 和 logic failure，infra failure 不计入 Judge 质量评分
- 图片 token 优化（`media/parse_images.py`）— 三层分级策略：<10KB 跳过 / 10-50KB 轻量描述 / >50KB 或流程图关键词精读，自动关联 browser_asset_manifest.json 获取 size
- Critique Gene/Capsule 反馈结晶（`quality/gene_store.py`）— 高置信度 Critique 提取为可复用评审基因（Gene），成功修正快照存为 Capsule，自动注入下游 Phase context
- Profile L0 压缩（`core/profiles.py`）— baseline + risk catalog 压缩为结构化元规则（标题/表格/强约束句），压缩比 ~50%，减少 context token 消耗
- Worker 经验结晶（`context/skill_crystal.py`）— 从高分执行（score>=4.0）提取成功模式，结晶为可复用模板注入后续同 Phase 执行
- DAG Preflight 增强（`runtime/preflight.py`）— 上游产物完整性检查（report + structured JSON 非空）+ 级联失败阻断（上游 tainted/parse_failed 时阻断下游），DAG 调度器每个 Phase 执行前自动运行
- 静默失败修复（`runtime/handlers_finalize.py`）— `_async_write_json` 和 `_emit_handler` 的 `except: pass` 改为 `log.debug` 记录失败原因，消除调试盲区

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
- `load_context()` 已切换为 retrieval-first evidence pack：`_upstream_context.md` 输出固定为 Pack 概览 + 证据摘要 + 关键引用；Phase Q01 会优先使用当前输入证据，bug case relevance seed 会排除 profile / memory / 已注入 bug cases，避免空上下文误注入和重复放大
- `chunk_processor.py` 已为 `_split_large_chunk()` / `_compact_chunk()` 增加局部 token cache，重复段落与压缩中间态不再反复 `estimate_tokens()`
- Judge / Critique / Experiment 的 bug case relevance 输入已统一改为 excerpt/seed 模式，避免从报告、结构化 JSON、skill 全文中反复拼接大文本
- `judge` / `critique` / `experiment` 的 bug case relevance 输入已改为 excerpt/seed 复用，避免把报告、结构化 JSON、skill 全文直接喂给相关性匹配
- `judge` / `critique` / `experiment` 的 relevance 输入已改为 excerpt/seed 复用，避免把大文件全文直接塞进 bug case matching
- `adaptive` 的 multi-judge vote 已改为并行执行，支持 judge model 去重、单 Judge 失败容错和结果顺序稳定，降低串行投票等待时间
- `semantic_cache` / `MemoryLayer.search()` 已切到版本感知 cache namespace；`cache_invalidate()` 支持按 `project_id`、`result_type`、`cache_version` 精确失效
- `MemoryLayer.index_phase()` 已支持按关键输入签名增量索引；未变化跳过重建，变化后重建事实索引/知识节点，并联动清理项目级 fact search cache
- `adaptive_loop` 已复用 `Agent.query_cache`，重复 Worker/Judge/Fixer/Critique 路径可直接命中缓存，补齐应用层 LLM result cache 主执行链路
- FTS5 中文检索已改为边界感知分词 + identifier subtoken，fact/text/image/code 统一使用 MATCH builder 与轻量 post-filter，降低中文单字误命中
- Phase Q06 `execute` 新增 `_internal/_weak_assert_context.{json,md}`，把 `assertNotNull` / `verify-only` / `assertThrows-only` 等 `WRONG_TARGET` 候选前置暴露给审计流程

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
- Bug 案例库（按 Phase 分类，相关性匹配注入，finalize 自动生成）
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
- `wiki_layer` 恢复并采用 excerpt/limit 策略，避免把 Phase Q01 文本和 `.dqg-wiki` 全文直接塞进 prompt
- 代码智能搜索（业务概念→代码关键词映射 + Java 结构索引 FTS5）
- 需求粒度标准（Story + AC 分层模型）
- BR 细节要求（禁止概括性描述，必须包含字段/枚举/校验/提示）
- 图片解析 P0 必做（状态机/流程图必须转 Mermaid）
- 所有 7 个 Phase skill 统一执行流程（证据采集→全量理解→产出→自检→Judge/Critique→修正→finalize）
- `.claude/commands/` + `.gemini/commands/` slash command 支持
- Multi-Agent Phase 1（Orchestrator + Worker/Judge/Critique 独立 prompt + DAG 并行调度）
- Multi-Agent Phase 2（模型无关 Agent Framework，Claude/DeepSeek/Qwen/Gemini/Kimi/Codex 自动 fallback，`dqg-run agent-run`）
- Multi-Agent Phase 3（自适应循环：Judge 不通过自动修正重试 + 多 Judge 投票取共识，`dqg-run adaptive`）

2026-04-08 新增：

- Phase 顺序重构：Q01 → Q02(可选) → Q03 → Q04 → Q05 → Q06 → Q07（先生成方案，再评审质量，最后审覆盖度）
- Phase Q02 技术方案生成（资深架构师 Agent，含 HLD+LLD+DTO+流程图+伪代码）
- 技术方案 AI 亲和性原则（完整到 AI 可直接编码和写单测）
- 技术方案完整性标准（参考飞书模板：接口协议清单+外部依赖+部署灰度+影响范围+可观测性）
- LLM Result Cache 100%（缓存键含 skill/rubric 签名 + 全局统计 + Preference 缓存）
- FTS5 中文分词 jieba 集成（词级分词+停用词过滤，降级兼容 n-gram）
- 弱断言检测 tree-sitter Java AST（链式调用/变量追踪/跨方法 Helper 分析/5种弱断言信号）
- 弱断言业务语义映射（断言与 Phase Q01 SE / Phase Q05 EUT 自动关联）
- DAG 并行调度器（`dqg-run dag`，Phase 间全自动并行执行，ThreadPoolExecutor）
- CLAUDE.md/AGENTS.md 职责分离（AGENTS.md 为通用知识单一来源，CLAUDE.md/GEMINI.md/.cursor 为适配层）
- SKIPPED 状态可满足依赖（可选 Phase 跳过后不阻塞下游）
- Phase Q02 schema 校验（`schemas/phase_a3.py`）

2026-04-09 新增：

- 跨项目知识自动注入（`phase_service.py` 在 execute 时调用 knowledge_network，历史 GAP/BUG/LESSON 自动注入 prompt）
- 案例相关性二级匹配（`case_selector.py` 同义词扩展，"幂等"↔"重复提交"↔"并发安全" 等语义等价词自动关联）
- 图片→Mermaid 验证闭环（VLM prompt 要求输出 Mermaid 代码+节点/边数量，`validate_mermaid.py` 自动校验结构完整性）
- Phase Q05 编译验证 gate（`compile_check.py`，finalize 前自动编译检查，失败则 BLOCKED，支持 Maven/Gradle/Go）
- Q04 覆盖度结构化映射表（`coverage_matrix.py`，从 Phase Q01 自动生成 REQ/BR/SE→技术设计映射矩阵，LLM 填充而非自由审计）
- 业务域变异测试推导（`business_mutations.py`，从 Phase Q01 SE 自动推导金额精度/状态机跳转/并发保护/空值注入等变异规则）
- Harness/Domain 分层 Phase 0（`PHASE_DEFS` 提取到 `phase_registry.py`，store schema 拆为 `_HARNESS_SCHEMA` + `_DOMAIN_SCHEMA`）
- Runtime Kernel Phase 0（`src/dqg/runtime/` 包：PhaseResult 结构化结果、EventType 生命周期事件、ExecutionContext 执行上下文、LifecycleRegistry handler 注册机制、execute/finalize sidecar 下沉为 11 个独立 handler）
- 跨 session 进度文件（`_progress.json`，Phase 级 + 项目级，finalize 后自动生成，记录执行摘要/关键数字/下一步建议）
- Session startup protocol（`session_startup.py`，标准化启动序列：读 state → 读 progress → 读 reasoning log → 输出 orientation summary）
- Task store + resume 基础设施（`task_store.py`，SQLite task_runs/task_events/task_checkpoints 表，支持崩溃恢复和进度查询）
- 动态 Judge grading criteria（`dynamic_rubric.py`，从 Phase Q01 SE 类型分布自动生成针对性评分维度，追加到静态 rubric）
- Blast radius 影响范围分析（`blast_radius.py`，tree-sitter/regex 调用图 + git diff → 受影响 callers/tests，注入 Phase Q06）
- Judge/Critique anti-rationalization table（8 条常见放水借口 + 反驳，防止虚高评分）
- 事实索引 confidence tagging（EXTRACTED/INFERRED/AMBIGUOUS 三级标注，REQ/BR=EXTRACTED，SE=INFERRED，GAP=INFERRED，OPEN=AMBIGUOUS）
- Phase skill progressive disclosure（`skill_loader.py`，`<!-- @include -->` 标记按需加载详细 rubric/规则，减少 adaptive loop token 消耗）
- Hyperedge 跨项目多实体关联（`knowledge_hyperedges` + `knowledge_hyperedge_members` 表，按业务域自动聚合 SE+BR+GAP 为多节点关联链，`build_business_hyperedges()` 在 index_phase 时自动构建）
- Phase B/D Judge rubric 补齐（B: EUT 覆盖/断言强度/可编译性/SE 追溯 4 维度；D: 发现有效率/需求对齐/严重级别/链路追踪 4 维度）
- 覆盖率门禁代码化（`coverage_gate.py`，解析 JaCoCo XML，Phase Q06 finalize 时硬性校验 line >= 80% / branch >= 80%）
- `commands/phase.py` 切换到 runtime 入口（cmd_execute/cmd_finalize 瘦身为薄壳，调用 runtime_execute/runtime_finalize + lifecycle handler）
- `dqg_starter.md` 全面更新（Phase DAG、Q02、推理日志、Judge/Critique 前置、sidecar 说明、覆盖率门禁）
- 新增模块测试补齐（compile_check/blast_radius/coverage_matrix/dynamic_rubric/coverage_gate 共 21 条测试）
- multi_agent.py judge prompt 统一到 quality/judge.py（消除 Phase-A-only 的独立实现，dag_scheduler 自动获得全 Phase rubric）
- cmd_auto 切换到 runtime 入口（execute/finalize handler 在 auto 模式下正常触发）
- adaptive_loop report_map 补齐 Q02/Q05/Q06/Q07（消除 fallback 到不存在文件的问题）
- skill_loader 接入 dag_scheduler（progressive disclosure 从死代码变为活代码）
- Skill 结构标准化（`SKILL_TEMPLATE.md` 模板 + 7 个 Phase skill 统一追加 Anti-Rationalization / Verification 节）
- Agent Persona 行为描述（Judge: 10 年质量负责人视角；Critique: 资深 QA 架构师视角）
- Phase Q01 假设前置（Step 0.5 Assumption Surfacing，列出假设等用户确认后再继续，防止 Agent 默默填充模糊需求）
- Phase Q05 Mock 优先级层级（Real > Fake > Stub > Mock）+ DAMP 原则（测试可读性优先）
- Phase Q07 变更大小门禁（~100 行好/~300 可接受/~1000 必须拆分）+ 评论严重级别标签（Critical/Important/Suggestion/Nit/FYI）
- 全局错误恢复协议（`error-recovery-protocol.md`，Stop-the-Line + Triage 五步法：Reproduce→Localize→Reduce→Fix→Guard）
- 上下文层级模型（`context-hierarchy.md`，五级金字塔 + 信任级别 + 行数阈值，统一所有 Phase 的上下文加载策略）
- Phase Q02 实施切片指导（垂直切片 + 风险优先 + XS/S/M/L/XL 任务分级 + Contract-first）
- Phase Q06 Judge 新增"场景覆盖质量"维度（测试数据是否覆盖多记录/边界值/枚举组合等真实故障路径）
- Phase Q06 覆盖状态新增 CONFLICT（团队有意的模式与审计标准冲突时，标记交人工裁决而非误判 WRONG_TARGET）
- Phase Q01 输出增加"边界约定"节（必须做/需确认/禁止做三级，下游 Phase 可引用）
- 下游→上游反馈触发机制（UPSTREAM_UPDATE_NEEDED 标记，下游发现需求问题时显式标记而非静默处理）
- 错误恢复协议增强（bisection 回归定位 + 不可复现 bug 四分支决策树：时序/环境/状态/随机）
- 范围外发现协议（Phase Q01/Q02/Q05 输出模板增加 Noticed But Not Touching 节）
- 上下文硬性行数阈值（2000 行/任务聚焦，5000 行降级触发，写入 system-rules.md）
- Phase Q07 依赖新增 5 问审查 + feature flag 检查
- Skill Factory（`skill_factory.py`，基于 bug case 库自动分析失败模式，生成 Anti-Rationalization 条目 + 红线规则补充建议，finalize 时自动触发，输出 `_skill_suggestions.md` 供人工 review）
- Bug Case Lesson 自动推断（`lesson_inference.py`，从 title/tags/error_type/source 字段推断缺失的 lesson，覆盖率从 26% 提升到 86%）
- 测试数据模式推导（`data_patterns.py`，从 Phase Q06 bug case 提取 8 种故障数据模式，Phase Q05/Q06 execute 时自动注入 `_data_patterns.md`，解决 Layer 3 场景 gap）
- Skill Evolution 技能自进化闭环（`skill_evolution.py`，生成具体 diff 而非建议文本 + 进化谱系记录 + 高置信度规则标记自动合入，借鉴 OpenSpace FIX/CAPTURED 模式）
- 代码语义检索增强（`code_semantic_search.py`，SE→Code 自动映射 + 概念映射动态扩展 + 调用链查询，零新依赖复用 FTS5+tree-sitter，Phase Q05/Q06/Q07 execute 时自动注入 `_se_code_mapping.md`）
- Skill 目录结构改造为 agentskills.io 标准（7 个 Phase skill 从扁平 .md 改为 `skills/<name>/SKILL.md` + `references/` 目录结构，所有 SKILL.md < 500 行，详细规则拆到 references/，旧路径保留 facade 兼容）
- Reasoning Sandwich（`phase_registry.py` 每个 Phase 增加 `reasoning_profile`，`context_loader.py` 按 execution level 动态调整 budget：high=100%/standard=60%，为推理留更多空间）
- Worker 内部拆分（`two_phase_worker.py`，Collector Agent 只做证据收集输出 `_evidence_pack.json`，Writer Agent 只看 evidence pack 不看原始文档，context 更干净）

2026-04-16 新增：

- Skill Evolution 全自动闭环（`skill_reflector.py`，adaptive loop 耗尽后触发 Reflect→Persist→Cluster→Write pipeline，v1 仅 SKILL_RULE 可自动合并，KNOWLEDGE/CONTEXT/SCHEMA 降级人审）
- Anti-Rationalization 运行时强制（`rationalization_guard.py`，两层检测：关键词正则扫描 + LLM 确认，Judge 放水时自动拦截并重审，预算耗尽标记 GUARD_EXHAUSTED 降级手动 judge）
- JudgeRunner 统一 Judge 执行（`judge_runner.py`，canonical schema 线兼容现有 `_judge_result.json` 消费方，primary→fallback 模型链，structured output 硬约束）
- LLM Backend 结构化输出（`llm_backends.py` 新增 `chat_structured()` → `StructuredChatResult(parsed, raw_text, provider_meta)`，OpenAI 兼容后端支持 `response_format=json_object`）
- Adaptive Loop 集成升级（`_run_single_judge()` 收口为 JudgeRunner thin wrapper，Guard 按 round 拦截 primary judge，`judge_health_check()` 区分 SEMANTIC_FAIL vs INFRA_FAILURE）
- resolve_worker_prompt() 统一 skill 解析入口（`skill_loader.py`，以 PHASE_DEFS 为主，所有生产调用方迁移：commands/agents.py + dag_scheduler.py）
- Phase 报告章节 contract（`phase_registry.py` 新增 `required_report_sections` 含别名归一，`phase_contract.py` 新增 `check_report_structure()` 模糊匹配校验）
- Eval-Driven 量化质量基线（`eval_baseline.py`，每个 Phase 定义固定评估指标，finalize 自动计算并对比历史基线，指标退化超 5% 触发 WARNING）
- Phase Contract 执行合同（`phase_contract.py`，execute 时自动生成 done_definition + verification_targets + evidence_refs + hard_checks，Judge 按 contract 逐条打分）
- Verification Bundle 统一验证包（`verification_bundle.py`，finalize 时收集所有自动化验证结果到 `_verification_bundle.json`，Judge 先看确定性证据再做语义判断）
- Context Compressor 迭代摘要（`context_compressor.py`，tool result 裁剪 + 结构化摘要 Goal/Progress/Decisions/Next Steps + 增量更新 + tool_call 孤儿修复）
- Memory on_pre_compress 钩子（`compress_hooks.py`，压缩前提取已修复问题/已确认决策/评分趋势到持久化存储，防止 adaptive loop 信息丢失）
- 多凭证轮转（`credential_pool.py`，多 API key 配置 + 429 自动轮转 + least_used 策略 + 冷却机制）
- Preflight 增强（`preflight.py`，adaptive/dag 每轮预检：checkpoint 恢复 + 产物完整性 + 依赖检查 + contract 存在性）
- Harness Ablation Matrix（`harness_ablation.py`，24 个组件注册表 + compact/full/review-heavy 三种 profile + 成本估算 + ablation 报告）
- DeepEval 评分校准层（`score_calibration.py`，Judge 评分一致性检测：DQG Judge vs DeepEval GEval 独立打分，drift > 1.0 触发告警；评分趋势监控：通胀/通缩检测）
- 断线修复：DAG scheduler 接入 runtime（execute/finalize handler 在 dag 模式下正常触发）
- 断线修复：score_calibration 注册为 finalize handler（order=95，自动触发一致性检测+趋势监控）
- 断线修复：session_startup 接入 CLI startup 命令（orientation 输出到 stderr，不影响 JSON stdout）
- 断线修复：task_store 接入 adaptive_loop + dag_scheduler（create_task_run 启动时、save_checkpoint 每轮/每批次、complete_task_run 结束时，支持崩溃恢复）

2026-04-17 新增（学术研究驱动优化，参考 2603.00539/2601.19929/2501.04810/2410.21798/2501.18160）：

- 增量覆盖率分析（`coverage_gate.py` 新增 `parse_jacoco_per_file()` + `compute_incremental_coverage()`，只对 blast radius 内文件计算覆盖率变化，其余继承全量结果，Phase Q06 finalize 优先增量模式）
- LLM Overcorrection 对策（`rationalization_guard.py` 新增 `OvercorrectionGuard`，反向检测 Judge 过严误报：关键词扫描 + FAIL 无证据行号检测；`phase_contract.py` Judge 规则新增 evidence_lines 硬性要求，FAIL 缺行号降级为 INSUFFICIENT_EVIDENCE）
- TREEFRAG 代码骨架压缩（`code_skeleton.py`，tree-sitter Java AST 提取类签名+方法签名+字段+注解，省略方法体；Oracle 标注按需展开 SE 关联方法；regex fallback 零依赖；典型压缩比 10:1~18:1）
- Demand-driven 代码路径追踪（`demand_trace.py`，从 SE→Code 映射提取入口方法，复用 blast_radius 调用图正向 BFS 追踪被调用方，与 blast_radius 交叉分析输出置信度）
- Requirements Smell 检测（`requirement_smell.py`，纯规则零 LLM：5 类异味 VAGUE/INCOMPLETE/SUBJECTIVE/UNBOUNDED/CONTRADICTORY，输出 `_requirement_smells.json`，与 confidence tagging AMBIGUOUS 衔接）
- 需求层级图 GAP 检测（`requirement_graph.py`，networkx DiGraph 构建 REQ→BR→SE 依赖图，自动检测 UNCOVERED_BR/ORPHAN_SE/ISOLATED_REQ/DANGLING_GAP/DANGLING_OPEN 五类异常，输出覆盖率汇总）
- Verification Bundle 新增 incremental_coverage 检查项（blast radius 内文件的增量行/分支覆盖率）
- 常量新增 OVERCORRECTION_PATTERNS（7 条 Judge 过严信号正则）

2026-04-11 新增（Hermes Agent 借鉴 + 架构升级）：

- **安全模块**：`security/content_scanner.py`（Memory/Wiki 写入安全扫描：prompt injection + 凭证泄露 + 不可见 unicode + 状态篡改）+ `security/tool_permissions.py`（Agent 工具权限白名单：Worker 全部 / Judge 只读 / Critique 可写不可委派）
- **spawn_subagent 安全**：深度限制 MAX_DEPTH=2 + 返回值截断 16k 字符（可配置）
- **性能优化**：Tool output pruning（旧工具返回值替换占位符）+ Frozen Snapshot（Adaptive Loop system prompt 不变保护 prefix cache）+ 按 Phase 配置模型等级（strong/standard → MODEL_TIER 映射）
- **Context 压缩**：跨 Phase 结构化摘要模板（ID 级摘要替代全文）+ Facts 数量监控（超 5000 阈值自动降级为摘要模式）
- **Trajectory Compressor**：`quality/trajectory.py`（压缩 Agent 执行轨迹为 JSONL，保护首尾 turn，压缩中间 tool call）
- **AutoHarness finalize**：`quality/auto_checks.py`（从 Pydantic schema + phase_registry 自动推导校验：schema 合规 / 交叉引用 / 严重等级 / RSM 覆盖率）
- **行为指纹回归**：`quality/behavioral_fingerprint.py`（从 trajectory 提取工具调用模式 / ID 数量 / 输出长度，统计分布替代 binary diff，PASS/FAIL/INCONCLUSIVE 三态判定）
- **batch_query 工具**：一次提交多个 search/wiki 查询，O(N)→O(1) token overhead
- **Memory 防污染**：`memory/memory_filter.py`（条目按 global/project 标签分级，Phase Q01 只注入 global，注入时加免责声明）+ Wiki 读取加不可靠提示 + 写入加来源元数据
- **Worker 结构化优先**：输出以 JSON 为主，md 从 JSON 自动渲染（`reporting/render.py`），JSON 是 source of truth
- **Judge 升级**：deterministic checker（auto_checks）先跑 → 结果作为 evidence 注入 LLM → LLM 只负责语义判断（需求完整性/逻辑一致性/可实现性/风险识别）
- **Critique 可执行反馈**：`schemas/critique_feedback.py`（target_id + action + patch + confidence + evidence_source），低置信度自动过滤，生成 `_critique_instructions.md` 供 Worker 消费
- **RSM 全局语义模型**：`schemas/rsm.py`（RequirementLifecycle 跨 Phase 追踪 + CoverageReport 6 指标 + 可写数据总线 apply_mutations + 持久化 `_rsm.json`）
- **闭环1 Critique→RSM 回流**：Critique 的 add/modify/delete 反馈自动 apply 到 RSM，下游 Phase 感知变化
- **闭环2 Coverage Gap→自动补充**：finalize 发现覆盖率缺口时生成 `_coverage_gap_tasks.json`，列出需补充的具体 ID 和目标 Phase
- **闭环3 Memory→RSM 进化**：`memory/rsm_patterns.py`（从多项目 RSM 提取高频 GAP 模式，沉淀为 global Memory，新项目 Phase Q01 自动注入检查清单）
- 测试：296 passed（从 238 新增 58 个），零破坏

### P1（下一阶段）

已完成（本轮架构优化）：

- `adaptive` 多 Judge 并行投票（去重重复 model、单 Judge 失败容错、投票结果顺序稳定）
- 版本感知 cache namespace + 定向失效（`semantic_cache` / `MemoryLayer.search`）
- 增量索引 / 变更感知知识层（`MemoryLayer.index_phase` 跳过未变化重建，`finalize` 统一接入）
- DAG Scheduler 增强（`dqg-run dag`，Phase 间全自动并行执行 + `--plan` 预览）
- LLM Result Cache 完善（缓存键含 skill/rubric 签名、全局统计、Preference 缓存）
- FTS5 中文分词 jieba 集成（词级分词 + 停用词过滤）
- 弱断言 tree-sitter Java AST（跨方法 Helper 分析 + 业务语义映射）
- 增量覆盖率分析（blast_radius + coverage_gate 联动，Phase Q06 finalize 优先增量模式）
- LLM Overcorrection 对策（OvercorrectionGuard 反向检测 + evidence_lines 硬性要求）
- TREEFRAG 代码骨架压缩 + Oracle 标注（code_skeleton.py，tree-sitter/regex 双模式）
- Demand-driven 代码路径追踪（demand_trace.py，SE→入口方法→调用链→审查集合）

仍待推进：

- Task store + resume/background runner（SQLite task_runs/task_events/task_checkpoints 表已建，CLI `dqg-run task list/resume` 待接入）
- CI/PR 门禁模板化接入（GitHub Action）
- 飞书 Bot 通知（Phase 完成/失败推送）
- 失败样例库扩容与标签化
- 误报/漏报/命中率/闭环时长四类运营口径完善
- `--strict-profile-context` 灰度上线
- 团队聚合看板（跨项目 Phase 通过率、GAP 闭环率趋势）
- PyPI 发布（`pip install dev-quality-gate`）
- 断点续跑（Phase 失败后从断点继续）
- LSP 集成（代码智能，jedi/Java LSP）
- FTS5 自定义 tokenizer（让 SQLite 原生使用 jieba 分词，当前是应用层分词后写入）
- ~~Requirements Smell 检测接入 Phase Q01 execute~~ → 已完成：`handle_requirement_smell` 注册为 execute handler（order=3），Phase Q01 execute 时自动运行
- ~~需求层级图 GAP 检测接入 Phase Q01 finalize~~ → 已完成：`handle_requirement_graph` 注册为 finalize handler（order=63），结果追加到 verification_bundle
- ~~TREEFRAG + Demand Trace 接入 Phase Q07 execute~~ → 已完成：`handle_demand_trace`（order=75）+ `handle_code_skeleton`（order=80）注册为 execute handler，OvercorrectionGuard 接入 adaptive_loop judge pipeline

### P2（平台化规模阶段）

- **Harness/Domain 分层 Phase 1** — 定义 `HarnessApp` 协议（provider/hooks/task_runner/output_protocol/session_resume），Domain 层通过注册而非 import 接入 Harness
- **Harness/Domain 分层 Phase 2** — `context_loader.py` 的 phase-specific 分支改为 Domain 层注册的 context_policy；`multi_agent.py` 的 prompt 模板改为 Domain 层提供；`row_to_dict` 的 JSON 字段列表改为 schema 驱动
- **DeepEval 集成** — ~~引入 DeepEval 作为自动化评分引擎，替代 prompt-based judge~~ → 已完成：作为评分校准层（一致性检测 + 趋势监控），不替代 Judge
- ~~代码 Embedding + 语义搜索（替代 FTS5 n-gram）~~ → 已完成：`code_semantic_search.py` 基于 FTS5 + 概念映射 + 调用链实现，零新依赖
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

---

## 7. 架构级优化（原 ARCHITECTURE_OPTIMIZATION_ROADMAP.md，已合并）

> 面向大量文档、知识库、代码仓库和图片输入场景的架构级优化。
> 目标：减少重复 I/O、降低 prompt token 浪费、提升证据相关性和执行稳定性。

### 优化方向总表

| 优先级 | 方向 | 状态 | 收益 |
|--------|------|------|------|
| P0 | 应用层 LLM result cache | **已完成(100%)** | 降低重复 LLM 调用，缓存键含 skill/rubric 签名，全局统计，Judge/Critique/Preference 全覆盖 |
| P0 | retrieval-first evidence pack | **已完成(95%)** | evidence pack schema（概览+摘要+关键引用），Phase Q01 当前输入证据与 bug case 去重 |
| 高 | FTS5 中文分词完善 | **已完成(85%)** | jieba 词级分词+停用词+bigram 补充召回，降级兼容 n-gram。待完善：FTS5 自定义 tokenizer |
| 高 | 弱断言检测 | **已完成(95%)** | tree-sitter Java AST 解析+跨方法 Helper 分析+业务语义映射(SE/EUT)。待完善：多语言支持 |
| 高 | DAG 并行调度器 | **已完成(100%)** | `dqg-run dag` 端到端并行执行，ThreadPoolExecutor，支持 --skip/--max-parallel/--plan |
| 中 | 证据与结果的可观测性闭环 | 进行中 | 缓存命中率/证据包大小/上下文 token/LLM 调用次数统一指标 |
| 低 | Prompt 细节和文档治理 | 规划中 | 统一提示词风格、报告模板、引用格式 |

### 落地原则

1. 缓存失效：只要输入证据变更就强制失效（文件 mtime+size 签名）
2. 证据优先级：结构化事实 > 相关摘录 > 摘要 > 全文
3. 检索兜底：召回不足时允许回退到更宽松的摘要层，但不直接回全文
4. 渐进落地：先覆盖最频繁的应用路径，每次落地配命中率/token 变化/调用次数三类指标

*最后更新：2026-04-22*

---

## 8. PhaseGuardrail 统一质量门控

> 借鉴 Agent SDK Guardrail 模式，将 DQG 三层检查统一为 PhaseGuardrail 接口。

### 短期（已完成）

| 项目 | 状态 | 说明 |
|------|------|------|
| PhaseGuardrail 基类 + GuardrailResult | **已完成** | `quality/guardrail.py`，支持 BLOCKED/WARNING/INFO 三级 |
| 三层检查包装 | **已完成** | `quality/guardrail_impl.py`：FinalizeChecksGuardrail / PhaseConstraintsGuardrail / RuleComplianceGuardrail |
| 并发执行 + 结果持久化 | **已完成** | `run_guardrails()` 支持 ThreadPoolExecutor 并发，结果写入 `_guardrail_results.json` |
| 接入 runtime_finalize | **已完成** | finalize handler 执行后统一跑 guardrail，不阻断主流程 |

### 长期（规划中，依赖 Agent SDK 迁移）

| 项目 | 触发条件 | 说明 |
|------|---------|------|
| Agent SDK 迁移 | DQG 需要多 agent 协作时 | 每个 Phase 变成一个 Agent，用 AgentHooks 做前后置检查 |
| RunHooks 全局 tracing | 迁移后 | 替代现有 telemetry/observability 散装逻辑，统一 tracing/cost 统计 |
| AgentHooks 单 Phase 检查 | 迁移后 | 替代 sidecar handler，独立测试，层级区分 |
| Guardrail 装饰器 | 迁移后 | `@input_guardrail` / `@output_guardrail` 直接挂在 Agent 上，`run_in_parallel=True` 不增加延迟 |
| tripwire 即时终止 | 迁移后 | `tripwire_triggered=True` 立即抛异常终止 agent 执行，替代现有 BLOCKED 检查 |

---

## 9. 并行 Phase 调度

> 独立 Phase 并行执行，缩短 pipeline 端到端耗时。

### 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| DAG 调度器 | **已完成** | `agents/dag_scheduler.py`，ThreadPoolExecutor 并行，`dqg-run dag` 命令 |
| Orchestrator 并行派发指令 | **已完成** | `dqg_starter.md` 步骤二新增并行调度规则，Orchestrator 同时派发多个 SubAgent |
| 并行安全保证 | **已完成** | 各 Phase 写不同子目录不冲突，finalize 串行保护 state.json |

### 规划中

| 项目 | 触发条件 | 说明 |
|------|---------|------|
| Git Worktree 隔离 | Q05/Q07 需要代码仓库时 | 每个并行 Phase 在独立 worktree 执行，避免代码文件冲突 |
| Agent Teams 集成 | Claude Code Agent Teams GA 后 | 替代手动多 SubAgent 派发，用 Team Lead + Teammate 模型 |

*最后更新：2026-04-22*
