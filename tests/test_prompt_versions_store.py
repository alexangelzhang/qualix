"""P2: prompt_versions SQLite."""

from __future__ import annotations

from qualix.store.prompt_versions import query_prompt_versions, record_prompt_snapshot


def test_record_prompt_snapshot_versions(tmp_path) -> None:
    out = tmp_path / "output"
    v1 = record_prompt_snapshot(
        out,
        prompt_hash="deadbeef",
        prompt_text="first body",
        agent_name="w",
        agent_role="worker",
        trace_run_id="tr1",
    )
    assert v1 == 1
    v2 = record_prompt_snapshot(
        out,
        prompt_hash="deadbeef",
        prompt_text="second body",
        agent_name="w",
        agent_role="worker",
        trace_run_id="tr2",
    )
    assert v2 == 2
    v_dup = record_prompt_snapshot(
        out,
        prompt_hash="deadbeef",
        prompt_text="second body",
        agent_name="w",
        agent_role="worker",
        trace_run_id="tr2",
    )
    assert v_dup is None
    rows = query_prompt_versions(out, prompt_hash="deadbeef", limit=10)
    assert len(rows) == 2
