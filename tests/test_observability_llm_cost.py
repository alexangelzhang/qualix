"""P1: observe 报告中的 llm_calls 成本聚合."""

from __future__ import annotations

from datetime import datetime

from dqg.reporting.observability import _build_prompt_effectiveness
from dqg.reporting.telemetry import PhaseRunRecord


def test_build_prompt_effectiveness_includes_cost_usd() -> None:
    now = datetime.now().isoformat()
    rec = PhaseRunRecord(
        project_id="proj-cost",
        phase_id="Q03",
        phase_name="x",
        action="finalize",
        timestamp=now,
        llm_calls=[
            {
                "model_id": "claude-test",
                "prompt_hash": "abc",
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_hit": False,
                "prompt_excerpt": "peek",
            },
        ],
    )
    pe = _build_prompt_effectiveness([rec])
    assert pe["cost_total_usd"] > 0
    row = pe["token_distribution"][0]
    assert row["cost_usd"] > 0
    assert row["phase_id"] == "Q03"
    assert pe["payload_sample_calls"] == 1
