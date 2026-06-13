# GEMINI.md — Gemini CLI 适配层

> 通用项目知识见 `AGENTS.md`（Phase 流程、代码规范、架构、Agent 角色等）。
> 本文件只放 Gemini CLI 特有的适配信息。

## 入口

- `/qualix-starter` — 快速启动（command 文件自包含启动逻辑，按需加载执行指南）
- CLI 启动: `qualix-run <project_id> startup`
- P1 一键入口: `qualix-run <project_id> check --prd <path> --json`（返回 PRD ingest + Q01→Q05a→Q06 phase plan）
- P0 公开验证: `qualix-run expense-demo run-demo --json`（无需模型 API key）
- P2 安装验证: `python scripts/check_installed_wheel_smoke.py`（wheel 安装后验证 `check --json` + `run-demo --json`）
- P3 Python Q05b: `python-service` 使用 compileall + import validation，pytest 模板在 `profiles/python-service/templates/`
- P4 Benchmark: `python scripts/check_phase_failure_patterns.py` 校验 Q01/Q05a/Q06 phase failure patterns

## Skill 文件结构（agentskills.io 标准）

所有 Phase skill 已迁移为 `skills/<name>/SKILL.md` + `references/` 目录结构：
- SKILL.md < 500 行（执行骨架），详细规则在 references/ 按需加载
- 支持跨平台：Claude Code / Codex / Cursor / Gemini CLI

## Orchestrator 模式 & 并行调度

长任务（Q03/Q04/Q06 等）主 Agent 作为 Orchestrator，禁止自己执行 skill，必须通过 SubAgent 派发。同一批无依赖的 Phase 可并行执行（如 Q02 + Q05a）。CLI 模式: `qualix-run <project_id> dag --max-parallel 2`。详见 `AGENTS.md`。

## 执行引擎

- execute 时自动生成 Phase Contract（`_phase_contract.json`）
- finalize 时自动收集 Verification Bundle（`_verification_bundle.json`）
- Eval Baseline：每次 finalize 自动对比历史基线
- Reasoning Sandwich：planning/verification 用 high budget，execution 用 standard（60%）

## Gemini 工具映射

| AGENTS.md 中的工具名 | Gemini CLI 等价操作 |
|---------------------|-------------------|
| Read | 直接读取文件 |
| Write | 直接写入文件 |
| Edit | 直接编辑文件 |
| Grep | `grep` / `rg` 命令 |
| Bash | shell 命令执行 |

## 多平台支持

| 工具 | 指令文件 |
|------|---------|
| Claude Code CLI | `CLAUDE.md` + `AGENTS.md` |
| OpenAI Codex CLI / opencode | `AGENTS.md` |
| Google Gemini CLI | `GEMINI.md`（本文件）+ `AGENTS.md` |
| Cursor | `AGENTS.md`（Cursor 规则可由 `qualix-run init` 在用户项目中生成） |
| IntelliJ IDEA | `AGENTS.md` |

*最后更新：2026-06-13*
