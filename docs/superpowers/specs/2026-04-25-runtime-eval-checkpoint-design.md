# Runtime Eval — Checkpoint Validation Design

> 在 Worker 执行中间和 Phase 间插入轻量验证，早期止损避免无效迭代。

## 背景

### 问题

DQG 当前是"跑完再审"模式：Worker 跑完整轮 → Judge 发现问题 → 整轮作废。
两个天然断点没有验证：

1. Two-Phase Worker：Collector 输出 evidence_pack 后无条件启动 Writer
2. DAG Phase 间：Preflight 只检查上游文件存在性，不检查内容质量

### 目标

在两个断点插入规则 + LLM 两层验证，不合格则阻断，避免下游浪费 token。

## 设计

### Checkpoint Validator 核心模块

统一验证逻辑，两个 checkpoint 位置复用：

```python
@dataclass
class CheckpointResult:
    passed: bool
    rule_checks: list[dict[str, Any]]
    llm_check: dict[str, Any] | None
    block_reason: str = ""

def validate_checkpoint(
    content: str,
    contract: dict[str, Any],
    phase_id: str,
    checkpoint_name: str,
) -> CheckpointResult:
```

两层验证：

| 层 | 成本 | 检查内容 | 触发条件 |
|----|------|---------|---------|
| 规则层 | 零 LLM | 非空、关键 ID 覆盖率、来源标注、JSON 可解析 | 始终 |
| LLM 层 | haiku 级 | "内容是否充分覆盖验证目标？" | 规则通过但覆盖率 < 80% |

LLM 层超时 10 秒，超时视为 PASS（不因 LLM 不可用阻断主流程）。

存储位置：`src/dqg/quality/checkpoint_validator.py`

### Checkpoint 1: Two-Phase Worker 断点

触发位置：`two_phase_worker.py` 的 `run_two_phase_worker()`，Collector 输出 `_evidence_pack.json` 之后、Writer 启动之前。

规则层检查：
- evidences 列表非空
- 每条 evidence 有 source 字段
- Phase Contract 的 verification_targets 中的 ID 至少 60% 出现在 evidence 中

LLM 层触发条件：覆盖率 60-80% 时用 haiku 确认关键目标是否被覆盖。

失败行为：返回 `{"status": "failed", "error": "Evidence pack checkpoint failed: ..."}`，不启动 Writer。调用方（adaptive_loop）看到 Worker 失败，进入下一轮修正或早停。

### Checkpoint 2: DAG Phase 间断点

触发位置：`preflight.py` 的 `run_preflight()`，在 `_check_upstream_artifacts`（文件存在性）之后新增 `_check_upstream_quality`（内容质量）。

规则层检查：
- structured JSON 中 core arrays（REQ/BR/SE/EUT 等）数量 ≥ Phase Contract 最低阈值
- 报告长度 ≥ 最低字数（防截断报告流入下游）
- 报告包含必要章节标题（从 Phase Contract done_definition 提取关键词匹配）

LLM 层触发条件：规则通过但 core array 数量可疑（低于历史均值 50%）时触发。

失败行为：`PreflightResult.can_continue = False`，DAG 调度器不启动该 Phase。与现有 cascade_failure 阻断模式一致。

### 改动范围

| 文件 | 改动 |
|------|------|
| 新建 `quality/checkpoint_validator.py` | CheckpointResult + validate_checkpoint() + 规则检查 + LLM 确认 |
| 修改 `agents/two_phase_worker.py` | Collector → Writer 之间插入 validate_checkpoint |
| 修改 `runtime/preflight.py` | 新增 _check_upstream_quality()，调用 validate_checkpoint |
| 新建 `tests/test_checkpoint_validator.py` | 规则检查 + LLM fallback + 超时处理测试 |
| 新建 `tests/test_checkpoint_integration.py` | 端到端集成测试 |

### 不做的事

- 不改 adaptive_loop 的迭代逻辑（checkpoint 失败通过现有 Worker failed 路径处理）
- 不改 Judge/Critique 流程（checkpoint 是 pre-Judge 验证，不替代 Judge）
- 不加 checkpoint 到单次 LLM 调用内部（Worker 是一次调用，没有中间状态）
- 不改 Phase Contract 生成逻辑（复用现有 contract 数据）

### 风险

| 风险 | 缓解 |
|------|------|
| 规则检查误阻断（正常内容被拦） | 阈值保守（60% 覆盖率），LLM 层做二次确认 |
| LLM 层超时导致延迟 | 10 秒硬超时，超时 = PASS |
| Phase Contract 不存在时无法验证 | contract 为空时跳过 checkpoint（退化为现有行为） |

*设计日期: 2026-04-25*
