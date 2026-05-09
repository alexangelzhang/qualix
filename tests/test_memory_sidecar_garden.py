"""Memory sidecar L1 + Garden + trust + weighted walk."""

from __future__ import annotations

from pathlib import Path

from dqg.memory.garden import _polarity_clash, run_memory_garden
from dqg.memory.knowledge_network import add_link, upsert_node, walk_weighted_neighbors
from dqg.memory.sidecar_l1 import enqueue_memory_sidecar
from dqg.memory.trust_level import TrustLevel, recent_trust_summary, record_trust_event, trust_weight
from dqg.store import get_connection


def _init_db(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with get_connection(output_dir) as conn:
        conn.execute("SELECT 1")


def test_polarity_clash() -> None:
    assert _polarity_clash("必须支持退款", "禁止任何退款") is True
    assert _polarity_clash("必须支持退款", "应当支持退款") is False


def test_trust_weight_and_record(tmp_path: Path) -> None:
    out = tmp_path / "output"
    _init_db(out)
    assert trust_weight(TrustLevel.HIGH) == 1.0
    assert trust_weight("unknown_level_xyz") == trust_weight(TrustLevel.MEDIUM)
    record_trust_event(
        out,
        project_id="proj-x",
        phase_id="Q01",
        event_type="unit_test",
        trust_level=TrustLevel.LOW,
        payload={"k": 1},
    )
    rows = recent_trust_summary(out, project_id="proj-x", phase_id="Q01", limit=5)
    assert len(rows) == 1
    assert rows[0]["trust_level"] == "low"
    assert rows[0]["payload"] == {"k": 1}


def test_walk_weighted_neighbors(tmp_path: Path) -> None:
    out = tmp_path / "output"
    _init_db(out)
    upsert_node(out, "a:Q01:REQ1", "FACT", "[REQ] REQ1", content="x", project_id="a", phase_id="Q01")
    upsert_node(out, "b:Q02:REQ9", "FACT", "[REQ] REQ9", content="y", project_id="b", phase_id="Q02")
    add_link(out, "a:Q01:REQ1", "b:Q02:REQ9", "SIMILAR", strength=0.9, reason="test")
    hits = walk_weighted_neighbors(out, "a:Q01:REQ1", max_depth=2, max_nodes=10)
    ids = {h["node_id"] for h in hits}
    assert "b:Q02:REQ9" in ids


def test_sidecar_enqueue_and_garden_drain(tmp_path: Path) -> None:
    out = tmp_path / "output"
    _init_db(out)
    with get_connection(out) as conn:
        conn.execute(
            """INSERT INTO structured_facts (project_id, phase_id, fact_type, fact_id, description)
               VALUES ('p1','Q01','REQ','REQ-1','hello')"""
        )
        conn.execute(
            """INSERT INTO requirement_versions
            (project_id, phase_id, fact_id, fact_type, description, version, status,
             prev_description, change_type, valid_from)
            VALUES ('p1','Q01','REQ-1','REQ','old text',1,'superseded','','modified','2020-01-01')"""
        )
        conn.execute(
            """INSERT INTO requirement_versions
            (project_id, phase_id, fact_id, fact_type, description, version, status,
             prev_description, change_type, valid_from)
            VALUES ('p1','Q01','REQ-1','REQ','new text',2,'active','old text','modified','2020-01-02')"""
        )
    # knowledge node for current fact (as index_project_facts would)
    upsert_node(out, "p1:Q01:REQ-1", "FACT", "[REQ] REQ-1", content="new text", project_id="p1", phase_id="Q01")

    enqueue_memory_sidecar(out, project_id="p1", phase_id="Q01", fingerprint="fp1")
    report = run_memory_garden(out, max_queue_lines=50)
    assert report.get("queue_lines_consumed", 0) >= 1
    assert report.get("supersedes_links", 0) >= 1

    with get_connection(out) as conn:
        n = conn.execute("SELECT COUNT(*) FROM knowledge_nodes WHERE node_id LIKE 'memver:p1:Q01:%'").fetchone()[0]
        assert n >= 1
        lk = conn.execute(
            "SELECT COUNT(*) FROM knowledge_links WHERE link_type='SUPERSEDES' AND source_id='p1:Q01:REQ-1'"
        ).fetchone()[0]
        assert lk >= 1
