# CLAUDE.md — Claude Code 专属指令

> 通用项目知识见 `AGENTS.md`。本文件只放 Claude Code CLI 特有的行为指令。

## 入口

- `/dqg-starter` — 快速启动
- `dqg-run <project_id> startup` — CLI 启动

## 行为规则

- 用中文交流，技术术语保持英文（context window, skill, hook, agent, pipeline, DDD, TMF）
- 逐步交互：多步输入时每次只展示一个问题，等待用户回复后再展示下一个
- 控制权交还：Phase 产出后进入 finalize 流程，不自动建议下一步
- Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥
- 状态管理必须通过 `dqg-run` CLI，禁止手动编辑 `state.json`
- 收尾四步：产出检测 → finalize → approve → 刷新菜单
- 代码变更后必须同步指令文件 — `completion_gate.py` 会自动检测并阻断，映射规则见 `AGENTS.md > 文档同步铁律`

## Code Index（强制）

- 探索代码时必须先尝试 code_index 工具，失败了再 fallback 到 Grep/Read/Explore
- 查看代码文件：code_index_lookup 获取 AST 摘要 → code_index_read_lines 读具体行
- 搜索符号（函数/类/常量）：code_index_search，不用 Grep
- 跨文件引用分析：code_index_refs，重构前用 code_index_blast_radius
- 禁止在 code_index 可用时直接派 Explore agent 做代码探索

*最后更新：2026-04-29*
