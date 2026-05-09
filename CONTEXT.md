# CONTEXT.md — DQG 领域术语表

> 所有 agent/skill/文档必须使用本文件定义的术语。歧义时以本文件为准。

## 核心概念

### Phase
DQG 流水线中的一个执行阶段，编号 Q01-Q07。每个 Phase 有独立的 Skill、产物目录和质量约束。
- _Avoid_: "步骤"、"stage"、"step"（Phase 是独立可调度单元，不是线性步骤）
- Relationships: Phase 由 Skill 驱动，产出经 Finalize 校验，受 GateVerdict 卡控
- Example: "Q03 Phase 依赖 Q02 完成后才能执行"

### Gate
质量门禁——阻断不合格产出流入下游的检查点。DQG 的核心价值主张。
- _Avoid_: "检查"、"validation"（Gate 强调阻断能力，不只是检查）
- Relationships: Gate 由 GateVerdict 统一裁决，包含 HARD gate（不可绕过）和 SOFT gate（可降级）

### Skill
Phase 对应的执行指令文件（`skills/*.md`），定义该 Phase 的完整执行步骤（Step 0-6）。Agent 必须严格按 Skill 执行，禁止自由发挥。
- _Avoid_: "prompt"、"template"（Skill 是完整的执行规程，不是模板片段）
- _Avoid_: 与 Claude Code 的 "superpowers skill" 混淆——DQG Skill 是 Phase 执行规程，superpowers skill 是 Claude Code 插件能力
- Relationships: 每个 Phase 对应一个 Skill 文件，Skill 引用 Profile 和 Knowledge

### Profile
项目配置集，定义目标项目的语言、框架、架构风格和评审规则（如 `profiles/java-ddd-tmf/`）。
- _Avoid_: "config"、"settings"（Profile 是领域知识集，不是技术配置）
- Relationships: Profile 包含 baseline（基线规则）和 risk-catalog（风险目录），被 Skill 引用

### Finalize
Phase 产出完成后的校验流程。运行所有 handler（report_quality_checks、finalize_checks、flow_integrity 等），汇总为 GateVerdict。
- _Avoid_: "submit"、"complete"（Finalize 是主动校验，不是简单提交）
- Relationships: Finalize → GateVerdict → Approve（三步收尾）

### GateVerdict
统一卡控裁决层。汇总所有检查结果到 `_gate_verdict.json`，分 HARD（不可绕过）和 SOFT（可降级）两级。Approve 命令读取 GateVerdict 决定是否放行。
- _Avoid_: "result"、"score"（GateVerdict 是二值裁决 PASS/BLOCKED，不是分数）
- Relationships: 由 Finalize handler 产出构建，被 Approve 消费

### Worker
执行 Phase 核心任务的 LLM 调用。Worker 接收 Prompt Harness 组装的完整 prompt，产出结构化报告。
- _Avoid_: "agent"（Worker 是单次 LLM 调用，不是自主 agent）
- Relationships: Worker 由 Harness 驱动，产出经 Judge 评分

### Judge
对 Worker 产出进行质量评分的 LLM 调用。使用 Shared Rubric + Phase-specific rubric 双维度打分。
- _Avoid_: "reviewer"（Judge 是量化评分，不是定性评审）
- Relationships: Judge 在 adaptive loop 中可触发多轮迭代，受 Rationalization Guard 监控

### Critique
切换批评者视角审视 Worker 产出，发现 Judge 可能遗漏的结构性问题。与 Judge 互补。
- _Avoid_: "review"（Critique 是对抗性审视，比 review 更激进）
- Relationships: Critique 高置信度发现可结晶为 Gene

### Gene (Critique Gene)
历史高置信度 Critique 结晶的评审基因。模式匹配后自动注入同类 Phase 的上下文，实现跨 session 经验传递。
- _Avoid_: "rule"、"pattern"（Gene 是从实际评审中提炼的，不是预设规则）
- Relationships: 由 Critique 产出 → 结晶 → 注入下次执行

### Crystal (Skill Crystal)
历史高分执行的成功模式结晶。记录"什么样的执行方式得了高分"，同 Phase 复用。
- _Avoid_: "example"、"template"（Crystal 是经验证的成功模式，不是示例）
- Relationships: 与 Gene 互补——Gene 记录"什么会出错"，Crystal 记录"什么做得好"

### Harness (Prompt Harness)
Prompt 组装追踪系统。负责将 Skill + Profile + Gene + Crystal + Evidence 组装为完整 prompt，并记录 manifest（hash、section sources、组装顺序）供审计。
- _Avoid_: "prompt builder"（Harness 强调可追踪性，不只是组装）
- Relationships: Harness 产出 manifest 文件，供 Prompt Policy Gate 校验

### Evidence Pack
检索优先的上下文包。将上游产物、diff、profile 等压缩为 token 高效的证据集，注入 Worker prompt。
- _Avoid_: "context"（Evidence Pack 是经过筛选和压缩的，不是原始上下文）
- Relationships: 由 upstream_collector 构建，被 Harness 消费

### Orchestrator
长任务模式下的主 Agent 角色。只负责读 state → 决定下一个 Phase → 构造 SubAgent prompt → 收集结果。禁止自己执行 Skill。
- _Avoid_: "coordinator"（Orchestrator 有决策权，不只是协调）
- Relationships: Orchestrator 派发 SubAgent，SubAgent 执行 Skill

### DAG
Phase 间的有向无环图依赖关系。决定哪些 Phase 可并行、哪些必须串行。
- _Avoid_: "pipeline"（DAG 允许并行分支，pipeline 暗示线性）
- Relationships: DAG Scheduler 根据依赖图 + Preflight 结果调度执行

### Preflight
DAG 执行每个 Phase 前的预检。检查 checkpoint、依赖完成、上游产物存在性、级联失败等。任一 FAIL 项阻断执行。
- _Avoid_: "pre-check"（Preflight 是正式的阻断机制，不是建议性检查）

### RunStatus
Phase 执行结果的 5 值枚举：ok / timeout / adapter_crashed / parse_failed / tainted。区分 infra failure（不计入质量评分）和 logic failure（计入）。
- _Avoid_: "status"（RunStatus 特指执行结果分类，不是 Phase 生命周期状态）

### PhaseGuardrail
语义级防护。在 Finalize 后并发执行，检测 BR 概括性描述、覆盖度虚高、跨 Phase 越权等语义问题。
- _Avoid_: "validator"（Guardrail 检测语义层面的问题，不是格式校验）

### Rationalization Guard
Judge 放水检测器。识别 Judge 评分中的合理化倾向（"虽然...但可以接受"），触发 rejudge。同时检测过严误报。
- _Avoid_: "bias detector"（专注于 rationalization 这一特定认知偏差）

### EnumSource / EnumContract
枚举单一真源。定义 severity、id 正则、状态机等枚举在 schema / prompt / 示例中的唯一权威值，由 `context/enum_contract.py::render_enum_contract_prefix` 渲染为 `ENUM_CONTRACT` 节注入到 skill prompt 头部，与 Pydantic schema 同源。
- _Avoid_: "枚举表"、"常量表"（EnumSource 强调"唯一真源"和"跨文档同源"两个属性）
- Relationships: 解决 Skill 示例 ≠ Schema required 的"两张皮"问题；T8 Schema↔Prompt 一致性 CI 以 EnumSource 作为比对基准

### Q05BranchCoverageGuardrail
Q05 Phase 专属的 PhaseGuardrail。校验 EUT 对业务方法各分支（happy / 边界 / 异常 / 并发）的覆盖率，关键方法（含 throws / try-catch）必须 ≥1 条异常分支 EUT，否则 BLOCKED。配合 Q05 三步生成范式（分支枚举 → 业务后果映射 → 断言对准）使用。
- _Avoid_: 与通用 PhaseGuardrail 混用（这是 Q05 专属挂载，只在 `get_phase_guardrails("Q05")` 时生效）
- Relationships: 由 T6 Q05 范式改造引入；T12 bug 回归实验的验收依赖它真能拦住 no-exception-test

### RationalizationProbeGuardrail
字段级合理化拦截器。在 Q03/Q06 的 `PhaseGuardrail` 中对自由文本字段（business_path、failure_scenario、finding.message）扫描合理化话术（"虽然... 但是..."、"按常识...")，与对话层的 RationalizationGuard 形成互补。
- _Avoid_: 与 Rationalization Guard 混为一体（前者作用在"字段"，后者作用在"Judge 对话"）
- Relationships: 由 T11 引入，挂载在 `get_phase_guardrails("Q03"|"Q06")`

### Guard Precision Report
Guard 精度周报。聚合 `output/*/_guardrail_results.json`，按 guard 维度统计"拦对/拦错/漏拦"三态，输出到 `docs/*/guard_precision.md`。命令 `dqg-run observe guard-precision`，finalize 后自动刷新。
- _Avoid_: "guardrail 报告"（此处特指精度三态观测，非单次 guardrail 执行结果）
- Relationships: 由 T9 引入；是 DoD "上线后"维度的观测数据源之一

## Flagged Ambiguities

| 术语 | 歧义场景 | 裁决 |
|------|---------|------|
| Skill | DQG Phase Skill vs Claude Code superpowers skill | 在 DQG 语境下默认指 Phase Skill；提及 Claude Code 能力时必须加前缀 "superpowers skill" |
| Agent | Orchestrator/SubAgent vs Claude Code agent tool | 在 DQG 语境下指 Orchestrator 或 SubAgent；提及工具时用 "Agent tool" |
| Pipeline | DQG 执行流水线 vs CI/CD pipeline | DQG 语境下指 Phase DAG 执行流；CI/CD 时必须明确说 "CI pipeline" |
| Profile | DQG 项目配置集 vs 用户 profile | DQG 语境下指项目配置集；其他场景需加限定词 |
| Gate | 质量门禁（概念）vs gate_verdict.py（实现）| 讨论概念用 "Gate"，讨论实现用 "GateVerdict" |

*最后更新：2026-05-09*
