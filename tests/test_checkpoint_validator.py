"""Tests for checkpoint validator: rule checks + LLM fallback."""

from __future__ import annotations

import json


def _make_contract(verification_targets=None, done_definition=None):
    return {
        "verification_targets": verification_targets
        or [
            {"id": "REQ-001", "description": "创建维保单"},
            {"id": "SE-001", "description": "校验车辆数量"},
            {"id": "BR-001", "description": "最多关联5辆车"},
        ],
        "done_definition": done_definition or ["需求结构化报告", "结构化JSON"],
    }


def test_validate_passes_with_good_content():
    """Content covering all verification targets passes."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    content = json.dumps(
        {
            "evidences": [
                {"id": "E-001", "source": "prd.md:10", "content": "REQ-001 创建维保单"},
                {"id": "E-002", "source": "prd.md:20", "content": "SE-001 校验车辆数量"},
                {"id": "E-003", "source": "prd.md:30", "content": "BR-001 最多关联5辆车"},
            ]
        }
    )
    result = validate_checkpoint(content, _make_contract(), "Q01", "evidence_pack")
    assert result.passed is True
    assert result.block_reason == ""


def test_validate_fails_with_empty_content():
    """Empty content fails rule check."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    result = validate_checkpoint("", _make_contract(), "Q01", "evidence_pack")
    assert result.passed is False
    assert "empty" in result.block_reason.lower() or "非空" in result.block_reason


def test_validate_fails_with_low_coverage():
    """Content covering < 60% of verification targets fails."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    content = json.dumps(
        {
            "evidences": [
                {"id": "E-001", "source": "prd.md:10", "content": "REQ-001 创建维保单"},
            ]
        }
    )
    result = validate_checkpoint(content, _make_contract(), "Q01", "evidence_pack")
    assert result.passed is False
    assert "覆盖" in result.block_reason or "coverage" in result.block_reason.lower()


def test_validate_skips_when_no_contract():
    """No contract → skip checkpoint, return PASS."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    result = validate_checkpoint("some content", {}, "Q01", "evidence_pack")
    assert result.passed is True


def test_validate_skips_when_no_targets():
    """Contract with empty verification_targets → skip, return PASS."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    result = validate_checkpoint("some content", {"verification_targets": []}, "Q01", "test")
    assert result.passed is True


def test_rule_checks_recorded():
    """Rule check results are recorded in CheckpointResult."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    content = json.dumps({"evidences": [{"id": "E-001", "source": "x:1", "content": "REQ-001 test"}]})
    result = validate_checkpoint(content, _make_contract(), "Q01", "test")
    assert len(result.rule_checks) >= 1
    assert all("name" in c and "passed" in c for c in result.rule_checks)


def test_validate_plain_text_content():
    """Plain text (not JSON) content also works for upstream quality check."""
    from qualix.quality.checkpoint_validator import validate_checkpoint

    content = "# 需求结构化报告\n\n## REQ-001 创建维保单\n## SE-001 校验\n## BR-001 关联"
    result = validate_checkpoint(content, _make_contract(), "Q01", "upstream_report")
    assert result.passed is True
