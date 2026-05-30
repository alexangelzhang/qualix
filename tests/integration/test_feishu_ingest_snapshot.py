"""Integration snapshot tests for feishu ingest."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from qualix.ingest.feishu_ingest_snapshot import (
    assert_snapshot_case,
    build_snapshot_case_name,
    load_snapshot,
    normalize_snapshot_bundle,
    run_feishu_snapshot_case,
    save_snapshot,
)


def test_build_snapshot_case_name_prefers_explicit_case() -> None:
    assert build_snapshot_case_name("https://mi.feishu.cn/docx/ABC123", "rights-platform") == "rights-platform"


def test_build_snapshot_case_name_falls_back_to_doc_token() -> None:
    assert build_snapshot_case_name("https://mi.feishu.cn/docx/ABC123", None) == "docx_ABC123"


def test_normalize_snapshot_bundle_removes_volatile_fields() -> None:
    bundle = {
        "ingest.json": {
            "source": {
                "generated_at": "2026-01-01T00:00:00",
            },
            "assets": [
                {
                    "path": "/tmp/run/assets/image_a.png",
                    "attempts": [{"note": "fallback"}],
                }
            ],
        },
        "dependency_graph.json": {
            "generated_at": "2026-01-01T00:00:00",
            "nodes": [{"output_dir": "/tmp/run/doc"}],
        },
        "aggregate_ingest.json": {
            "generated_at": "2026-01-01T00:00:00",
            "dependency_graph_path": "/tmp/run/dependency_graph.json",
            "aggregate_plain_text_path": "/tmp/run/aggregate_plain_text.txt",
        },
        "plain_text.txt": "hello\n",
    }

    normalized = normalize_snapshot_bundle(bundle)

    assert "generated_at" not in normalized["ingest.json"]["source"]
    assert normalized["ingest.json"]["assets"][0]["path"] == "<normalized>"
    assert normalized["dependency_graph.json"]["nodes"][0]["output_dir"] == "<normalized>"
    assert normalized["aggregate_ingest.json"]["dependency_graph_path"] == "<normalized>"
    assert normalized["plain_text.txt"] == "hello\n"


def test_save_and_load_snapshot_round_trip(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    bundle = {
        "ingest.json": {"summary": {"doc_count": 1}},
        "plain_text.txt": "hello\n",
    }

    save_snapshot(snapshot_dir, "demo-case", bundle)
    loaded = load_snapshot(snapshot_dir, "demo-case")

    assert loaded == bundle
    assert json.loads((snapshot_dir / "demo-case" / "ingest.json").read_text(encoding="utf-8"))["summary"]["doc_count"] == 1
    assert (snapshot_dir / "demo-case" / "plain_text.txt").read_text(encoding="utf-8") == "hello\n"


def test_load_snapshot_raises_for_missing_case(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_snapshot(tmp_path / "snapshots", "missing-case")


def test_assert_snapshot_case_updates_snapshot_when_requested(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    actual = {"ingest.json": {"summary": {"doc_count": 2}}}

    assert_snapshot_case(snapshot_dir, "demo-case", actual, update=True)

    loaded = load_snapshot(snapshot_dir, "demo-case")
    assert loaded == actual


def test_assert_snapshot_case_fails_when_snapshot_differs(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshots"
    save_snapshot(snapshot_dir, "demo-case", {"ingest.json": {"summary": {"doc_count": 1}}})

    with pytest.raises(AssertionError, match="Snapshot mismatch for case: demo-case"):
        assert_snapshot_case(snapshot_dir, "demo-case", {"ingest.json": {"summary": {"doc_count": 2}}}, update=False)


def test_run_feishu_snapshot_case_collects_bundle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeClient:
        pass

    def fake_load_larkkit():
        return FakeClient, lambda _: "python"

    def fake_crawl_documents(**kwargs):
        output_dir = kwargs["output_dir"]
        (output_dir / "ingest.json").write_text(json.dumps({"summary": {"doc_count": 1}}), encoding="utf-8")
        (output_dir / "plain_text.txt").write_text("hello\n", encoding="utf-8")
        return {"nodes": [], "edges": []}

    monkeypatch.setattr("qualix.ingest.feishu_ingest_snapshot.load_larkkit", fake_load_larkkit)
    monkeypatch.setattr("qualix.ingest.feishu_ingest_snapshot.crawl_documents", fake_crawl_documents)

    bundle = run_feishu_snapshot_case("https://mi.feishu.cn/docx/ABC123", tmp_path / "run")

    assert bundle["ingest.json"]["summary"]["doc_count"] == 1
    assert bundle["plain_text.txt"] == "hello\n"


@pytest.mark.skipif(not os.getenv("DQG_FEISHU_TEST_URL"), reason="requires real Feishu test url")
def test_real_feishu_snapshot_replay(tmp_path: Path) -> None:
    url = os.environ["DQG_FEISHU_TEST_URL"]
    case_name = build_snapshot_case_name(url, os.getenv("DQG_FEISHU_SNAPSHOT_CASE"))
    snapshot_dir = Path(__file__).resolve().parents[1] / "fixtures" / "feishu_ingest_snapshots"

    bundle = run_feishu_snapshot_case(url, tmp_path / "real-run")
    assert_snapshot_case(
        snapshot_dir,
        case_name,
        bundle,
        update=os.getenv("DQG_UPDATE_SNAPSHOTS") == "1",
    )
