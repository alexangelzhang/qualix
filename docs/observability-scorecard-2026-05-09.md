# DQG 可观测性能力评分卡 · 2026-05-09

> **用途**：基线记录，用于对照 LangSmith / Langfuse 这两家业界成熟平台跟踪 DQG 可观测性能力的演进。
>
> **刷新频率**：可观测性相关功能成套落地后重评一次（上一次是 2026-05-09 的 P0-P3 包）。只做零星修改时不用重评。

## 评分口径

- **★★★★★**：功能齐全、在生产环境跑得稳、有配套工具
- **★★★★☆**：核心能力有了，缺一两个次要特性
- **★★★☆☆**：骨架搭起来了，细节和覆盖面不够
- **★★☆☆☆**：只有局部能力，或仅在特定场景可用
- **★☆☆☆☆**：基本没有

DQG 不追求在每一维都打满——某些维度（比如 playground）对 DQG 的工程化 prompt 装配机制意义不大，刻意留空。

## 9 维全景（2026-05-09）

| 维度 | LangSmith | Langfuse | DQG 当前 | 核心差距 |
|------|-----------|----------|----------|----------|
| LLM 调用追踪 | ★★★★★ | ★★★★★ | **★★★★☆** | 仍差 per-step latency 分层（model / tool / prompt 装配三段独立计时）|
| Prompt 管理 | ★★★★★ | ★★★★☆ | **★★★☆☆** | 仍差 playground（在线编辑）、部署流程（已写进 ROADMAP 待启动）|
| 评估框架 | ★★★★★ | ★★★★☆ | **★★★★★** | bootstrap 实证分位数补上"统计显著性"，本轮闭合 |
| 监控告警 | ★★★★★ | ★★★★☆ | **★★★★☆** | Z-score/IQR 已接入。仍差：实时流（当前批处理日报模型）|
| 成本追踪 | ★★★★☆ | ★★★★☆ | **★★★★☆** | 按 `(phase, model)` 聚合已落地。仍差：按 rule 归因的成本（需要 rule_hash 打到 llm_call）|
| 数据集管理 | ★★★★★ | ★★★★☆ | ★★★☆☆ | 仍差：版本化、从生产采样 |
| 人工标注 | ★★★★☆ | ★★★★☆ | ★★☆☆☆ | approve/skip 是隐式反馈，缺结构化标注 UI + 评分维度 |
| 回归检测 | ★★★★☆ | ★★★☆☆ | **★★★★☆** | regression.py + failure library + 周趋势做得不错；本轮 empirical baseline 间接降误报 |
| 规则归因 | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | `rule_hash` + `rule_changes` 是 DQG 独有能力，通用平台没对应概念 |

## 本轮（2026-05-09 P0-P3 包）的评分迁移

| 维度 | 之前 | 之后 | 本轮贡献 |
|------|------|------|---------|
| LLM 调用追踪 | ★★★☆☆ | ★★★★☆ | P0 加 prompt/response excerpt + P2 加 trace_run_id + span_path 分层 |
| Prompt 管理 | ★★☆☆☆ | ★★★☆☆ | P2 版本库骨架 + `dqg-run observe prompt-versions` 查询 CLI |
| 评估框架 | ★★★★☆ | ★★★★★ | P1-b `_eval_metric_runs.jsonl` + bootstrap 式实证分位数 |
| 监控告警 | ★★★☆☆ | ★★★★☆ | P3 Z-score/IQR 接入 `observability_alerts.extra_alerts` 钩子 |
| 成本追踪 | ★★☆☆☆ | ★★★★☆ | P1-a `estimate_llm_call_cost_usd` + 按 `(phase, model)` 聚合 + Dashboard 展示（提了两档）|

未变动 4 项：数据集管理、人工标注、回归检测、规则归因——不是优先级，本轮未排期。

## DQG 相对通用平台的独特优势

这几条是 LangSmith / Langfuse **不具备**的领域特化能力，应被视为 DQG 的结构性差异，不是需要"赶上"的差距：

1. **质量门禁语义**：可观测性围绕 Phase 质量门禁（Q01-Q07）设计，不是通用 LLM tracing。Judge/Critique 投票、共识机制、早停策略是领域特有
2. **规则级归因**：`compute_rule_hash()` + `rule_changes` 能追踪到"哪条 baseline 规则变更导致指标退化"
3. **Loop Health 监控**：score stagnation、issue repetition、infra failure 检测是 multi-agent 循环特有
4. **Behavioral Fingerprint**：从 trajectory 提取工具调用模式、ID 计数等行为指纹，用于检测 agent 行为漂移

## 仍未覆盖的差距（按成本/收益排序）

| 优先级 | 改进项 | 工作量 | 判断 |
|--------|--------|--------|------|
| 小工作量顺手做 | LLM tracing 的 per-step latency 分层 | 0.5 周 | 下次动 agent.py 时一并做 |
| 架构级改动再动 | 成本归因到 rule（rule_hash 打通到 llm_call）| 1.5 周 | 等"成本异常告警"有明确需求再启动 |
| 架构级改动再动 | 实时告警流（消息队列 / SSE）| 2+ 周 | 当前批处理日报模型够用，不启动 |
| ROI 低，默认不做 | Prompt playground（在线编辑 UI） | 2+ 周 | DQG 的 prompt 是 skill 文件 + 工程化注入，和 LangSmith 的"一段字符串"不是一回事 |
| ROI 低，默认不做 | Prompt 部署流程（label/灰度/回滚）| 2 周 | 已写进 ROADMAP §C "待启动"，详见该节启动条件与跳过条件 |
| 次优先 | 数据集版本化 + 从生产采样 | 1.5 周 | 等 regression case 规模化（>500 条）再做 |
| 次优先 | 人工标注结构化 UI + 多维评分 | 2+ 周 | 等对标注质量有量化要求时再做 |

## 下一次重评触发条件

出现以下任一情况时重评这张表：

- 可观测性新增功能成套落地（如这次 P0-P3 包）
- 对比平台（LangSmith / Langfuse）出了新能力影响评分口径
- 实际使用 6 个月以上发现某一维度的评分与体感偏差明显
- 某项"待启动"条目被真正立项并完成

## 引用

- 本表起点：2026-05-09 session 最后对 P0-P3 可观测性包做的 review
- 相关 commit：`68ae29c` / `d14373a` / `48b8bf4` / `23ad226` / `aad70bd` / `3556ee9`
- 相关 ROADMAP 条目：§C "仍需推进（P1）" 和 §C "待启动（长期规划）"
