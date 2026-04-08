from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING

from dqg.agents.adaptive_loop import multi_judge_vote
from dqg.cache.semantic_cache import cache_get, cache_invalidate, cache_put
from dqg.constants import MEMORY_INDEX_STATE_FILE
from dqg.core.state_machine import PHASE_DEFS
from dqg.memory.memory_layer import MemoryLayer
from dqg.store import get_connection

if TYPE_CHECKING:
    from pathlib import Path


def test_multi_judge_vote_runs_in_parallel_and_preserves_model_order(monkeypatch, tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text("# report", encoding="utf-8")

    lock = threading.Lock()
    stats = {"active": 0, "max_active": 0}
    sleep_by_model = {"judge-a": 0.03, "judge-b": 0.01, "broken": 0.02}

    class _FakeAgent:
        def __init__(self, name: str, role: str, system_prompt: str, model, output_dir=None) -> None:
            del name, role, system_prompt, output_dir
            self.model_name = model.primary

        def run(self, user_message: str, context_files=None):
            del user_message, context_files
            with lock:
                stats["active"] += 1
                stats["max_active"] = max(stats["max_active"], stats["active"])
            try:
                time.sleep(sleep_by_model[self.model_name])
                if self.model_name == "broken":
                    raise RuntimeError("judge exploded")
                payload = {
                    "scores": {"quality": 5 if self.model_name == "judge-a" else 2},
                    "overall": 4.5 if self.model_name == "judge-a" else 2.0,
                    "verdict": "PASS" if self.model_name == "judge-a" else "FAIL",
                    "issues": [],
                }
                return SimpleNamespace(
                    status="success",
                    content=json.dumps(payload, ensure_ascii=False),
                    model_used=self.model_name,
                    duration_seconds=sleep_by_model[self.model_name],
                )
            finally:
                with lock:
                    stats["active"] -= 1

    monkeypatch.setattr("dqg.agents.adaptive_loop.Agent", _FakeAgent)

    result = multi_judge_vote(
        tmp_path,
        report_path,
        "judge rubric",
        ["judge-a", "broken", "judge-b"],
        fallback="fallback-model",
    )

    assert stats["max_active"] > 1
    assert [vote.model for vote in result.votes] == ["judge-a", "judge-b"]
    assert result.consensus == "PASS_WITH_CONCERNS"
    assert result.avg_score == 3.25


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
    phase_root = output_dir / "demo" / PHASE_DEFS["A"]["dir_suffix"]
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

    monkeypatch.setattr("dqg.memory.memory_layer.index_phase_facts", _fake_index_phase_facts)
    monkeypatch.setattr("dqg.memory.memory_layer.index_project_facts", _fake_index_project_facts)
    monkeypatch.setattr("dqg.memory.memory_layer.extract_facts_from_json", _fake_extract_facts_from_json)
    monkeypatch.setattr("dqg.memory.memory_layer.track_version", _fake_track_version)
    monkeypatch.setattr("dqg.memory.memory_layer.generate_summary_file", _fake_generate_summary_file)
    monkeypatch.setattr("dqg.memory.memory_layer.cache_invalidate", _fake_cache_invalidate)

    memory = MemoryLayer(output_dir)

    first = memory.index_phase("demo", "A")
    version_before = memory._project_fact_cache_version("demo")
    state_path = phase_root / "_internal" / MEMORY_INDEX_STATE_FILE

    second = memory.index_phase("demo", "A")

    assert second["skipped"] == 1
    assert second["signature_unchanged"] == 1
    assert second["reindexed"] == 0
    assert calls == {"facts": 1, "nodes": 1, "track": 1, "summary": 1, "invalidate": 1}

    time.sleep(0.001)
    (phase_root / "phase_a_structured.json").write_text(
        json.dumps({"requirements": [{"req_id": "REQ-001", "description": "v2 updated"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    third = memory.index_phase("demo", "A")
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
