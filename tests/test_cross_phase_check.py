"""Tests for dqg.cross_phase_check — 跨 Phase ID 引用校验."""

import json
from pathlib import Path

from dqg.quality.cross_phase_check import check_cross_phase_refs, validate_eut_id_subset


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestCrossPhaseRefs:
    def test_no_structured_output(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert errors == []
        assert hashes == {}

    def test_a5_refs_valid(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [{"se_id": "SE-001", "description": "y"}],
                "gaps": [{"gap_id": "GAP-001", "description": "z"}],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q04" / "phase_a5_structured.json",
            {
                "project_id": "PROJ",
                "req_coverage": [{"req_id": "REQ-001", "status": "COVERED"}],
                "se_coverage": [{"se_id": "SE-001", "status": "COVERED"}],
                "gap_closure": [{"gap_id": "GAP-001", "status": "已闭环"}],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert errors == []
        assert "Q01/phase_a_structured.json" in hashes
        assert "Q04/phase_a5_structured.json" in hashes

    def test_a5_refs_missing_req(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [],
                "gaps": [],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q04" / "phase_a5_structured.json",
            {
                "project_id": "PROJ",
                "req_coverage": [{"req_id": "REQ-999", "status": "MISSING"}],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert len(errors) == 1
        assert "REQ-999" in errors[0]

    def test_b_refs_valid_se(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [{"se_id": "SE-001", "description": "y"}],
                "gaps": [],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q05" / "phase_b_structured.json",
            {
                "project_id": "PROJ",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_se": "SE-001",
                        "route_type": "Happy Path",
                        "given": "g",
                        "when": "w",
                        "then": "t",
                    }
                ],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert errors == []
        assert "Q05/phase_b_structured.json" in hashes

    def test_b_refs_missing_se(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [],
                "gaps": [],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q05" / "phase_b_structured.json",
            {
                "project_id": "PROJ",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_se": "SE-999",
                        "route_type": "Happy Path",
                        "given": "g",
                        "when": "w",
                        "then": "t",
                    }
                ],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert len(errors) == 1
        assert "SE-999" in errors[0]
        assert "EUT-001" in errors[0]

    def test_c_refs_missing_eut(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [],
                "gaps": [],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q05" / "phase_b_structured.json",
            {
                "project_id": "PROJ",
                "eut_items": [
                    {
                        "eut_id": "EUT-001",
                        "bound_se": "",
                        "route_type": "Happy Path",
                        "given": "g",
                        "when": "w",
                        "then": "t",
                    }
                ],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q06" / "phase_c_structured.json",
            {
                "project_id": "PROJ",
                "audit_items": [{"eut_id": "EUT-999", "status": "MISSING"}],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert len(errors) == 1
        assert "EUT-999" in errors[0]

    def test_c_refs_when_phase_b_file_missing(self, tmp_path: Path):
        """Q06 引用 EUT 但 Q05 产物不存在时须报错（phantom / 无法对齐子集）。"""
        output_dir = tmp_path / "output"
        _write_json(
            output_dir / "PROJ" / "Q01" / "phase_a_structured.json",
            {
                "project_id": "PROJ",
                "requirements": [{"req_id": "REQ-001", "description": "x"}],
                "semantic_expectations": [],
                "gaps": [],
                "open_items": [],
            },
        )
        _write_json(
            output_dir / "PROJ" / "Q06" / "phase_c_structured.json",
            {
                "project_id": "PROJ",
                "audit_items": [{"eut_id": "EUT-001", "status": "MISSING"}],
            },
        )
        errors, hashes = check_cross_phase_refs(output_dir, "PROJ")
        assert len(errors) == 1
        assert "phase_b_structured.json" in errors[0]

    def test_validate_eut_id_subset_unit(self):
        phase_c = {"audit_items": [{"eut_id": "EUT-007", "status": "MISSING"}]}
        err_missing_b = validate_eut_id_subset(None, phase_c)
        assert len(err_missing_b) == 1
        assert "phase_b_structured.json" in err_missing_b[0]
        phase_b = {"eut_items": [{"eut_id": "EUT-007", "bound_se": ""}]}
        assert validate_eut_id_subset(phase_b, phase_c) == []
