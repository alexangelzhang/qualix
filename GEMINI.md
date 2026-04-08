# GEMINI.md — Gemini CLI 适配层

> 通用项目知识见 `AGENTS.md`（Phase 流程、代码规范、架构、Agent 角色等）。
> 本文件只放 Gemini CLI 特有的适配信息。

## 入口

- 全流程引导: 读取 `dqg_starter.md` 开始
- CLI 启动: `python -m dqg.runner <project_id> startup`

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
| Claude Code CLI | `CLAUDE.md`（Claude Code 专属）+ `AGENTS.md`（通用知识） |
| OpenAI Codex CLI / opencode | `AGENTS.md` |
| Google Gemini CLI | `GEMINI.md`（本文件）+ `AGENTS.md`（通用知识） |
| Cursor | `.cursor/rules/dqg.mdc` + `AGENTS.md`（通用知识） |
| IntelliJ IDEA | `AGENTS.md` |

*最后更新：2026-04-08*
