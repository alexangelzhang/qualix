# Multi-Agent 架构详解

> 本文件从 AGENTS.md 拆分，仅在使用 `agent-run` / `adaptive` / `dag` 命令时需要参考。

## Agent 角色

| 角色 | 职责 | Context | 模型建议 |
|------|------|---------|---------|
| Worker Agent | 按 skill 执行 Phase 任务，输出报告+JSON+推理日志 | 独立：只看输入材料+skill | Opus（最强推理） |
| Architect Agent | Phase Q02 专用：基于需求生成技术方案（HLD+LLD+DTO+流程图） | 独立：需求产物+代码仓库+知识库 | Opus（深度设计） |
| Judge Agent | 独立评审产物准确性，打分+找问题 | 独立：只看产物，看不到 Worker 推理过程 | Sonnet（平衡） |
| Critique Agent | 假设有遗漏主动找问题 | 独立：看产物+Judge 结果 | Opus（深度推理） |
| Preference Agent | 比较 v1 vs v2 偏好 | 独立：看两个版本 | Sonnet |
| Orchestrator | DAG 调度 + 并行编排 + 自适应循环 | 全局视图 | Haiku（轻量） |

## Phase 1: Prompt 隔离模式

生成独立 prompt 文件，在当前 session 中用 subagent 执行。适合日常使用。

```bash
qualix-run <project> orchestrate <phase> --plan
qualix-run <project> orchestrate <phase>
```

生成的文件：
- `_worker_prompt.md` — Worker Agent 读取执行
- `_judge_prompt_v2.md` — Judge Agent 读取评审（看不到 Worker 推理日志）
- `_critique_prompt_v2.md` — Critique Agent 读取批评

执行方式：主 session spawn 三个 subagent，依次执行 Worker → Judge → Critique。

源码: `src/dqg/multi_agent.py`

## Phase 2: 真独立 Agent 模式

通过 API 调用真正独立的 LLM 实例，支持不同模型+自动 fallback。适合 CI/CD 集成。

```bash
qualix-run <project> agent-run <phase>
qualix-run <project> agent-run <phase> \
  --primary claude-opus-4-6 \
  --fallback deepseek-chat \
  --judge-model claude-sonnet-4-6
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

## Phase 3: 自适应循环模式

Judge 不通过 → 自动触发 Worker 修正 → 再次 Judge → 循环直到通过或达上限。支持多 Judge 并行投票。

```bash
qualix-run <project> adaptive <phase>
qualix-run <project> adaptive <phase> \
  --primary claude-opus-4-6 \
  --judge-models claude-sonnet-4-6,deepseek-chat \
  --max-iter 3 --threshold 3.5
```

自适应循环流程：
```
Iter 1: Worker 执行 → 多 Judge 投票 → Guard 放水检测 → 不通过？→ Critique 找问题
Iter 2: Worker 根据反馈修正 → 多 Judge 投票 → Guard 放水检测 → 不通过？→ Critique
Iter 3: Worker 再次修正 → 多 Judge 投票 → Guard 放水检测 → 通过/达上限
全部 FAIL + Judge 健康 → SkillReflector 自动进化 skill 规则
```

审查深度自适应（P1 ACT）：
- blast_radius risk_tier → REVIEW_DEPTH_CONFIG 查表
- LOW: 1 轮, primary only, 跳过 critique
- MEDIUM: 2 轮, boundary secondary
- HIGH/CRITICAL: 3 轮, 强制 secondary

锚点注入防漂移（P2）：
- 每轮修正时 handoff 文档新增 Anchor section（REQ/BR/SE 摘要）
- Fixer context_files 保留完整 _upstream_context.md

共享+路由 Judge rubric（P3）：
- compose_rubric(phase_id) 组合 shared(40%) + routed(60%) + dynamic
- 权重归一化：所有维度等比缩放使总和 = 100%

Phase 评估协议（Evaluation Protocol）：
- 每个 Phase 的 Judge/Critique 有专属检查清单 + 行为红线 + 领域词汇
- 静态层：人工维护的基础协议（低频更新）
- 动态层：Gene Store 按 phase_id + agent_role 过滤注入历史经验
- 门控：protocol_compliance handler (required, HARD gate)

Runtime Eval Checkpoint：
- Two-Phase Worker 断点：Collector → validate_checkpoint → Writer（evidence_pack 质量不达标不启动 Writer）
- DAG Preflight 内容质量：上游产物 ID 覆盖率 + 报告长度 + 章节完整性检查
- 两层验证：规则层（零 LLM）+ LLM 层（haiku，覆盖率 60-80% 时触发，10 秒超时 = PASS）

Anti-Rationalization Guard（运行时放水拦截）：
- Layer 1: 关键词正则扫描（8 种放水模式，零成本）
- Layer 2: LLM 确认（仅 Layer 1 命中时触发，haiku 级模型）
- 拦截后重审 1 次，预算耗尽标记 GUARD_EXHAUSTED 降级手动 judge
- 源码: `src/dqg/quality/rationalization_guard.py`

Skill Evolution 自动闭环（adaptive 耗尽后触发）：
- Judge Health Gate: 区分 SEMANTIC_FAIL vs INFRA_FAILURE
- 仅 SEMANTIC_FAIL 触发 Reflect→Persist→Cluster→Write pipeline
- v1 仅 SKILL_RULE 可自动合并，其他类型降级人审
- 源码: `src/dqg/tracking/skill_reflector.py`

JudgeRunner 统一执行：
- 所有 Judge 调用统一走 `JudgeRunner`（canonical schema，structured output）
- primary→fallback 模型链，双失败才标记 INFRA_FAILURE
- 源码: `src/dqg/quality/judge_runner.py`

投票规则：
- 全部 PASS → 共识 PASS
- 过半 FAIL → 共识 FAIL
- 其他 → PASS_WITH_CONCERNS
- 均分 ≥ threshold → 通过

产出文件：
- `_judge_iter1.json` / `_judge_iter2.json` — 每轮投票结果
- `_adaptive_summary.json` — 循环总结

源码: `src/dqg/adaptive_loop.py`

## Multi-Agent 编排

三个 Agent 通过文件交换数据，context 完全隔离：

```
Worker 写入 → phase_a_report.md + _reasoning_log.md
                    ↓（Judge 只读报告，看不到推理日志）
Judge 写入  → _judge_result.json
                    ↓
Critique 写入 → _critique.json
```
