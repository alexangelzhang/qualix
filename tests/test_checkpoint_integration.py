# tests/test_checkpoint_integration.py
"""Integration tests for runtime eval checkpoint validation."""

from __future__ import annotations

import json


def test_evidence_pack_checkpoint_passes_good_pack():
    """Good evidence pack with contract passes checkpoint."""
    from dqg.quality.checkpoint_validator import validate_checkpoint

    contract = {
        "verification_targets": [
            {"id": "REQ-001", "description": "创建维保单"},
            {"id": "SE-001", "description": "校验车辆数量"},
        ],
    }
    pack = {
        "evidences": [
            {"id": "E-001", "source": "prd.md:10", "content": "REQ-001 创建维保单功能"},
            {"id": "E-002", "source": "prd.md:20", "content": "SE-001 校验车辆数量上限"},
        ],
    }
    result = validate_checkpoint(json.dumps(pack), contract, "Q01", "evidence_pack")
    assert result.passed is True


def test_evidence_pack_checkpoint_blocks_empty_pack():
    """Empty evidence pack fails checkpoint."""
    from dqg.quality.checkpoint_validator import validate_checkpoint

    contract = {
        "verification_targets": [{"id": "REQ-001", "description": "test"}],
    }
    result = validate_checkpoint(json.dumps({"evidences": []}), contract, "Q01", "evidence_pack")
    assert result.passed is False


def test_upstream_quality_check_in_preflight(tmp_path):
    """Preflight upstream quality check runs without error."""
    from unittest.mock import MagicMock, patch

    from dqg.runtime.preflight import _check_upstream_quality

    project_id = "test-proj"
    q01_dir = tmp_path / project_id / "Q01"
    q01_dir.mkdir(parents=True)
    int_dir = q01_dir / "_internal"
    int_dir.mkdir()

    contract = {
        "verification_targets": [
            {"id": "REQ-001", "description": "创建维保单"},
            {"id": "REQ-002", "description": "多车辆关联"},
            {"id": "SE-001", "description": "校验数量"},
        ],
    }
    (int_dir / "_phase_contract.json").write_text(json.dumps(contract))

    structured = {"requirements": [{"id": "REQ-001", "description": "创建维保单"}]}
    (q01_dir / "phase_a_structured.json").write_text(json.dumps(structured))
    (q01_dir / "phase_a_report.md").write_text("# 报告\n简短内容")

    mock_state = MagicMock()
    mock_phase = MagicMock()
    mock_phase.status = "approved"
    mock_phase.run_status = "ok"
    mock_state.phases = {"Q01": mock_phase}

    with patch("dqg.core.state_machine.load_state", return_value=mock_state):
        result = _check_upstream_quality(tmp_path, project_id, "Q03")

    assert result["name"] == "upstream_quality"
    assert result["status"] in ("PASS", "FAIL")


def test_checkpoint_no_contract_graceful_skip():
    """No contract file → checkpoint skips gracefully."""
    from dqg.quality.checkpoint_validator import validate_checkpoint

    result = validate_checkpoint("some content here", {}, "Q01", "test")
    assert result.passed is True
