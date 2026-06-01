# 性能治理 Changelog

> 本文件从 AGENTS.md 拆分，记录 Qualix 框架的性能优化历史。

## 2026-04-11
- Skill Evolution 技能自进化闭环（`skill_evolution.py`）
- 代码语义检索增强（`code_semantic_search.py`，SE→Code 自动映射）
- Skill 目录结构改造为 agentskills.io 标准
- Reasoning Sandwich（reasoning_profile 按 Phase 配置 high/standard）
- Worker 内部拆分（`two_phase_worker.py`，Collector→Writer）
- Eval-Driven 量化质量基线（`eval_baseline.py`）

## 2026-04-10
- multi_agent.py judge prompt 统一到 quality/judge.py
- cmd_auto 切换到 runtime
- adaptive_loop report_map 补齐 Q02/Q05a/Q06/Q07
- skill_loader 接入 dag_scheduler（progressive disclosure 激活）
- Skill 结构标准化（7 个 Phase skill 统一追加 Anti-Rationalization + Verification 节）
- Agent Persona（Judge: 10 年质量负责人；Critique: 资深 QA 架构师）
- Phase Q01 假设前置（Step 0.5 Assumption Surfacing）
- Phase Q05a Mock 优先级（Real > Fake > Stub > Mock）+ DAMP 原则
- Phase Q07 变更大小门禁 + 评论严重级别标签
- 全局错误恢复协议（Stop-the-Line + Triage 五步法）
- 上下文层级模型（五级金字塔 + 信任级别 + 行数阈值）
- Phase Q02 实施切片指导（垂直切片 + 风险优先 + XS/S/M/L/XL）
- Phase Q06 Judge 新增 scenario_quality 维度 + CONFLICT 状态
- Phase Q01 输出增加边界约定节 + 范围外发现节
- 下游→上游反馈触发（UPSTREAM_UPDATE_NEEDED）
- Skill Factory + Bug Case Lesson 自动推断 + 测试数据模式推导
- DeepEval 评分校准层（`score_calibration.py`）
- 断线修复：DAG scheduler / score_calibration / session_startup / task_store

## 2026-04-09
- 跨项目知识自动注入（`_cross_project_insights.md`）
- 案例相关性二级匹配（同义词扩展）
- 图片→Mermaid 验证闭环
- Phase Q05b 编译验证 gate（原 Q05a 分拆后，编译 gate 归属 Q05b）
- Q04 覆盖度结构化映射表
- 业务域变异测试推导
- Harness/Domain 分层 Phase 0
- Runtime Kernel（11 个独立 handler）
- 跨 session 进度文件 + Session startup protocol + Task store
- 动态 Judge grading criteria + Blast radius 影响范围分析
- Judge anti-rationalization table + 事实索引 confidence tagging
- Phase skill progressive disclosure
- Hyperedge 多实体关联
- Phase Q05a/Q07 Judge rubric 补齐
- 覆盖率门禁代码化

## 2026-04-08
- `agent-run` / `adaptive` 有效上下文去重读取
- `write_phase_profile_manifest()` relevance-matched bug case manifest
- `load_profile_context()` 基于路径 + mtime 的进程内缓存
- `LoadedContext` 流式写盘 helper
- `load_context()` retrieval-first evidence pack 收口
- `chunk_processor.py` 局部 token cache
- Judge / Critique / Experiment bug case relevance excerpt/seed 模式
- `adaptive_loop` multi-judge vote 并行化
- `semantic_cache` / `MemoryLayer.search()` 版本感知 cache namespace
- `MemoryLayer.index_phase()` 增量索引
- `adaptive_loop` Agent.query_cache + FTS5 中文检索升级
