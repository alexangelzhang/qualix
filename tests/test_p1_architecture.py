from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from qualix.agents.adaptive_loop import multi_judge_vote
from qualix.cache.semantic_cache import cache_get, cache_invalidate, cache_put
from qualix.constants import MEMORY_INDEX_STATE_FILE
from qualix.core.state_machine import PHASE_DEFS
from qualix.memory.memory_layer import MemoryLayer
from qualix.store import get_connection

if TYPE_CHECKING:
    from pathlib import Path


def test_multi_judge_vote_runs_in_parallel_and_preserves_model_order(monkeypatch, tmp_path: Path) -> None:
    """Primary judge-a PASS_WITH_CONCERNS(3.5) → boundary triggers secondary.

    'broken' secondary raises RuntimeError (subprocess failure) → skipped.
    'judge-b' secondary returns FAIL(2.0).
    Tests that multi_judge_vote collects valid secondary votes and skips broken ones.
    Now uses subprocess dispatch: mock _run_single_judge directly.
    """
    from qualix.agents.judge_vote import JudgeVote

    report_path = tmp_path / "report.md"
    report_path.write_text("# report", encoding="utf-8")

    called_models: list[str] = []

    def _fake_run_single_judge(output_dir, report_path, rubric, model, fallback, warning_override=None):
        called_models.append(model)
        if model == "broken":
            raise RuntimeError("judge exploded")
        overall = 3.5 if model == "judge-a" else 2.0
        verdict = "PASS_WITH_CONCERNS" if model == "judge-a" else "FAIL"
        return JudgeVote(
            model=model,
            scores={"quality": int(overall)},
            overall=overall,
            verdict=verdict,
            issues=[],
            duration=0.01,
            raw_output="",
            health="HEALTHY",
            token_usage={"input_tokens": 10, "output_tokens": 5},
        )

    monkeypatch.setattr("qualix.agents.judge_vote._run_single_judge", _fake_run_single_judge)

    result = multi_judge_vote(
        tmp_path,
        report_path,
        "judge rubric",
        ["judge-a", "broken", "judge-b"],
        fallback="fallback-model",
    )

    # judge-a is primary; score=3.5 in boundary → secondary triggered
    assert "judge-a" in called_models
    assert "judge-a" in [vote.model for vote in result.votes]
    # broken secondary must be skipped (RuntimeError caught)
    assert "broken" not in [vote.model for vote in result.votes]
    # judge-b secondary should be collected
    assert "judge-b" in [vote.model for vote in result.votes]
    # consensus from judge-a(PASS_WITH_CONCERNS) + judge-b(FAIL)
    assert result.consensus in ("FAIL", "PASS_WITH_CONCERNS")
    assert result.avg_score > 0


def test_semantic_cache_respects_cache_versions_and_targeted_invalidation(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    cache_put(output_dir, "权限校验", [{"id": 1}], result_type="fact", project_id="demo", cache_version="sig-a")
    cache_put(output_dir, "权限校验", [{"id": 2}], result_type="fact", project_id="demo", cache_version="sig-b")

    assert cache_get(output_dir, "权限校验", result_type="fact", project_id="demo", cache_version="sig-a") == [
        {"id": 1}
    ]
    assert cache_get(output_dir, "权限校验", result_type="fact", project_id="demo", cache_version="sig-b") == [
        {"id": 2}
    ]
    assert cache_get(output_dir, "权限校验", result_type="fact", project_id="demo", cache_version="sig-c") is None

    deleted = cache_invalidate(output_dir, project_id="demo", result_type="fact", cache_version="sig-a")
    assert deleted == 1
    assert cache_get(output_dir, "权限校验", result_type="fact", project_id="demo", cache_version="sig-a") is None
    assert cache_get(output_dir, "权限校验", result_type="fact", project_id="demo", cache_version="sig-b") == [
        {"id": 2}
    ]

    with get_connection(output_dir) as conn:
        rows = conn.execute("SELECT query_text FROM query_cache ORDER BY query_hash").fetchall()
    assert len(rows) == 1
    assert '"cache_version":"sig-b"' in rows[0]["query_text"]


def test_memory_layer_index_phase_skips_unchanged_inputs_and_reindexes_on_change(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_root = output_dir / "demo" / PHASE_DEFS["Q01"]["dir_suffix"]
    ingest_dir = phase_root / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    (phase_root / "phase_a_structured.json").write_text(
        json.dumps({"requirements": [{"req_id": "REQ-001", "description": "v1"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    (ingest_dir / "plain_text.txt").write_text("summary seed v1", encoding="utf-8")

    calls = {"facts": 0, "nodes": 0, "track": 0, "summary": 0, "invalidate": 0}

    def _fake_index_phase_facts(*args, **kwargs):
        calls["facts"] += 1
        return 3

    def _fake_index_project_facts(*args, **kwargs):
        calls["nodes"] += 1
        return 2

    def _fake_extract_facts_from_json(path: Path):
        return [{"fact_id": "REQ-001", "fact_type": "REQ", "description": path.read_text(encoding="utf-8")}]

    def _fake_track_version(*args, **kwargs):
        calls["track"] += 1
        return {"added": 1, "modified": 0, "removed": 0}

    def _fake_generate_summary_file(phase_dir: Path):
        calls["summary"] += 1
        summary_path = phase_dir / "ingest" / "plain_text_summary.md"
        summary_path.write_text("cached summary", encoding="utf-8")
        return summary_path

    def _fake_cache_invalidate(*args, **kwargs):
        calls["invalidate"] += 1
        return 0

    monkeypatch.setattr("qualix.memory.memory_layer.index_phase_facts", _fake_index_phase_facts)
    monkeypatch.setattr("qualix.memory.memory_layer.index_project_facts", _fake_index_project_facts)
    monkeypatch.setattr("qualix.memory.memory_layer.extract_facts_from_json", _fake_extract_facts_from_json)
    monkeypatch.setattr("qualix.memory.memory_layer.track_version", _fake_track_version)
    monkeypatch.setattr("qualix.memory.memory_layer.generate_summary_file", _fake_generate_summary_file)
    monkeypatch.setattr("qualix.memory.memory_layer.cache_invalidate", _fake_cache_invalidate)

    memory = MemoryLayer(output_dir)

    first = memory.index_phase("demo", "Q01")
    version_before = memory._project_fact_cache_version("demo")
    state_path = phase_root / "_internal" / MEMORY_INDEX_STATE_FILE

    second = memory.index_phase("demo", "Q01")

    assert second["skipped"] == 1
    assert second["signature_unchanged"] == 1
    assert second["reindexed"] == 0
    assert calls == {"facts": 1, "nodes": 1, "track": 1, "summary": 1, "invalidate": 1}

    time.sleep(0.001)
    (phase_root / "phase_a_structured.json").write_text(
        json.dumps({"requirements": [{"req_id": "REQ-001", "description": "v2 updated"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    third = memory.index_phase("demo", "Q01")
    version_after = memory._project_fact_cache_version("demo")

    assert first["reindexed"] == 1
    assert first["facts"] == 3
    assert first["knowledge_nodes"] == 2
    assert first["version_changes"] == 1
    assert state_path.exists()

    assert third["reindexed"] == 1
    assert third["version_changes"] == 1
    assert version_before != version_after
    assert calls == {"facts": 2, "nodes": 2, "track": 2, "summary": 2, "invalidate": 2}
