"""P2: trace span enrichment."""

from __future__ import annotations

from qualix.reporting.observability import _build_trace_summary
from qualix.reporting.telemetry import PhaseRunRecord
from qualix.reporting.trace_spans import enrich_llm_call_span


def test_enrich_llm_call_span_path() -> None:
    base = {"model_id": "m", "prompt_hash": "ab"}
    out = enrich_llm_call_span(
        base,
        project_id="proj",
        phase_id="Q05",
        iteration=2,
        agent_step="worker",
        trace_run_id="runxyz",
        llm_index=0,
    )
    assert out["trace_run_id"] == "runxyz"
    assert out["span_path"] == "Q05/iter2/worker"
    assert out["span_parent"] == "Q05/iter2"
    assert out["span_root"] == "proj/Q05"


def test_build_trace_summary_counts_paths() -> None:
    rec = PhaseRunRecord(
        project_id="p",
        phase_id="Q01",
        phase_name="",
        action="finalize",
        llm_calls=[
            {"span_path": "Q01/iter1/worker", "trace_run_id": "a"},
            {"span_path": "Q01/iter1/worker", "trace_run_id": "a"},
            {"span_path": "Q01/iter1/judge:m", "trace_run_id": "a"},
        ],
    )
    s = _build_trace_summary([rec])
    assert s["unique_trace_runs"] == 1
    assert any(x["path"] == "Q01/iter1/worker" and x["count"] == 2 for x in s["span_paths"])
