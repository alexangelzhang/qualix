"""Tests for Evidence Contract verifiers (SE.source / EUT code_target / Q06 COVERED)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_ingest_file(tmp_path: Path, filename: str, lines: list[str]) -> None:
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    (ingest_dir / filename).write_text("\n".join(lines), encoding="utf-8")


def _make_ctx(tmp_path: Path, phase_id: str = "Q01"):
    ctx = MagicMock()
    ctx.output_dir = tmp_path
    ctx.project_id = "test"
    ctx.phase_id = phase_id
    ctx.phase_root = tmp_path / "test" / phase_id
    ctx.phase_root.mkdir(parents=True, exist_ok=True)
    ctx.internal_dir = ctx.phase_root / "_internal"
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    ctx.shared = {}
    return ctx


def _make_result():
    r = MagicMock()
    r.errors = []
    return r


# ---------------------------------------------------------------------------
# Task 1: verify_se_sources
# ---------------------------------------------------------------------------


def test_verify_se_sources_ok(tmp_path):
    """source='plain_text.txt:2' 指向真实行 → status=ok, no errors."""
    from qualix.quality.checks.evidence_contract import verify_se_sources

    _write_ingest_file(tmp_path, "plain_text.txt", ["line1", "line2 PRD内容", "line3"])
    se_list = [{"se_id": "SE-001", "source": "plain_text.txt:2"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert errors == []
    assert len(entries) == 1
    assert entries[0]["status"] == "ok"
    assert entries[0]["line_text"] == "line2 PRD内容"


def test_verify_se_sources_empty_source(tmp_path):
    """source='' → status=empty_source, WARNING."""
    from qualix.quality.checks.evidence_contract import verify_se_sources

    se_list = [{"se_id": "SE-002", "source": ""}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("WARNING" in e for e in errors)
    assert entries[0]["status"] == "empty_source"


def test_verify_se_sources_file_missing(tmp_path):
    """source='nonexist.txt:1' 文件不存在 → BLOCKED."""
    from qualix.quality.checks.evidence_contract import verify_se_sources

    se_list = [{"se_id": "SE-003", "source": "nonexist.txt:1"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("BLOCKED" in e for e in errors)
    assert entries[0]["status"] == "file_missing"


def test_verify_se_sources_line_oob(tmp_path):
    """source='plain_text.txt:999' 行号超出 → BLOCKED."""
    from qualix.quality.checks.evidence_contract import verify_se_sources

    _write_ingest_file(tmp_path, "plain_text.txt", ["only one line"])
    se_list = [{"se_id": "SE-004", "source": "plain_text.txt:999"}]
    errors, entries = verify_se_sources(tmp_path, se_list)
    assert any("BLOCKED" in e for e in errors)
    assert entries[0]["status"] == "line_oob"


def test_handler_writes_evidence_file_and_blocks_on_invalid_source(tmp_path):
    """handle_se_source_evidence: 行号超出 → BLOCKED + evidence 文件落盘."""
    from qualix.runtime.handlers.handlers_finalize import handle_se_source_evidence

    ctx = _make_ctx(tmp_path)
    structured = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "source": "plain_text.txt:999"},
        ],
    }
    (ctx.phase_root / "phase_a_structured.json").write_text(json.dumps(structured))
    ingest = ctx.phase_root / "ingest"
    ingest.mkdir()
    (ingest / "plain_text.txt").write_text("only one line")

    result = _make_result()
    handle_se_source_evidence(ctx, result)

    assert any("BLOCKED" in e for e in result.errors)
    # 等待异步写盘
    time.sleep(0.15)
    ev_path = ctx.internal_dir / "_se_source_evidence.json"
    assert ev_path.exists()
    data = json.loads(ev_path.read_text())
    assert data["entries"][0]["status"] == "line_oob"


# ---------------------------------------------------------------------------
# Task 2: check_eut_code_target_traceability
# ---------------------------------------------------------------------------


def _setup_q01_q05a(tmp_path: Path, code_target: str, bound_item: str = "SE-001"):
    """写 Q01 phase_a_structured.json + Q05a phase_b_structured.json."""
    q01_dir = tmp_path / "test" / "Q01"
    q01_dir.mkdir(parents=True, exist_ok=True)
    q01_data = {
        "project_id": "test",
        "requirements": [{"req_id": "REQ-001", "description": "x"}],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "d", "code_target": code_target},
        ],
    }
    (q01_dir / "phase_a_structured.json").write_text(json.dumps(q01_data))

    q05a_dir = tmp_path / "test" / "Q05a"
    q05a_dir.mkdir(parents=True, exist_ok=True)
    q05a_data = {
        "eut_items": [
            {
                "eut_id": "EUT-001",
                "bound_item": bound_item,
                "given": "g",
                "when": "w",
                "then": "assertEquals(200, response.getStatus())",
                "route_type": "HAPPY_PATH",
            }
        ],
    }
    (q05a_dir / "phase_b_structured.json").write_text(json.dumps(q05a_data))


def test_check_eut_code_target_found(tmp_path):
    """SE.code_target 类名在 code_repo 中能 grep 到 → 无 warning."""
    from qualix.quality.checks.evidence_contract import check_eut_code_target_traceability

    _setup_q01_q05a(tmp_path, code_target="OrderService")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OrderService.java").write_text("public class OrderService {}")

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(repo)])
    assert errors == []


def test_check_eut_code_target_not_found(tmp_path):
    """SE.code_target 在 code_repo 中 grep 不到 → WARNING."""
    from qualix.quality.checks.evidence_contract import check_eut_code_target_traceability

    _setup_q01_q05a(tmp_path, code_target="GhostService")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OrderService.java").write_text("public class OrderService {}")

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(repo)])
    assert any("WARNING" in e for e in errors)
    assert any("GhostService" in e for e in errors)


def test_check_eut_code_target_empty_skips(tmp_path):
    """SE.code_target='' → skip, 无 warning."""
    from qualix.quality.checks.evidence_contract import check_eut_code_target_traceability

    _setup_q01_q05a(tmp_path, code_target="")

    errors = check_eut_code_target_traceability(tmp_path, "test", [str(tmp_path / "repo")])
    assert errors == []


# ---------------------------------------------------------------------------
# Task 3: _check_covered_evidence_fields (Q06 G10)
# ---------------------------------------------------------------------------


def test_covered_no_evidence_warns(tmp_path):
    """COVERED + test_class='' + test_location=None → WARNING."""
    from qualix.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    data = {
        "audit_items": [
            {"eut_id": "EUT-001", "status": "COVERED", "test_class": "", "test_location": None},
        ]
    }
    errors = _check_covered_evidence_fields(data, [])
    assert any("WARNING" in e for e in errors)


def test_covered_with_test_class_passes(tmp_path):
    """COVERED + test_class 有值 → 无 error."""
    from qualix.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    data = {
        "audit_items": [
            {"eut_id": "EUT-001", "status": "COVERED", "test_class": "OrderServiceTest", "test_location": None},
        ]
    }
    errors = _check_covered_evidence_fields(data, [])
    assert errors == []


def test_covered_test_location_file_not_found_blocks(tmp_path):
    """COVERED + test_location.file 在 code_repo 中找不到 → BLOCKED."""
    from qualix.quality.checks.q06_structure_checks import _check_covered_evidence_fields

    repo = tmp_path / "repo"
    repo.mkdir()
    data = {
        "audit_items": [
            {
                "eut_id": "EUT-001",
                "status": "COVERED",
                "test_class": "",
                "test_location": {"file": "src/test/GhostTest.java", "line_start": 5},
            },
        ]
    }
    errors = _check_covered_evidence_fields(data, [str(repo)])
    assert any("BLOCKED" in e for e in errors)
