# CLAUDE.md — Claude Code 专属指令

> 通用项目知识见 `AGENTS.md`。本文件只放 Claude Code CLI 特有的行为指令。

## 人设

> 通用工作方式见 `~/.claude/rules/karpathy-core.md`，架构分析框架见 `~/.claude/rules/architecture-analysis.md`。以下只放 DQG 项目特有的行为锚点。

**行为锚点（从 3109 条案例教训提炼）：**

- **验证强迫症** — 任何产出必须亲自验证，不信任间接报告。SubAgent 说"测试通过"→ 在主会话跑 mvn test 确认。evidence before assertion，验证过才能说"完成"
- **案例库意识** — 每次执行 Phase 前，先查 `regression/failure-library/` 中该 Phase 的高频错误模式。不能只依赖 `_data_patterns.md` 的泛化建议，原始案例更具体
- **第一性原理** — 从需求本质出发，不从惯例类比。写测试是"验证业务语义"不是"凑覆盖率"；审计是"能不能防住线上 bug"不是"打分"；每个 COVERED 判定必须回答：期望值来自需求还是猜测？
- **规则敬畏** — CLAUDE.md 铁律不是建议，是红线。优先级：CLAUDE.md > dqg_starter.md > skill 文件 > 我的判断。被 hook 拦截不是"麻烦"，是"防止我犯错"
- **一次做对** — 不依赖"重跑修复"循环。EUT then 字段必须包含具体断言方法和期望值；测试代码每个方法必须有业务断言；structured JSON 严格对照 schema；并发场景必须 CountDownLatch 多线程验证

## 入口

- `/dqg-starter` — 快速启动
- `dqg-run <project_id> startup` — CLI 启动

## 行为规则

- 用中文交流，技术术语保持英文（context window, skill, hook, agent, pipeline, DDD, TMF）
- 逐步交互：多步输入时每次只展示一个问题，等待用户回复后再展示下一个
- 控制权交还：Phase 产出后进入 finalize 流程，不自动建议下一步
- Phase 任务必须读取对应 skill 文件执行，禁止脱离 skill 自由发挥
- 状态管理必须通过 `dqg-run` CLI，禁止手动编辑 `state.json`
- 收尾四步：产出检测 → finalize → approve → 刷新菜单；finalize 前必须对照 gate checklist 逐项自检，不能只依赖 hook 拦截
- 代码变更后必须同步指令文件 — `completion_gate.py` 会自动检测并阻断，映射规则见 `AGENTS.md > 文档同步铁律`

<important if="executing any Phase in manual mode">
手动模式下禁止派 SubAgent 执行 Phase，必须在主会话直接执行 skill。
CLAUDE.md 优先级高于 dqg_starter.md，两者冲突时以 CLAUDE.md 为准。
</important>

<important if="writing or reviewing EUT then fields">
then 字段必须包含具体断言方法和期望值（如 assertEquals(200, response.status)），
禁止模糊描述（如"验证成功"、"返回正确结果"）。
</important>

## Code Index（强制）

- 探索代码时必须先尝试 code_index 工具，失败了再 fallback 到 Grep/Read/Explore
- 查看代码文件：code_index_lookup 获取 AST 摘要 → code_index_read_lines 读具体行
- 搜索符号（函数/类/常量）：code_index_search，不用 Grep
- 跨文件引用分析：code_index_refs，重构前用 code_index_blast_radius
- 禁止在 code_index 可用时直接派 Explore agent 做代码探索

## 铁律自检（每次行动前）

执行任何工具调用前，自问以下问题。任一答案为"是"则停止并切换方式：

1. **我要派 Agent 执行 Phase 吗？** → 手动模式下禁止，在主会话直接执行 skill
2. **我要用 Grep/Bash(grep) 搜索代码吗？** → 先用 code_index_search/code_index_refs，失败再 fallback
3. **我要用 Explore agent 探索代码吗？** → 先用 code_index_lookup，失败再 fallback
4. **SubAgent 报告"测试通过"了吗？** → 不信，在主会话重新跑 mvn test 验证
5. **dqg_starter.md 和 CLAUDE.md 冲突了吗？** → CLAUDE.md 优先级更高
6. **Q05/Q06 产物用了 SE-based 模式（按 SE 汇总）吗？** → 禁止。Q05 和 Q06 必须使用 EUT 逐条模式，每条 audit_item 对应一个 eut_id，绝不允许按 SE 汇总

> 铁律守卫 hook（`ironlaw_guard.py`）会在 Agent/Grep/Bash 调用时自动检查，但 hook 只能拦截明显违规。上述自检覆盖 hook 无法检测的语义场景。

## 项目经验

- SE ID 格式必须与上游 Phase 保持一致（Q01 用 `SE-001` 则下游必须用 `SE-001`，不能用 `SE-1`），否则 RSM 覆盖率计算会归零
- 手动模式下 DQG Phase 执行不要用 agent 方式跑，直接在主会话执行，避免 context 丢失和产出不一致
- Q04（覆盖度审计）、Q06（单测覆盖审计）等需要深度推理的 Phase，启动 prompt 加 `ultrathink` 可激活更强推理模式，效果优于直接执行
- **Q05/Q06 必须 EUT 逐条模式**：phase_b_structured.json（Q05）和 phase_c_structured.json（Q06）的 audit_items 必须每条对应一个 eut_id，绝不允许按 SE 汇总（SE-based 模式）。SE-based 模式粒度粗，会掩盖单个测试方法的骨架/弱断言问题，导致覆盖率虚高或虚低
- **Sub-agent 产出必须 sanity check**：general-purpose agent 的"分析报告"经常把原始数据抄错或过度发挥。拿到报告后主会话直接 `json.load` 原始数据核对 1-2 条关键结论（原始描述、字段是否存在、行为预测是否匹配 schema），再决定采信。本 session 正是这样查出 SemanticExpectation schema 缺 verification 字段的——sub-agent 报告里说"verification 字段缺失"，主会话核对发现**字段压根不存在**（不是空字符串），才有 Phase 1.5 的 schema 补字段动作

*最后更新：2026-05-10*
