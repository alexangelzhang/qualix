"""Tests for dqg.quality.auto_checks."""

import json
import tempfile
from pathlib import Path

import pytest

from dqg.quality.auto_checks import auto_derive_checks


def _setup_phase_a(tmpdir: Path, data: dict) -> Path:
    """创建 Phase A 的产物目录和 JSON."""
    phase_dir = tmpdir / "test-proj" / "phaseA"
    phase_dir.mkdir(parents=True)
    json_path = phase_dir / "phase_a_structured.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmpdir


def _setup_phase_a6(tmpdir: Path, data: dict) -> Path:
    """创建 Phase A.6 的产物目录和 JSON."""
    phase_dir = tmpdir / "test-proj" / "phaseA6"
    phase_dir.mkdir(parents=True)
    json_path = phase_dir / "phase_a6_structured.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmpdir


VALID_PHASE_A = {
    "project_id": "test-proj",
    "requirements": [
        {"req_id": "REQ-001", "description": "用户可以创建工单"},
        {"req_id": "BR-001", "parent_id": "REQ-001", "description": "工单创建需要校验幂等性"},
    ],
    "semantic_expectations": [
        {"se_id": "SE-001", "description": "幂等性校验"},
    ],
    "gaps": [
        {"gap_id": "GAP-001", "related_ids": ["REQ-001"], "description": "并发场景未定义", "required_clarification": "需要明确并发策略"},
    ],
    "open_items": [
        {"open_id": "OPEN-001", "related_ids": ["REQ-001"], "question": "超时时间是多少？"},
    ],
}


class TestAutoChecksPhaseA:

    def test_valid_data_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a(Path(tmpdir), VALID_PHASE_A)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert errors == []

    def test_missing_json_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "test-proj" / "phaseA").mkdir(parents=True)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert any("MISSING" in e for e in errors)

    def test_invalid_req_id_pattern(self):
        data = {**VALID_PHASE_A, "requirements": [
            {"req_id": "INVALID-001", "description": "bad id"},
        ]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert any("SCHEMA" in e for e in errors)

    def test_gap_references_nonexistent_id(self):
        data = {**VALID_PHASE_A, "gaps": [
            {"gap_id": "GAP-001", "related_ids": ["REQ-999"], "description": "引用不存在的ID", "required_clarification": "x"},
        ]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert any("XREF" in e and "REQ-999" in e for e in errors)

    def test_gap_missing_clarification(self):
        data = {**VALID_PHASE_A, "gaps": [
            {"gap_id": "GAP-001", "related_ids": ["REQ-001"], "description": "缺少澄清", "required_clarification": ""},
        ]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert any("INCOMPLETE" in e and "GAP-001" in e for e in errors)

    def test_no_req_level_requirement(self):
        """只有 BR 没有 REQ 应该被 schema validator 捕获."""
        data = {**VALID_PHASE_A, "requirements": [
            {"req_id": "BR-001", "description": "只有分支需求"},
        ]}
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q01")
            assert any("SCHEMA" in e for e in errors)


class TestAutoChecksPhaseA6:

    def test_valid_a6_passes(self):
        data = {
            "project_id": "test-proj",
            "issues": [
                {"issue_id": "ARCH-001", "description": "架构问题", "severity": "HIGH"},
            ],
            "failure_modes": [
                {"business_path": "创建工单", "failure_scenario": "超时", "has_exception_handling": True, "status": "SAFE"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a6(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q03")
            assert errors == []

    def test_issue_missing_severity(self):
        data = {
            "project_id": "test-proj",
            "issues": [
                {"issue_id": "ARCH-001", "description": "缺少严重等级"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_phase_a6(Path(tmpdir), data)
            errors = auto_derive_checks(output_dir, "test-proj", "Q03")
            # severity 是必填字段，schema 校验会捕获
            assert any("SCHEMA" in e for e in errors)


class TestAutoChecksUnknownPhase:

    def test_unknown_phase_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = auto_derive_checks(Path(tmpdir), "test-proj", "Z")
            assert errors == []
