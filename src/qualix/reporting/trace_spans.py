"""P2: LLM 调用分层 trace 元数据（Phase → Iteration → Agent → LLM call）.

写入 `llm_calls[]` 条目的扁平字段，便于 JSONL/SQLite 查询与聚合；不引入 OpenTelemetry 依赖。
"""

from __future__ import annotations

from typing import Any


def enrich_llm_call_span(
    call: dict[str, Any],
    *,
    project_id: str,
    phase_id: str,
    iteration: int | None,
    agent_step: str,
    trace_run_id: str,
    llm_index: int = 0,
) -> dict[str, Any]:
    """为单条 llm_calls 记录附加 span 字段（返回新 dict）."""
    out = dict(call)
    if iteration is None:
        iter_seg = "single"
        parent = phase_id
    else:
        iter_seg = f"iter{int(iteration)}"
        parent = f"{phase_id}/{iter_seg}"
    agent_seg = agent_step.replace("/", "_")
    out["trace_run_id"] = trace_run_id
    out["span_root"] = f"{project_id}/{phase_id}"
    out["span_iteration"] = iteration
    out["span_agent"] = agent_step
    out["span_parent"] = parent
    out["span_path"] = f"{phase_id}/{iter_seg}/{agent_seg}"
    out["span_depth"] = 3 if iteration is not None else 2
    out["llm_index"] = llm_index
    return out
