# Architecture

> 本文件从 AGENTS.md 拆分，仅在开发 DQG 框架本身时需要参考。

**项目类型**：CLI 框架 + AI Agent Pipeline
**主要语言**：Python 3.11+
**入口点**：`src/dqg/core/runner.py`（CLI）、`dqg_starter.md`（AI IDE）

## 包结构
| 子包 | 职责 | 关键模块 |
|------|------|---------|
| `core/` | 状态机 + CLI 入口 + Profile | state_machine.py, phase_registry.py, runner.py, profiles.py |
| `store/` | SQLite 统一存储（facade + 8 子模块） | core.py (schema), telemetry.py, experiments.py |
| `cache/` | FTS5 缓存/索引层 | fact_cache.py, image_cache.py, text_cache.py, semantic_cache.py, code_search.py, code_semantic_search.py |
| `memory/` | 记忆/知识层 | memory_layer.py, knowledge_network.py, version_tracker.py, wiki_layer.py |
| `agents/` | Multi-Agent 框架 | llm_backends.py, agent.py, adaptive_loop.py, two_phase_worker.py |
| `quality/` | 质量评审链 | judge.py, critique.py, review_chain.py, golden_sample.py, coverage_gate.py, eval_baseline.py, requirement_smell.py, requirement_graph.py, demand_trace.py |
| `tracking/` | Bug 案例 + 回归 + 实验 | bug_cases.py, case_selector.py, skill_factory.py, skill_evolution.py |
| `context/` | 上下文加载 + 分块压缩 | context_loader.py, chunk_processor.py, diff_context.py, skill_loader.py, code_skeleton.py |
| `prompting/` | Prompt Harness：prompt spec、assembler、模板片段、hash、manifest、policy gate | assembler.py, spec.py, compiler.py, manifest.py, policy.py, record.py |
| `languages/` | 多语言 Provider 抽象层 | base.py, registry.py, java/provider.py, typescript/provider.py |
| `reporting/` | 性能/指标/可观测 | perf_tracker.py, telemetry.py, collect_metrics.py |
| `ingest/` | 文档抓取（可扩展） | feishu/ |
| `media/` | 图片处理 | parse_images.py, validate_mermaid.py |
| `services/` | 业务服务层 | phase_service.py, orchestrator.py |
| `runtime/` | 执行引擎 + 生命周期 | phase_runtime.py, lifecycle.py, handlers_execute.py, handlers_finalize.py, session_startup.py, task_store.py |
| `security/` | 安全扫描 | content_scanner.py, tool_permissions.py |
| `schemas/` | Phase 数据契约 | phase_a.py ~ phase_d.py |

## 根目录工具模块
| 文件 | 职责 |
|------|------|
| `constants.py` | 全局常量（Phase 映射、路径、阈值、定价） |
| `json_utils.py` | 统一 JSON 操作 |
| `exceptions.py` | 异常层次 |
| `log.py` | 统一日志配置 |
| `store.py` | 存储层 facade |
| `agent_framework.py` | Agent 框架 facade |

## 数据目录
| 目录 | 职责 |
|------|------|
| `profiles/` | 技术栈 profile（每个含 profile.json + baseline.md） |
| `references/` | 通用模板 + 共享知识 |
| `regression/` | Bug 案例库 + Golden Sample |
| `skills/` | 7 个 Phase 的 skill prompt |
| `output/` | 项目产物目录 |

## 设计模式
- **Harness/Domain 分层**：`phase_registry.py`（Domain）与 `state_machine.py`（Harness）分离
- **状态机**：Phase 流转（not_started → in_progress → pending_review → approved）
- **Plugin 式 Skill**：每个 Phase 对应一个 .md skill 文件，执行时动态加载
- **Prompt Harness**：Prompt 内容仍由 domain 模块生成，harness 统一 assembler 顺序、section hash、section source mapping、prompt hash、资产 hash 和 `_internal/_prompt_manifests/*.json`，finalize 时通过 `prompt_policy` 校验 schema 绑定、证据契约、检查清单、行为红线，并阻断专家 persona 标签
- **SQLite 统一存储**：所有缓存/索引/遥测/状态共用一个 DB，FTS5 中文 n-gram 分词
- **Facade 模式**：大模块拆分后保留 facade re-export
- **Multi-Agent**：三阶段（prompt 隔离 → 独立 API → 自适应循环），详见 `docs/multi-agent-architecture.md`

## 外部依赖
- **存储**：SQLite（内置，零部署）
- **LLM API**：Anthropic / OpenAI / Google Gemini / DeepSeek / Qwen / Moonshot（按需）
- **飞书 API**：文档抓取（larkkit，可选）

## Common Tasks → Files

| 要做什么 | 看哪里 |
|----------|--------|
| 加新 Phase / 改 Phase 流转 | `core/phase_registry.py` → `constants.py` → `skills/` |
| 加新 CLI 命令 | `commands/` 新建 .py → `core/runner.py` 注册 |
| 改 LLM 调用逻辑 | `agents/llm_backends.py` → `agents/agent.py` |
| 改质量评审链 | `quality/judge.py` / `critique.py` |
| 加新语言支持 | `languages/base.py` → `languages/registry.py` → `profiles/<profile-id>/profile.json` |
| 改 Prompt 治理/追踪 | `prompting/` → `quality/judge.py` / `critique.py` / `review_chain.py` |
| 改 Bug 案例匹配 | `tracking/case_selector.py` → `tracking/bug_cases.py` |
| 改上下文加载/压缩 | `context/context_loader.py` → `context/chunk_processor.py` |
| 改存储 schema | `store/core.py` → `store.py`（facade） |
| 加新 execute/finalize sidecar | `runtime/handlers_execute.py` 或 `handlers_finalize.py` |
| 改常量/阈值 | `constants.py`（唯一来源） |
