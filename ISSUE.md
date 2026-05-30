# ISSUE.md — 变更记录

## 2026-05-09 — 系统健康报告可执行任务（T1–T12）

来源：`docs/system-health-reports/2026-05-09.md` 第六节。

**状态二维定义**（避免"代码 done"与"验收 done"混为一谈）：
- `code`：实现落地（模块/脚本/配置到位），跑得通
- `verified`：**代码 done + 拿到重跑数据，验收标准全部命中**（DoD "上线后"维度，见 §本周失败量快照）
- `todo` / `doing`：未开始 / 进行中

### 任务清单

| ID | 任务 | 档位 | 周数 | Owner | 交付物 | 依赖 | 代码 | 验收 |
|----|------|------|------|-------|-------|------|------|------|
| T1 | Q03 failure_modes schema + prompt 必填清单 | P0 | 0.5 | zhangyiqian3 | schema 修正 + Q03 skill prompt 必填表 | — | code | verified |
| T2 | Q06 findings schema + prompt 必填清单 | P0 | 0.5 | zhangyiqian3 | `skills/unit-test-audit/references/phase_c_structured.schema.json` + Q06 skill 必填表 | — | code | todo |
| T3 | Q05→Q06 EUT ID 子集硬约束 | P0 | 0.5 | zhangyiqian3 | `cross_phase_check.validate_eut_id_subset` | — | code | verified |
| T4 | 失败案例库 lesson 补齐 + case_category 五类 | P0 | 1 | zhangyiqian3 | `case_category.py`、`lesson_inference` 扩展、`scripts/backfill_failure_case_lessons.py`（全库 `--apply` 完成） | — | code | verified |
| T5 | Q05 剩余结构合规 validator（mock_wrong / mock_phantom_method / eut_missing_se / wrong_directory；compile_fail 由 `test_execution_gate` 兜底） | P0 | 2 | zhangyiqian3 | `q05_structure_checks.py` + 接入 `finalize_checks` | T4 | code | todo |
| T6 | Q05 生成范式三步改造 + Guardrail 分支覆盖 | P1 | 3 | zhangyiqian3 | `references/q05-three-step-paradigm.md` + SKILL 三步节 + `Q05BranchCoverageGuardrail` | T5 | code | **todo**（见下方 §回写要求） |
| T7 | 统一枚举源 EnumSource + prompt 注入 | P1 | 0.5 | zhangyiqian3 | `context/enum_contract.py`；`resolve_worker_prompt` / `generate_worker_prompt` 注入 | — | code | verified |
| T8 | Schema↔Prompt 一致性 CI | P1 | 1 | zhangyiqian3 | `scripts/check_schema_prompt_sync.py` + `.pre-commit-config.yaml` hook | T7 | code | verified |
| T9 | Guard 精度仪表盘 | P1 | 1.5 | zhangyiqian3 | `reporting/guard_precision_report.py` + `observe guard-precision` 命令 + `docs/.../guard_precision.md` | T1–T5 有一周稳定运行数据 | code | todo |
| T10 | Failure → Reflector 自动回流 | P2 | 1 | zhangyiqian3 | `scripts/reflect_case.py` + 采集钩子 | T4 | code | todo |
| T11 | RationalizationProbe 字段级 | P2 | 2 | zhangyiqian3 | `PhaseGuardrail::RationalizationProbe` | — | code | verified |
| T12 | Q05 生产 bug 回归实验 | P2 | 2 | zhangyiqian3（需业务方提供 bug 列表） | 3 项目 × 10 条历史 bug 重跑报告（路径：`observability/reports/q05-bug-regression/{project}.md`） | T6 | **todo** | **todo**（见下方 §回写要求） |

### 依赖图

实现前应该先有这张图，这次补上作为下次立项的标准动作。

```
T1 ─┐
T2 ─┤ (并行 P0 首周收尾，三条独立)
T3 ─┘

T4 ──┬──► T5 (Q05 结构合规五 validator)
     │
     └──► T10 (Reflector 需 T4 的 case_category 语料)

T5 ──► T6 (Q05 范式改造复用 T5 的校验基座)
       │
       └──► T12 (bug 回归只能测新范式)

T7 ──► T8 (CI 的 required 字段来自 EnumSource)

T1–T5 稳定一周 ──► T9 (精度仪表盘要有样本才有数)

T11 独立（RationalizationProbe 字段级护栏）
```

### DoD（"上线后"维度）

代码落地不等于目标达成。每项任务的"验收"必须附带下面两类证据之一：

1. **重跑数据**：对应失败类型在 N 个历史项目上重跑后的新发案例数，对照 §量化目标（报告 §6.3）
2. **观测数据**：该任务上线后 ≥7 天的 `observability/reports/` 日报里对应 Phase 的 `validation_error_count` / `failure_rate`

**没有这两类证据，状态只能停在 `code`，不能标 `verified`。** 这是这次 review 最关键的一条改进。

### 验收证据（verified 任务的证据链）

- **T1 (verified)**：schema 落地 + Q03 SKILL 必填清单，T8 hook 首次运行即拦住 Q06 SKILL 缺节（证明机制能实际拦错）。失败量快照：Q03 自 2026-04-27 后 0 条新增
- **T3 (verified)**：`validate_eut_id_subset` 接入 `finalize_checks`，`test_cross_phase_check` 覆盖 phase_b 缺失 / eut_items 空 / phantom 引用三条边界路径。Q06 phantom EUT 类 2026-04-29 后 0 条新增
- **T4 (verified)**：`backfill_failure_case_lessons.py --apply` 对 1776 条历史 case 回填 lesson + case_category（commit `da6b1a5`），lesson 空率 98.3% → 0；`test_case_category` 通过
- **T7 (verified)**：`render_enum_contract_prefix` 注入到 `skill_loader.load_skill_progressive` 和 `agents/multi_agent.py` 两处；`test_enum_contract` 通过
- **T8 (verified)**：hook 初版 `language:python` 启隔离 venv 不能 import dqg，**首次实战即被发现并修为 `language:system`**（commit `c85ce5b` 附带补丁）；随后分别拦住 `q05_branch_coverage.py` 和 `guard_precision_report.py` 的 `json.load` 架构违规
- **T11 (verified)**：`RationalizationProbeGuardrail` 通过 `get_guardrails("Q03"|"Q06")` 分派挂载；`test_rationalization_probe_guardrail` 通过

### 仍需回写（code → verified 缺的证据）

- **T2**：schema / 必填清单已就位，但 Q06 2026-05-07 仍有 19 条 findings 缺字段类失败（commit `7b3970d`）。需在 shuangzhou-v4 05-09 后重跑一次确认归零
- **T5**：`q05_structure_checks.py` 接入 + 测试通过，但 Q05 自 2026-04-29 起 0 条新增很可能是"没跑"而非"止血"（见下方 §本周失败量快照免责声明），需下次规模化跑批确认
- **T9**：guard 精度报告可产出，但 `docs/system-health-reports/guard_precision.md` 需至少 7 天稳定观测数据才能说"三态均有样本"，目前刚上线
- **T10**：Reflector 脚手架就位，`test_case_reflect` 通过，但新采集 case 自动填充率 ≥95% 的口径未跑实际数据

### 回写要求（T6 / T12 阻塞 `verified`）

- **T6**：需提供 3 个项目（finance-model、shuangzhou-v4、store-ops）重跑后的 `no-exception-test` 新发数、关键方法异常分支 EUT 覆盖率。未回写前状态保持 `code`
- **T12**：需提供 `observability/reports/q05-bug-regression/{project}.md` 三份报告，包含"能复现 bug 的 EUT 占比"。低于 20% 触发止损线（报告 §6.3），需升级决策

### 本周失败量快照

基线统计口径：`regression/failure-library/cases/{Phase}/*/case.json` 的 `created_at` 字段聚合。

| Phase | 三周累计（至 05-09） | 最后新增日期 | 最后单日新增 | 5 月起累计 | 备注 |
|-------|---------------------|--------------|--------------|------------|------|
| Q01 | 92 | 2026-05-06 | 86 | 86 | bitable 解析问题集中涌现（T1+T5 治理） |
| Q03 | 969 | 2026-04-27 | — | 0 | 4-27 后无新增（需确认是"止血"还是"没跑"） |
| Q04 | 11 | 2026-04-28 | — | 0 | 4-28 后无新增 |
| Q05 | 225 | 2026-04-29 | — | 0 | 4-29 后无新增（同上，待 T12 回归实验验证） |
| Q06 | 352 | 2026-05-07 | 19 | 19 | shuangzhou-v4 findings 缺字段问题（T2 治理） |
| Q07 | 127 | 2026-04-24 | — | 0 | 4-24 后无新增 |

**重要免责声明**：5 月之后新增案例稀少有两种可能——(a) P0 阶段 guard 上线后真止血；(b) 窗口内没有规模化跑批，所以没有新失败机会。需要结合 `observability/reports/daily/` 的项目运行频次判断，不能直接归因为治理生效。

### 下一步（回到立项标准动作）

1. **本周内**：T6 / T12 回写重跑数据，把状态从 `code` 推进到 `verified`
2. **每周例会**：把上面的"本周失败量快照"表更新一次，对照报告 §6.3 量化目标，看曲线是否按 +4 周 / +8 周 / +12 周节奏下降
3. **下一轮立项**：依赖图和 DoD 在任务清单建好时就画（而非做完后补），Owner 直接写实名

---


## 2026-04-02

### 新增能力

- **LLM-as-Judge 自动评审** — `finalize` 后自动生成 `_judge_prompt.md`，支持 Phase Q01/Q04/Q03/Q06 四个阶段的独立评审，输出 precision/recall 估计和问题列表。CLI: `qualix-run <project> judge <phase>`
- **Self-Critique + RLAIF 融合闭环** — Phase 执行后自我批评生成 v2，偏好比较判定哪个更好，有效 critique 自动沉淀为 bug case。CLI: `qualix-run <project> critique <phase>` / `qualix-run <project> preference <phase>`
- **Bug 案例库** — 按 Phase 分类的结构化案例库（case.json + input.md），支持归因（SKILL_RULE/KNOWLEDGE/CONTEXT/SCHEMA）和修复路径建议。CLI: `qualix-run PROJ regression run` / `python -m dqg.tracking.bug_cases`
- **案例自动注入** — skill 执行时基于上游产物内容做相关性匹配，只注入相关案例为反例，token 节省 77%
- **案例批量导入** — 从飞书 Bitable 批量导入 bug 案例。CLI: `python -m dqg.tracking.import_bug_cases <ingest.json>`
- **飞书多维表格（Bitable）解析** — Wiki 节点 obj_type=bitable 时自动走 bitable 路径，遍历所有 sheet 读取全量记录
- **多平台支持** — 新增 `AGENTS.md`（Codex/opencode/IntelliJ）、`GEMINI.md`（Gemini CLI）、`.cursor/rules/dqg.mdc`（Cursor）
- **规则级质量追踪** — `finalize` 时比对结构化输出与 bug 案例库，输出健康度分数和命中的已知问题模式
- **自动修复闭环** — `finalize` 发现 validation errors 时自动生成 bug case 并建议 prompt 修改

### 优化

- **目录结构重构** — 输出路径从 `output/{id}_phaseA/` 改为 `output/{id}/phaseA/`，state.json 移入项目子目录。涉及 12 个源文件 + 5 个测试文件 + 3 个 skill 文档
- **飞书图片并发下载** — ThreadPoolExecutor 8 workers，预计提速 5-8x
- **飞书引用文档并发抓取** — 同层级文档 4 workers 并发，根文档串行
- **飞书单文档 API 并发** — get_meta + get_content + fetch_raw_content 三个请求并发
- **异常矩阵扩展** — `references/risk-and-exception-catalog.md` 从 38 行扩展到 364 行，每个风险/异常类型补充了 Java DDD+TMF 场景的触发条件、代码信号、判定规则
- **测试覆盖** — 从 85 个用例增加到 129 个

### 修复

- **飞书权限错误诊断** — Wiki 节点解析失败时给出具体排查步骤（区分 403/401/空响应），`call_with_token_fallback` 增加 user_access_token_not_supported 快速跳过
- **state.json 写入失败** — `save_state` 改为 `path.parent.mkdir(parents=True)` 确保项目子目录存在
- **regression case 路径** — `rights-platform` 的 case.json include 路径未更新为新目录结构（待更新）

## 2026-04-01

### 新增

- 87 条真实 bug 案例从飞书 Bitable 导入（Phase Q06: 56, Phase Q01: 22, Phase Q03: 6, Phase Q04: 1）
- 4 条手动创建的示例案例（并发幂等、覆盖度错判、RPC 无补偿、弱断言）

## 待办（文档债）

### 2026-05-08

- ~~**缺少 phase_c_structured.schema.json**~~ — 已于 2026-05-09 补充：`skills/unit-test-audit/references/phase_c_structured.schema.json`。
- **缺少 phase_b_structured.schema.json（Q05）** — 原备注把它挂在 T5 范围下不准确（T5 是 validator，不是 schema 文档）。独立为 **T13（P1，0.5 周）**：补一份 Q05 输出层 schema 文档，配合 T7 EnumSource 做硬约束。

## 2026-05-10 — Skill 治理发现的架构缺陷（T14）

来源：本 session 对 skills/ 目录结构治理 + Q05/Q06 failure-library 归类分析。

### T14：adaptive_loop schema 校验反馈回路（P1，2 周）

**现状**：Pydantic schema 校验只在 finalize 阶段（`phase_runtime.py:210`）执行，错误写入 telemetry/state 但**不回流到 adaptive_loop 的下一轮 iteration**。agent 在 loop 内永远看不到 schema 错误，下轮继续用同样方式产 JSON，schema 校验失败 → 无限循环。

**证据**：
- failure-library 抽样 20 个 Q05/Q06 case 归类，Q06 约 30% 是 E 类（schema 校验失败、修的是 schema 字段而非 skill 规则）
- `grep validate_phase_output src/dqg/agents/` → 0 命中，确认 adaptive_loop 完全不调用校验
- `grep "iteration|feedback|judge_result.issues" src/dqg/agents/adaptive_loop.py` → 0 命中，确认 loop 无 per-iteration feedback 机制

**实施要点**（详见 memory `deliverable_dqg_p2_schema_feedback_loop.md`）：
1. 在 `adaptive_loop._execute_iteration` 里 worker 产出后立即调 `validate_phase_output`
2. schema errors 注入 Judge rubric，让 judge 把 schema 违规当 issue
3. 下轮 worker prompt 拼接"上轮 schema 错误：..."引导修复
4. `IterationRecord` 新增 `schema_errors: list[str]` 字段
5. 不改 schema 定义、不改 finalize 卡控、不改性能

**预估**：200-350 行代码改动 + 2-3 个新测试。

**依赖**：本 session 已完成的 Q05/Q06 SKILL.md 规则侧改进（contract 提前、severity 歧义消除、Q05 补 4 条覆盖判定规则），形成"规则+反馈"闭环。

**验收**：Q06 iteration 1 缺 `findings[0].severity` 时，iteration 2 的 worker prompt 必须看到该错误且大概率补齐；finalize 阶段 `validate_phase_output` 作为最后防线不变。

## 2026-05-19 — simplify 时跳过的低优先级技术债（T15–T16）

### T15：Q01 finalize 跨函数双读 plain_text.txt（P2，0.5 周）

**现状**：`auto_derive_checks` 对 Q01 依次调用 `_save_se_source_evidence` 和 `_check_source_line_reality`，两个函数各自独立读取 `plain_text.txt` 和 `phase_a_structured.json`，导致同一 finalize 流程中两文件被读 2 次。

**原因跳过**：finalize 是一次性操作，文件通常 <1MB，非热路径，当前无可观测性能影响。

**修复思路**：提取 `_Q01Context(pd, phase_id)` 数据类，一次加载 `prd_lines` 和 `data`，作为参数传入两个函数。预估 30-50 行改动，零逻辑变更。

**验收**：`plain_text.txt` 在单次 `auto_derive_checks` 调用中只读一次（可用 `unittest.mock.patch` 断言调用次数）。

### T16：phase.py 三键 synthetic 检测收束（P2，0.5 周）

**现状**：`cmd_approve` 检查 judge_result 是否自动合成时查三个 key：`auto_synthesized`、`synthesis_source`、`synthetic`，历史扩张导致消费侧分散。

**原因跳过**：消费侧收束到单 key 需先改 `judge_runner.py` 写入侧，确保新旧产物向后兼容，超出本次 scope。

**修复思路**：`judge_runner.py` 写入时统一输出 `auto_synthesized: bool`，废弃 `synthesis_source` 和 `synthetic` 字段；`cmd_approve` 改为只读 `auto_synthesized`；加迁移期兼容（读不到 `auto_synthesized` 时 fallback 读旧字段）。

**验收**：`judge_runner.py` 产出的 judge_result 只含 `auto_synthesized`；`cmd_approve` 只读一个 key；旧格式 judge_result 不触发误报。
