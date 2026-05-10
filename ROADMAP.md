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

- profile 注册：`java-ddd-tmf`、`go-service`、`typescript-service`
- `dqg-run --profile ...` 切换基线  
- Profile 自动注入上下文（baseline/risk/thresholds）  
- 各 Phase 自动产物：`_profile.json`、`_profile_context.md`  
- 报告模板统一包含 `PROFILE_CONTEXT`
- profile schema 校验：`dqg-run doctor` 校验必填字段、SemVer、语言、路径和阈值范围
- profile 版本字段：内置 profile 显式声明 `version: 1.0.0`，新增 profile 默认兼容 `1.0.0`

验收结论（当前）：

- “新项目接入仅需选 profile + 输入源配置”已达成  
- “不改代码可切换至少 2 套基线”已达成

后续增强（P1）：

- profile 版本化选择器与兼容策略（如 `go-service@v2`）
- profile 变更影响分析接入 CI/PR 门禁

---

## C. 可观测、趋势与告警

**定位**：解决"质量门禁结果不可运营"。

> 评分体系全貌（T1-T8 共 ~64 个组件）见 [`docs/evaluation-tiers.md`](docs/evaluation-tiers.md)

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
- Critique Gene/Capsule 反馈结晶（`quality/regression/gene_store.py`）— 高置信度 Critique 提取为可复用评审基因（Gene），成功修正快照存为 Capsule，自动注入下游 Phase context
- Profile L0 压缩（`core/profiles.py`）— baseline + risk catalog 压缩为结构化元规则（标题/表格/强约束句），压缩比 ~50%，减少 context token 消耗
- Worker 经验结晶（`context/skill_crystal.py`）— 从高分执行（score>=4.0）提取成功模式，结晶为可复用模板注入后续同 Phase 执行
- DAG Preflight 增强（`runtime/preflight.py`）— 上游产物完整性检查（report + structured JSON 非空）+ 级联失败阻断（上游 tainted/parse_failed 时阻断下游），DAG 调度器每个 Phase 执行前自动运行
- 静默失败修复（`runtime/handlers/handlers_finalize.py`）— `_async_write_json` 和 `_emit_handler` 的 `except: pass` 改为 `log.debug` 记录失败原因，消除调试盲区
- CLI 命令整合 — 砍掉 4 个孤儿 entry point（dqg-orchestrate/dqg-metrics/dqg-observe/dqg-regression），收编为 `dqg-run` 子命令（metrics/observe/regression）；统一 Phase ID help 文本为 Q01-Q07；`dqg version` 去重委托 setup.py
- 增量上下文检测（`context/loading/file_snapshot.py`）— sha256 + mtime 快照比对，上游 Phase 产物未变更时跳过重读，减少 DAG 模式和重跑场景的 IO 开销
- 异构检测层（`runtime/handlers/handlers_detection.py`）— 四个 finalize handler：弱断言 gate（Q05 high-risk≥1 BLOCKED 左移卡控 / Q06 WARNING）、Q05 弱断言扫描（从 structured JSON 提取测试文件并生成 _weak_assert_context.json）、Mock 巧合正确检测（Q05 coincidence_hits BLOCKED / Q06 WARNING）、AI 产出标记（git blame + Co-Authored-By 推断代码来源）；EUT then 字段模糊检测（schema validator 拒绝"验证成功"等模糊描述，要求包含具体断言或值）
- Skill Evolution 全自动闭环（`tracking/skill_auto_merge.py`）— 高置信度规则（3+ case 支撑）自动合入 SKILL.md + holdout 验证 + overfitting 自动 revert；低置信度仍走 HUMAN_REVIEW；`SKILL_AUTO_MERGE_ENABLED` 全局开关

2026-04-24 新增（卡控机制审计 Phase 1 — 堵漏洞）：

- Handler required/optional 分级（`lifecycle.py`）— required handler 失败→BLOCKED 阻断 finalize，optional handler 失败→WARNING 继续执行；依赖死锁时报错而非静默降级为 order 排序
- Phase Contract 不可绕过（`phase.py`）— `--force` 无法绕过 Phase Contract 硬约束，blocking violation 必须修复后重新 finalize
- 指标解析失败视为约束失败（`phase_constraints.py`）— `_resolve_metric` 返回 None 时记录 WARNING 并生成 violation（reason=metric_resolve_failed），不再静默跳过
- Q01/Q02/Q05 Phase Contract 补齐（`phase_constraints.py`）— Q01 至少 1 条 REQ、Q02 至少 1 条需求→技术映射、Q05 至少 1 条 EUT
- Schema 校验 fail-closed（`schemas/__init__.py`）— 产物目录/文件不存在时返回错误列表而非 None，消除 fail-open 漏洞
- Auto-Judge gate_checklist 动态判定（`judge.py`）— 含 CRITICAL/blocker/阻断关键词的 checklist 项在有 critical 问题时标记 failed；precision/recall 根据 critical_count 和 score 动态计算
- 全 Phase core_arrays 补齐（`handlers_flow_integrity.py`）— Q02/Q04/Q05/Q06 加入空数组检查；critique closure 从 HIGH 升级为 CRITICAL
- Critique 依赖链断裂检测（`handlers_finalize.py`）— critique prompt 写入失败时标记 BLOCKED；review_chain handler 标记为 required
- flow_integrity handler 标记为 required — pre/post 两阶段检查失败均阻断 finalize

2026-04-24 新增（卡控机制审计 Phase 2 — GateVerdict 统一卡控层）：

- GateVerdict 统一卡控层（`runtime/gate_verdict.py`）— CheckItem + GateVerdict 数据类，HARD/SOFT 二级分类，所有检查汇入单一 verdict
- `runtime_finalize()` 末尾汇总 handler errors + guardrail + phase_constraints → `_gate_verdict.json`
- `cmd_approve()` 优先读 `_gate_verdict.json` 做决策，HARD 不可绕过，SOFT 可 `--force`，fallback 到旧逻辑
- 修复断裂点 1: Guardrail 结果接入 verdict（BLOCKED→HARD, WARNING→SOFT）
- 修复断裂点 2: finalize 时执行 Phase Constraints 并写入 verdict
- 多语言无关设计：通过 `source` 字段区分检查来源，不绑定具体语言

2026-05-07 新增（GateVerdict 上游产物哈希检测）：

- `GateVerdict.upstream_hashes`（`runtime/gate_verdict.py`）— finalize 时记录依赖的上游产物文件 MD5，`is_stale()` 方法检测哈希变化
- `check_cross_phase_refs` 返回值扩展为 `tuple[list[str], dict[str, str]]`，第二个元素为实际读取的文件路径→MD5 哈希字典
- `cmd_startup` stale 检测（`commands/startup_fast.py`）— `pending_review` Phase 自动检测上游产物是否变更，stale 时 menu item 标注 `stale: true` 并追加 comment 提示重新 finalize
- 解决问题：上游 Phase 产物修补后，下游 Phase 的旧 finalize 校验结果不再误报为有效

2026-05-09 新增（系统健康报告 T1–T12 落地）：

- T3 — `validate_eut_id_subset`（`quality/checks/cross_phase_check.py`）拦截 Q06 审计 Q05 不存在的 EUT 编号（phantom EUT），接入 `finalize_checks`
- T5 — Q05 结构合规 validator（`quality/checks/q05_structure_checks.py`）覆盖 mock_wrong / mock_phantom_method / eut_missing_se / wrong_directory 四类失败，compile_fail 仍由 `test_execution_gate` 兜底
- T6 — Q05 生成范式三步改造（`references/q05-three-step-paradigm.md` + SKILL 三步节）+ `Q05BranchCoverageGuardrail`（`quality/guardrail/q05_branch_coverage.py`），分支覆盖校验挂入 `get_phase_guardrails("Q05")`
- T7 — EnumSource 统一枚举源（`context/enum_contract.py::render_enum_contract_prefix`），在 `skill_loader.load_skill_progressive` 和 `agents/multi_agent.py` prompt 装配时自动注入 `ENUM_CONTRACT` 前缀节，与 schema 同源
- T8 — Schema↔Prompt 一致性 CI（`scripts/check_schema_prompt_sync.py`），挂入 `.pre-commit-config.yaml` 的 pre-commit hook
- T9 — Guard 精度周报（`reporting/guard_precision_report.py`）+ `dqg-run observe guard-precision` 命令 + finalize 后自动刷新
- T10 — Failure → Reflector 自动回流（`tracking/lesson_inference.py` 扩展 + `scripts/backfill_failure_case_lessons.py`），新采集 case 自动写 lesson
- T11 — `RationalizationProbeGuardrail`（`quality/guardrail/rationalization_probe.py`）字段级拦截合理化话术，挂入 Q03/Q06 的 `get_phase_guardrails`
- 状态跟踪见 `ISSUE.md §2026-05-09`：T1-T11 代码 done、验收 todo；T6/T12 阻塞 verified 待回写重跑数据

2026-05-10 新增（T14 AC 3 finalize 诊断收尾）：

- Adaptive loop schema 反馈回路 AC 3 收尾（`agents/adaptive_loop.py::_write_summary` + `runtime/phase_runtime.py::runtime_finalize`）— `_adaptive_summary.json` 新增 `adaptive_loop_schema_unresolved` + `adaptive_loop_last_schema_errors` 字段，finalize 读取后若最后一轮仍有 schema 错误，追加 warning + emit `VALIDATION_COMPLETED` 事件，明确区分"adaptive loop 跑完仍未修复"与"手工提交产物首次校验失败"
- 新增 2 条单测覆盖（`tests/test_adaptive_schema_feedback_t14.py`）：最后一轮有 errors → unresolved=True；早期轮有 errors 但最后一轮清空 → unresolved=False

2026-05-10 新增（Anti-Rationalization Guard 结构化 telemetry）：

- Guard telemetry 落盘（`quality/judge/guard_telemetry.py`）— `log_guard_event` 把 LAYER1_HIT / REJUDGE_PASSED / GUARD_EXHAUSTED 事件 append 到 `_internal/_rationalization_guard.jsonl`；`save_guard_pair` 把 block 触发的 before/after Judge `raw_output` 存为独立 pair JSON（`_internal/_rationalization_pairs/`），作为后续 precision 评估原料
- `multi_judge_vote` guard 块抽出（`agents/judge_vote_guards.py`）— `apply_rationalization_guard` / `apply_overcorrection_guard` 封装重审预算、telemetry 调用和 HARD_BLOCK 终态，`judge_vote.py` 回到 400 行内
- Guard 精度周报扩容（`reporting/guard_precision_report.py`）— 除原有 `_guardrail_results.json` 聚合外，新扫 `_rationalization_guard.jsonl` 并按 `rationalization_guard` / `overcorrection_guard` 分桶，表格新增 `triggered` 列
- 测试：`tests/test_guard_telemetry.py` 7 条（含并发 append + 失败静默 + roundtrip）+ `tests/test_guard_precision_report.py` 新增 3 条（事件聚合 / 损坏 jsonl 容错 / markdown 新列）
- **精度闭环待推进**：见本节"仍需推进（P1）"的 Anti-Rationalization Guard 精度评估三层规划

2026-05-10 新增（Skill Evolution absorb 闭环补强）：

- `apply_to_skill_file` 重写（`tracking/skill_auto_merge.py`）— 引入 `MarkdownSectionEditor` regex-based heading 扫描（跳过围栏代码块）+ `ApplyResult` 数据类（applied/inserted/skipped/rendered_diff）+ 幂等检查 + `dry_run` 模式 + 去掉 `rule_text[:60]` 截断 bug
- `verify_with_holdout` 关 fail-open — 异常 / `holdout_ready=False` 默认拒绝 merge（之前任何异常都返回 True 放行）；保留 `allow_fail_open=True` 作为 holdout 基础设施未就绪时的 escape hatch
- `validate_against_holdout` 增强（`quality/eval/eval_holdout.py`）— 新增 `holdout_ready` / `holdout_hit_rate` / `distribution_divergence` / `decision_reason` 字段；overfitting_signal 三条件触发（coverage_gap / root_cause L1 分布差 / hit_rate）
- `SkillReflector.write()` 接新 `ApplyResult` 契约 — `WriteResult` 新增 `skipped_duplicates` / `inserted_entries` / `rendered_diff`；新增 `NOOP_DEDUPED` 模式（全部建议被幂等检查跳过时不触发 holdout 节省）；`_write_evolution_trace` 展示幂等跳过列表和 diff
- 4 个新阈值常量（`constants.py`）：`SKILL_EVO_HOLDOUT_MIN_CASES=3` / `MIN_WITH_LESSON=2` / `DIST_DIVERGENCE_THRESHOLD=0.3` / `HIT_RATE_MIN=0.3`
- 测试：`tests/test_skill_auto_merge.py` 18 条（Editor / 幂等 / dry_run / 长规则 / fail-open 开关）+ `tests/test_eval_holdout.py` 9 条（三触发条件各一条 + 分布 L1 差基础用例 + holdout_ready 边界）+ `tests/test_skill_reflector.py` 新增 4 条（NOOP_DEDUPED / REVERTED / AUTO_APPLY diff 字段 / end-to-end reflect_and_write 映射）
- **真正的 Phase Pipeline 回放 ReplayExecutor 仍是 gap**：见本节"仍需推进（P1）"新增条目

2026-04-27 新增（Evidence Pack Compaction 基线遥测）：

- Judge token usage 链路打通（`judge_runner.py` → `judge_vote.py` → `adaptive_loop.py`）— JudgeResult/JudgeVote 新增 `token_usage` 字段，adaptive loop 每轮 judge 投票后提取 token 数据到 `iter_llm_calls`，修复 telemetry `llm_calls` 始终为空的问题
- Evidence Pack token breakdown（`context_loader.py` + `phase_runtime.py`）— `LoadedContext.token_breakdown()` 输出每个 chunk 的 source/token_estimate/char_count/priority/占比，execute 时写入 `_internal/_evidence_token_breakdown.json`
- Prompt manifest section tokens（`prompting/manifest.py` + `prompting/compiler.py`）— `PromptManifest` 新增 `section_tokens` 字段，`compile_named_sections()` 用 `estimate_tokens()` 计算各 section token 数，为 prompt 级 ablation 实验提供基线
- Evidence Pack compaction ablation 实验 — 4 组配置（baseline / rubric-compact / profile-l1 / both-compact）× 2 Phase（Q03/Q04）× 2 runs，结论：
  - Profile L1 压缩安全上线（评分偏移 0~-0.25，token 节省 41-57%），已切入生产路径（`upstream_collector.py`）
  - Rubric compact（5 级→3 级）有评分漂移（-0.3~-1.0），保留为可选严格模式（`compose_rubric_compact()`），不替换默认
- Profile L1 Phase 感知压缩（`core/profiles.py`）— `compress_to_l1()` 按 Phase 过滤 baseline sections（`_PHASE_RELEVANT_SECTIONS` 映射表），`load_profile_context_l1()` 输出纯文本替代 JSON 包裹，Q03 节省 57% / Q04 节省 41% / Q07 节省 51%
- Judge rubric compact 模式（`quality/judge/judge_rubrics.py`）— `compose_rubric_compact()` 将 5 级 rubric 压缩为 3 级（5/3/1）+ 精简 anti-rationalization，token 节省 43-45%，保留为可选模式

仍需推进（P1）：

- 审计命中率、修复闭环时长口径  
- 告警噪声治理（误报率、阈值自适配）  
- 周报到治理动作的闭环（负责人、修复 SLA）
- **Anti-Rationalization Guard 精度评估**（2026-05-10 立项）— 当前 Guard telemetry 已落盘（LAYER1_HIT / REJUDGE_PASSED / GUARD_EXHAUSTED + before/after pair），但还缺把原料变成数字的闭环。分三层落：
  - **Should P1a — Ground truth 标注集**：从历史 `_rationalization_pairs/*.json` 挑 30–50 条 pair，主会话人工判定 CONFIRMED vs FALSE_POSITIVE 作为基准集；基于基准集计算当前 `RATIONALIZATION_PATTERNS` / `OVERCORRECTION_PATTERNS` 的 precision / recall。**启动条件**：`guard_event_files_read` ≥ 20（telemetry 样本量够）
  - **Should P1b — 历史 failure-library 反事实回放**：对已知 leniency failure case 做"如果当时跑 guard 会不会拦住"的回放；输出每个 pattern 的命中率与拦截贡献。**依赖** P1a 的标注规范
  - **Nice P2 — A/B 对照实验**：同一批 Judge 输入跑 guard on/off 各一遍，对比最终 consensus 和 leniency 率差异。**成本**：holdout suite 双跑 N 条 Phase；**触发条件**：P1a + P1b 暴露的 precision 足够稳定，需要衡量净效益才启动
  - **验证指标**：guard precision ≥ 0.7、recall ≥ 0.8（先以 P1a 为基准校准阈值）
  - **实施笔记**：P1a/P1b 工作量合计约 1 周；P2 看 holdout 成本，单独立项
- **Skill Evolution 真正的 Phase Pipeline 回放（ReplayExecutor）**（2026-05-10 补，替代当前基于分布对比的打折版本）— 目前 `validate_against_holdout` 只对比 bug case 的 root_cause 分布 + suggestion 文本覆盖，**不实际执行 Phase**。距 2026-04-15 spec 的 ReplayExecutor 还有 ~80% 落差。P2 触发条件：
  - `regression/holdout/` 目录收集到至少 3-5 条可回放 case（完整输入 + 期望输出 snapshot + quality_baseline）
  - 出现 auto-merge 误放过的真实 overfitting 事件（当前分布对比漏判）
  - 预估工作量：~1 周（isolated output_dir + safe-finalize whitelist + JudgeRunner 对比 quality_baseline）
- **Bug Case compress 侧**（HL absorb+compress 对偶缺的另一半）— 当前 Bug Case Library 单调累加（2286 条），无淘汰 / 时间衰减 / 规则适用范围收窄机制。P2 触发条件：
  - Bug Case 数量 >5000，或出现"旧 case 污染新项目 suggestion"的具体失败案例
  - 与 `memory/confidence_decay.py`（已有 Correction/Preference/Fact 三级半衰期）口径统一
  - 预估工作量：0.5-1 周（衰减字段 + 查询时过滤 + 冲突规则收窄提案流程）

待启动（长期规划，等合适时机）：

- **Prompt 部署流程（LangSmith-style deployment）** — 当前 `prompt_versions`
  表是 passive 的（被动记录历史），若未来需要 active 管控（生产 prompt 在
  线切换 / 灰度 / 回滚），需要做：
  - `prompt_versions` 表加 label 字段（production / staging / canary），
    或新建 `prompt_labels` 关联表
  - `skill_loader` 加"active version 解析层"：Agent 运行时按 label 查
    当前生产版本，而不是硬编码 skill 文件
  - CLI 命令 `dqg-run observe prompt-promote --hash HASH --label production`
    用于切换生产版本
  - 审计日志：谁在何时把哪个版本设为 production
  - **启动条件**：出现真实的 prompt 生产故障且需要快速回滚（目前 skill
    文件 git revert 已够用）；或 Prompt 数量规模化（>50 个独立 prompt，
    手工文件管理成本 > 系统化成本）
  - **工作量预估**：schema 改造 0.5 周 + skill_loader 改造 1 周 + CLI +
    UI 0.5 周。不包括历史数据迁移。
  - **跳过条件**：DQG 的 prompt 是 skill 文件 + 工程化注入
    （EnumSource / Evidence Pack / Gene/Crystal），和 LangSmith
    "一段字符串" prompt 不是一回事，强上 deployment 可能和现有 skill
    加载链打架。这条不做决策时的默认状态是"不启动"。

- **Memory Garden 全局重算拆分** — 当前 `run_memory_garden` 内嵌
  `build_cross_project_links(output_dir)` 做全库跨项目相似度扫描，每个
  phase finalize 后都会跑一次，O(N²) 复杂度随项目数增长。5 个项目
  时 runtime 可忽略，10+ 项目时 finalize 会明显变慢。
  - **拆分方案**：`build_cross_project_links` 从 `run_memory_garden`
    里移出，改成独立入口由 `dqg-run observe daily` 每天调用一次；
    phase finalize 时的 Garden 只跑本 phase 边（supersedes /
    derived_from / gap_contradiction）
  - **启动条件**：已索引项目数 ≥10，或单次 finalize 的 Garden handler
    耗时 >5s（观测指标见 `_perf_metrics.json::handler_duration`）
  - **工作量预估**：garden.py 签名微调 + ops.py 加命令 + 一份测试，
    总计约 0.5 周
  - **跳过条件**：项目数维持在个位数则默认不启动，当前内嵌写法
    实现成本低于拆分成本

2026-04-25 新增（RDT-Inspired Review Optimization）：

- P1 ACT 审查深度自适应（`constants.py` REVIEW_DEPTH_CONFIG + `adaptive_loop.py` risk_tier 查表）— blast_radius risk_tier 驱动 max_iterations/force_secondary/skip_critique，LOW tier 省 ~60-70% token
- P2 锚点注入防漂移（`handoff_builder.py` extract_anchor_summary + `adaptive_loop.py` 上游 context 注入）— 每轮修正重注入 REQ/BR/SE 摘要 + 完整上游产物，防止 Worker 偏离原始需求
- P3 共享+路由 Judge rubric（`judge_rubrics.py` compose_rubric + `constants.py` SHARED_RUBRIC_DIMENSIONS）— shared(40%) 通用质量底线 + routed(60%) Phase 专属维度 + dynamic 追加，权重归一化

2026-04-25 新增（Runtime Eval Checkpoint）：

- Checkpoint Validator（`quality/checks/checkpoint_validator.py`）— 规则 + LLM 两层验证，规则层零 LLM 成本检查非空/ID 覆盖率/来源标注，LLM 层 haiku 级确认（覆盖率 60-80% 时触发，10 秒超时 fallback PASS）
- Two-Phase Worker 断点（`agents/two_phase_worker.py`）— Collector 输出 evidence_pack 后验证质量，不合格不启动 Writer，省掉无效 Writer 调用
- DAG Preflight 内容质量检查（`runtime/preflight.py`）— 上游 Phase 产物不仅检查文件存在性，还检查内容质量（ID 覆盖率、报告长度、章节完整性），不达标阻断下游 Phase

2026-04-25 新增（Phase Evaluation Protocol）：

- Phase-level 评估协议（`quality/eval/evaluation_protocols.py`）— 7 Phase × 2 角色（Judge+Critique）专属检查清单 + 行为红线 + 领域词汇，替代通用人设标签
- Gene Store phase+role 过滤（`quality/regression/gene_store.py`）— Gene 新增 agent_role 字段，注入时按 phase_id + agent_role 过滤，Q03 Judge 只看 Q03 Judge 的历史经验
- Protocol Compliance（`runtime/handlers/handlers_protocol.py`）— 已从 finalize 主流程移除。evaluation_protocols 的 prompt 注入功能保留（Judge/Critique checklist 注入），事后 keyword matching 验证因误报率高不再卡主流程。handler 文件保留供 regression 评测体系使用
- 研究驱动设计：基于 PRISM/EMNLP/Wharton 三篇独立研究结论，具体检查清单 >> 身份标签

2026-04-25 新增（Prompt Harness P0）：

- Prompt Harness 基础设施（`prompting/spec.py`, `prompting/compiler.py`, `prompting/manifest.py`, `prompting/record.py`）— 用 `PromptSpec`/`PromptAsset` 描述 prompt 身份与来源，用 SHA256 追踪 prompt 文本和依赖资产
- Prompt manifest 落盘 — `write_judge_prompt` / `write_critique_prompt` / `write_preference_prompt` / `write_review_chain_prompt` 写出 prompt 时，同步生成 `_internal/_prompt_manifests/*.json`
- 多语言无关设计 — manifest 支持可选 `language` / `profile_id` 字段，但 harness 不绑定固定语言枚举，避免新增语言 Provider 时改 prompt 治理代码

2026-04-25 新增（Prompt Policy Gate P1）：

- Prompt policy 模块（`prompting/policy.py`）— 校验 manifest 完整性、prompt hash、结构化输出 schema、evidence contract、检查清单和行为红线，并阻断专家 persona 标签
- finalize handler（`runtime/handlers/handlers_prompt_policy.py`）— `review_chain` 之后运行，发现 BLOCKED 级 policy issue 时阻断 finalize，并写入 `_internal/_prompt_policy.json`
- policy 仍保持多语言无关：只治理 prompt 元数据和评审契约，不绑定具体语言 Provider
- Judge/Critique 生成器去 persona 化 — `quality/judge/judge.py` / `quality/judge/critique.py` 从”你的身份/专家经验”改为”评估目标/行为约束/Phase Protocol”
- PromptAssembler（`prompting/assembler.py`）— 统一 Judge/Critique/Preference/Review Chain 的片段顺序、必选/可选片段和轻量模板渲染，`quality/judge/judge.py`、`quality/judge/critique.py`、`quality/judge/review_chain.py` 与 `agents/adaptive_loop.py` 共用同一入口
- 片段级追踪 — prompt manifest 新增 `assembly_order`、`section_hashes`、`section_sources`，可定位 prompt_hash 变化来自哪个片段、顺序变化或来源资产
- Prompt eval runner（P2）— `tracking/prompt_eval.py` 支持可注入 executor 与离线 `prompt_outputs/<version>.json`，逐版本执行后计算 PHASE_METRICS，并输出 prompt hash、assembly order、execution source 与指标表

2026-04-23 新增（借鉴 LangChain Evaluating Skills 方法论）：

- Prompt Fingerprint 基础设施 — `AgentResult.prompt_hash`（SHA256 前 16 位）+ `PhaseRunRecord.llm_calls` 聚合字段，自动捕获每次 LLM 调用的 model_id/prompt_hash/input_tokens/output_tokens/cache_hit，finalize 时从 `_adaptive_summary.json` 注入 telemetry；SQLite schema 同步扩展 + 存量 DB 自动迁移
- Prompt Regression Test Set — `dqg-regression prompt-eval` 子命令，Q05/Q06 各有 curated test case（固定输入 + 已知正确输出），支持不同 prompt 版本的 A/B 指标对比；逻辑提取到 `tracking/prompt_eval.py`
- Profile Rule Impact Measurement — `compute_rule_hash()` 按 Markdown 标题拆分规则块并计算 SHA256，`compare_with_baseline()` 扩展 `rule_changes` 归因字段，`dqg-regression rule-impact` 子命令输出规则变更→指标变化关联报告；逻辑提取到 `tracking/rule_impact.py`
- Prompt-Level Observability — observe 报告新增"Prompt 效果"section：prompt 版本分布（top 10 hash）、token 成本分布（phase × model 汇总）、cache 命中率；旧数据 graceful 跳过

仍需推进（P2）：

- Hybrid search（BM25 + 语义融合）— memory/ 已有 FTS5，未来可参考 claude-context 的融合策略加语义搜索。DQG agent 在明确 Phase context 下工作，不像 IDE agent 需要全 codebase 检索，优先级低于 P1

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

## F. 规模化分发边界（P0，规模化前置条件）

**定位**：解决"DQG 与用户项目代码边界模糊导致的 AI Agent 误改工具源码"问题。

**当前状态**：`规划中（P0，2026-05-10 立项，从 P1 中提升）`

> 详细症状诊断 + 三层修复路径见 [`docs/distribution-gap.md`](docs/distribution-gap.md)

### 触发现象

2026-05 第一个外部用户接入时观察到：用户的 Claude 在 DQG repo 里跑，发现 DQG 有 bug 后**直接修改 `src/dqg/` 源码**，而不是报 issue 给维护者。根因是现在 DQG 只能 `git clone` 使用，用户 cwd = DQG repo，工具和用户项目边界不存在。

### 为什么是 P0（不是 P1）

在没有分发边界之前，其他 P1 工作（CI/PR 门禁、团队看板、飞书 Bot）**都在放大同一个问题**：每新增一个接入方，都会产生新的"Claude 改 DQG 代码"事件，用户的 patch 随下次升级全废。

### 修复路径（三层）

- **L1 — PyPI 发布** `pip install dev-quality-gate`，用户目录看不到源码。Claude 默认读不到源码 → 遇到错误只能汇报而非直接修
- **L2 — `dqg-run init` 分离工作区**：用户项目下建 `.dqg/`（profile / SKILL overrides / output），工具本体用 `dqg-run path` 查询但不鼓励进入
- **L3 — CLAUDE.md guardrail 样板**：`dqg-run init` 同时往用户项目的 `CLAUDE.md` 追加一段 "DQG 是 pip 装的工具，不要改它的源码；遇到错误执行 `dqg-run doctor` 收集信息 + 报告"

### 验收标准

- 用户 cwd 里 `ls` 看不到 DQG 源码
- `dqg-run doctor` 产出可上报的 issue bundle（错误 stack + 输入摘要 + 版本 + 相关 _internal/）
- 新用户接入时，Claude Agent 默认行为是"读配置 + 跑 CLI"，而非"读源码 + 改源码"

### 工作量与依赖

- `pyproject.toml` 资源声明 + 所有路径推导改 `importlib.resources`
- `dqg-run init` 命令 + `.dqg/` 目录约定
- 发 PyPI（version bump，当前是 0.1.0）
- 迁移文档 + 升级指南
- 预估：3-5 工作日，建议单独 session

### 从 VAF 借鉴（2026-05-10 补充）

VAF（`~/git_dev/vibe-agentic-flow`）没发 PyPI 但通过 `install.sh + ~/.vcb/` 做硬了"工具/用户项目"边界，对 DQG 有 4 条可直接借鉴的点，按 ROI 排序：

1. **`install.sh` 模式作为 L1 备选**：`install.sh` 把 `skills/` / `references/` / `profiles/` 拷到 `~/.dqg/`，0.5 天即可拿到"用户 cwd 没源码"的物理边界，不必等 PyPI 改造（3-5 天）完成。详见 `docs/distribution-gap.md` §L1 备选
2. **独立 `VERSION` 文件**：VAF 用 `VERSION` 纯文本（`2.3.1-rc.20260304`）做版本源，不和 `pyproject.toml` 耦合。DQG 当前 `version = "0.1.0"` 卡死一年没动 —— 根因是跟 PyPI 发布绑定的心理负担。加一个独立 VERSION 文件让版本号流转起来
3. **双 starter 按角色分流**：VAF 根目录有 `vaf_starter.md` + `vaf_frontend_starter.md` 按角色分入口。DQG 当前只有 `dqg_starter.md`，新手/熟手/维护者挤同一份。拆为 `dqg_user_starter.md`（使用者视角）+ `dqg_dev_starter.md`（维护者视角），工作量 <1 小时但对规模化新用户体验影响大
4. **`core/` 规则外置**：VAF 用 `core/rules/*.md` + `core/standards/*.md` + `core/templates/*.md` 把规则从代码里拽出来。DQG 的 `phase_registry.py` / `phase_contract.py` / `judge_rubrics.py` 现在是 Python 代码，用户改不了。长期演进方向是抽出 `core/rubrics/Q01.yaml` / `core/thresholds.yaml` 这类用户可定制的配置文件，Python 保留做运行时加载器。不用一次做完，下次改常量时顺手抽一个就是进了一步

**DQG 比 VAF 强的地方**（对称看，不单向借鉴）：Multi-Judge + Anti-Rat/Overcorrection Guard + Bug Case Library 2000+ + Skill Evolution absorb 闭环 + 8 Tier 评分体系（`docs/evaluation-tiers.md`）都是 VAF 没有的。DQG 的问题是 **内在质量 > 外在交付**，VAF 相反。本节 4 条借鉴是补齐外在交付那一侧

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
- Phase Q05 编译验证 gate（`compile_check.py`，finalize 前自动编译检查，失败则 BLOCKED，支持 Maven/Gradle/Go，自动检测 pom.xml 目标 JDK 版本并切换 JAVA_HOME）
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
- multi_agent.py judge prompt 统一到 quality/judge/judge.py（消除 Phase-A-only 的独立实现，dag_scheduler 自动获得全 Phase rubric）
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

2026-04-23 新增：

- LanguageProvider 抽象层（`languages/base.py` ABC + `languages/registry.py` 全局 Registry，支持多语言 Provider 插拔）
- Java Provider 迁移（`languages/java/`，从 context/ 迁入 AST 分析器+断言映射，原位置 facade re-export 零破坏）
- TypeScript Provider（`languages/typescript/`，tree-sitter-typescript AST 解析 expect().toXxx() 链式调用，Jest/Vitest 断言强度映射，5 种弱断言信号）
- Pipeline Registry 驱动（handlers_execute 新增 language_detect handler，compile_check/weak_assert_context 支持 Provider 优先路径）
- Profile 扩展（DqgProfile 新增 language 字段，新增 `typescript-service` profile）
- 端到端验证（service-cli 接入：detect→Jest 识别→tsc 编译→断言解析→弱断言报告）
- LoopHealthMonitor（`agents/loop_health.py`，adaptive loop 3 维死循环检测：score stagnation / issue repetition / infra failure streak，支持 EARLY_STOP 早停省 token）
- OutputCompletenessGuardrail（`quality/guardrail/output_completeness.py`，报告截断检测 + 按 Phase 最小长度门槛，注册为第 6 个 guardrail，零 LLM 成本前置拦截残缺报告）
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
- DeepEval 评分校准层（`score_calibration.py`，Judge 评分一致性检测：DQG Judge vs DeepEval GEval 独立打分，drift > 1.0 触发告警；评分趋势监控：通胀/通缩检测）— **2026-05-10 更新**：`_run_deepeval_scoring` 已置为 no-op（`return None`），趋势检测保留。禁用原因：当时 GEval 绑 GPT-4/OpenAI，与 DQG 多 provider 策略冲突；且 Multi-Judge 投票 + Critique + Anti-Rat Guard 评审链已提供足够信号。**复活触发条件**见 §P2 DeepEval 集成条目
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
- **Trajectory Compressor**：`quality/regression/trajectory.py`（压缩 Agent 执行轨迹为 JSONL，保护首尾 turn，压缩中间 tool call）
- **AutoHarness finalize**：`quality/checks/auto_checks.py`（从 Pydantic schema + phase_registry 自动推导校验：schema 合规 / 交叉引用 / 严重等级 / RSM 覆盖率）
- **行为指纹回归**：`quality/eval/behavioral_fingerprint.py`（从 trajectory 提取工具调用模式 / ID 数量 / 输出长度，统计分布替代 binary diff，PASS/FAIL/INCONCLUSIVE 三态判定）
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
- PyPI 发布 → 已提升为规模化 P0，见 §3.F（独立章节）
- 断点续跑（Phase 失败后从断点继续）
- LSP 集成（代码智能，jedi/Java LSP）
- FTS5 自定义 tokenizer（让 SQLite 原生使用 jieba 分词，当前是应用层分词后写入）
- ~~Requirements Smell 检测接入 Phase Q01 execute~~ → 已完成：`handle_requirement_smell` 注册为 execute handler（order=3），Phase Q01 execute 时自动运行
- ~~需求层级图 GAP 检测接入 Phase Q01 finalize~~ → 已完成：`handle_requirement_graph` 注册为 finalize handler（order=63），结果追加到 verification_bundle
- ~~TREEFRAG + Demand Trace 接入 Phase Q07 execute~~ → 已完成：`handle_demand_trace`（order=75）+ `handle_code_skeleton`（order=80）注册为 execute handler，OvercorrectionGuard 接入 adaptive_loop judge pipeline

### P2（平台化规模阶段）

- **Harness/Domain 分层 Phase 1** — 定义 `HarnessApp` 协议（provider/hooks/task_runner/output_protocol/session_resume），Domain 层通过注册而非 import 接入 Harness
- **Harness/Domain 分层 Phase 2** — `context_loader.py` 的 phase-specific 分支改为 Domain 层注册的 context_policy；`multi_agent.py` 的 prompt 模板改为 Domain 层提供；`row_to_dict` 的 JSON 字段列表改为 schema 驱动
- **DeepEval 集成** — ~~引入 DeepEval 作为自动化评分引擎，替代 prompt-based judge~~ → **2026-05-10 修正为"代码保留但禁用"**。当前 `score_calibration.py::_run_deepeval_scoring` 是 no-op，趋势检测保留。2025 年起 DeepEval 已支持 Anthropic / Gemini / Bedrock / Ollama（当年绑 GPT-4 的限制已解除），但本项目已有 Multi-Judge 投票 + Critique + Anti-Rat/Overcorrection Guard 评审链，再加一层独立打分的信号增量不明显 & token 成本翻倍。**复活触发条件**（任一满足）：
  - Anti-Rationalization Guard 精度评估（见 P1 三层规划）暴露"Multi-Judge 三模型共识即便 PASS 也有大量实际 leniency"的系统偏差
  - 出现"同一报告跨 provider（Claude / DeepSeek / Qwen）评分严重分歧无法裁决"的具体 case
  - 需要定期对 golden 报告做第四方仲裁打分（避免 Judge 陷入自我校准循环）
  - 复活成本：写 `DeepEvalBaseLLM` 适配器套到 `LLMConfig`（~2h）+ 填 `_run_deepeval_scoring` 实现（~1h）+ 重新校准 `SCORE_DRIFT_THRESHOLD=1.0` 阈值（依赖真实数据，不是拍脑袋）
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
| 高 | 弱断言检测 | **已完成(100%)** | tree-sitter Java AST 解析+跨方法 Helper 分析+业务语义映射(SE/EUT)+finalize gate 阻断(WARNING)。LanguageProvider 抽象层+TypeScript Provider 已完成 |
| 高 | DAG 并行调度器 | **已完成(100%)** | `dqg-run dag` 端到端并行执行，ThreadPoolExecutor，支持 --skip/--max-parallel/--plan |
| 中 | 证据与结果的可观测性闭环 | 进行中 | 缓存命中率/证据包大小/上下文 token/LLM 调用次数统一指标 |
| 低 | Prompt 细节和文档治理 | 规划中 | 统一提示词风格、报告模板、引用格式 |

### 落地原则

1. 缓存失效：只要输入证据变更就强制失效（文件 mtime+size 签名）
2. 证据优先级：结构化事实 > 相关摘录 > 摘要 > 全文
3. 检索兜底：召回不足时允许回退到更宽松的摘要层，但不直接回全文
4. 渐进落地：先覆盖最频繁的应用路径，每次落地配命中率/token 变化/调用次数三类指标

### 记忆置信度衰减（jcode 对齐，2026-05-09）

参考：[jcode](https://github.com/1jehuang/jcode)。实现：`src/dqg/memory/confidence_decay.py`；项目级信任标量可由 `feedback_trust` 经 `recent_mean_trust_weight()` 聚合，与 `trust_level.py` 离散权重一致。

**按记忆类型的半衰期（天）**：Correction 365、Preference 90、Fact 30。

**公式**（`age` 为天；`log` 为自然对数 `ln`）：

`confidence = initial × e^(-age / half_life) × (1 + 0.1 × ln(access_count + 1)) × trust_weight`

接入检索或 Memory 注入时由调用方传入 `age_days`、`access_count` 与 `memory_category`（`correction` / `preference` / `fact`；与 `structured_facts.fact_type` 不同语义层）。子节更新：2026-05-09。

### Adaptive loop、Skill Evolution 与 Harness 增强（规划中，2026-05-09）

> 以下将 **AutoResearchClaw**（阶段目录版本化、空指标退化）、**Meta-Harness**（rubric 搜索、完整实验史、跨模型验证）等与 **DQG 现状** 对位，统一写入路线图，**不代表已排期开发**；实施时以 ISSUE 任务拆解为准。

#### 八项提案总览

| # | 主题 | 价值摘要 | 与 DQG 现状 | 建议优先级 |
|---|------|----------|-------------|------------|
| 1 | **PIVOT/REFINE 版本化目录** | 多轮修正可对比、可回退到较优轮次、为 eval_baseline 提供历史序列 | Adaptive 循环内 Worker/Judge 产物多为 **覆盖写**（如 `_worker_output`、结构化 JSON） | P0–P1 |
| 2 | **Evolution Store 时间衰减** | 老 lesson 自然降权；90 天硬过期减轻过时教训污染 context | `tracking/skill_evolution.py` 以 case **支撑数** 定置信，**无时间维度**；可与 `memory/confidence_decay.py` 思路对齐，注意与 Preference 半衰期 **口径统一** | P1 |
| 3 | **连续「无实质改善」退化检测** | 省 token；避免 doom loop；可强制结束并打 quality warning | 已有 `agents/loop_health.py`（分数停滞、issue 重复、infra 连续失败）；**可补**「产出指纹不变 + 驳回理由签名不变」与 AutoResearchClaw 式空 metrics 对位 | P0–P1 |
| 4 | **Agentic Proposer 搜索 Judge rubric** | 自动搜索维度权重、措辞、Anti-Rat 等，holdout 验证 | `quality/judge/judge_rubrics.py` 为 **静态**；成本高、需防过拟合 | P2 |
| 5 | **保留完整实验历史** | 反射器/元 harness 用上 traces+分数+上下文，优于仅摘要 | `_adaptive_summary.json`、`_judge_iter*` 等 **已存在**；Skill Reflector 通路偏窄带宽摘要时可显式引用原始片段 | P1–P2 |
| 6 | **跨模型泛化验证** | 回答「在模型 A 上调的 harness 在模型 B 是否仍有效」，支撑 `model_registry` primary/fallback | 多模型 **已支持**，**缺** 系统性 held-out 矩阵与报告落盘 | P1（流程可先半手动） |
| 7 | **data_patterns sidecar** | 按 Phase 过滤案例、保留 top N **lesson 原文**，降噪增效 | `tracking/data_patterns.py` 当前 **固定从 Q06** 提取注入各 Phase | P1 |
| 8 | **ironlaw_guard 规则外置** | 规则与案例库/配置同源，改规则少改代码 | Hook 偏 **写死**；动态全自动聚合有 **误杀与审计** 风险 | 规划-only：分阶段外置（见下表），**不预设自动从全库生效** |

#### 分阶段路线图（建议执行顺序）

**短期（约 2–4 周）**

1. **#7 data_patterns**：`write_data_patterns` 按当前 `phase_id` 过滤案例源（替代写死 Q06）；输出侧保留 top N 条 lesson 原文（长度上限可配置）。
2. **#3 退化检测**：在 `AdaptiveLoop` 与现有 `LoopHealthMonitor` 并存维度上，增加「Worker 产出指纹 / Judge 驳回摘要签名」连续不变则 **EARLY_STOP 或 PROCEED+WARNING**，结果写入 `_adaptive_summary` 与 Gate 相关字段（具体字段在任务中定）。
3. **#1 版本化（最小形态）**：在 Judge **FAIL** 且即将进入下一轮 Worker **之前**，将当前结构化 JSON、报告及 `_internal` 关键件快照到 `_pivot_v{n}/`（或等价 tarball），并维护 **当前生效** 指针（文档约定），避免下游误读旧目录。

**中期**

1. **#2 Evolution**：为 lesson/建议条目增加时间元数据（`first_seen` / `last_reinforced`）；评分乘 **指数衰减**（可与 ARClaw 式 `exp(-age·ln2/τ)` 对齐）并实施 **90 天硬过滤**；与 `confidence_decay` 文档口径统一。
2. **#5 反射输入契约**：Skill Reflector / evolution 输入显式引用 adaptive、judge 原始片段（设 token 上限），禁止「仅摘要无出处」。
3. **#6 跨模型验证**：定义 golden / failure-library 子集 × 多 held-out 模型 × 少量指标的 **runbook**，产出进 `observability/reports/`（可先脚本化半手动）。

**长期 / 研究**

1. **#4 Rubric 搜索**：独立 sandbox；搜索空间、训练/验证 split、与默认 rubric 回退策略单独立项。
2. **#8 ironlaw**：**阶段 A** 静态 YAML/JSON + schema + CI 校验，hook 只读配置；**阶段 B** 案例库仅生成 **候选规则**，经 PR 人审合并进配置；**阶段 C（可选）** 按 profile/Phase 覆盖。**不推荐**：hook 启动时从全库全自动聚合并直接生效。

#### 风险与依赖（摘要）

- **#1**：磁盘增长；需「当前指针」与索引/工具链约定，避免多版本并行时读错。
- **#3**：「强制 PROCEED」必须配套 **WARNING / GateVerdict**，避免误读为质量绿灯。
- **#2 与记忆衰减**：同一文档中区分「Evolution lesson 衰减」与 `confidence_decay` 的 **Preference 90 天** 各自适用场景。
- **#8**：外置规则需 **版本与审计**，防止不可复盘的行为漂移。

*最后更新：2026-04-25；本节规划增补：2026-05-09*

---

## 8. PhaseGuardrail 统一质量门控

> 借鉴 Agent SDK Guardrail 模式，将 DQG 三层检查统一为 PhaseGuardrail 接口。

### 短期（已完成）

| 项目 | 状态 | 说明 |
|------|------|------|
| PhaseGuardrail 基类 + GuardrailResult | **已完成** | `quality/guardrail/guardrail.py`，支持 BLOCKED/WARNING/INFO 三级 |
| 三层检查包装 | **已完成** | `quality/guardrail/guardrail_impl.py`：FinalizeChecksGuardrail / PhaseConstraintsGuardrail / RuleComplianceGuardrail |
| 并发执行 + 结果持久化 | **已完成** | `run_guardrails()` 支持 ThreadPoolExecutor 并发，结果写入 `_guardrail_results.json` |
| 接入 runtime_finalize | **已完成** | finalize handler 执行后统一跑 guardrail，不阻断主流程 |
| Phase 级 guardrail 注入（T6/T11） | **已完成** | `get_phase_guardrails(phase_id)` 按 Phase 挂额外 guardrail：Q05 接 `Q05BranchCoverageGuardrail`，Q03/Q06 接 `RationalizationProbeGuardrail` |

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

*最后更新：2026-04-25*
