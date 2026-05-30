"""Tests for prompt eval manifest metadata."""

from __future__ import annotations

from pathlib import Path

from qualix.json_utils import save_json
from qualix.tracking.prompt_eval import compute_prompt_metrics, format_comparison_table, run_prompt_eval_case


def test_compute_prompt_metrics_includes_manifest_hashes(tmp_path) -> None:
    case_dir = tmp_path / "case"
    (case_dir / "input").mkdir(parents=True)
    (case_dir / "prompt_versions").mkdir()
    save_json(case_dir / "case.json", {"case_id": "PE-001", "phase": "Q05a", "sample_type": "prompt-eval"})
    save_json(case_dir / "input" / "out.json", {"eut_cases": [{"id": "EUT-1"}]})
    (case_dir / "prompt_versions" / "v1.md").write_text("# Prompt", encoding="utf-8")
    save_json(
        case_dir / "prompt_versions" / "v1.manifest.json",
        {
            "prompt_hash": "abc123",
            "assembly_order": ["goal", "rubric"],
            "section_hashes": {"goal": "g1", "rubric": "r1"},
        },
    )

    result = compute_prompt_metrics(case_dir)

    row = result["rows"][0]
    assert row["prompt_hash"] == "abc123"
    assert row["assembly_order"] == ["goal", "rubric"]
    assert row["section_hashes"]["rubric"] == "r1"


def test_run_prompt_eval_case_uses_executor_outputs_per_prompt_version(tmp_path) -> None:
    case_dir = tmp_path / "case"
    (case_dir / "input").mkdir(parents=True)
    (case_dir / "prompt_versions").mkdir()
    save_json(case_dir / "case.json", {"case_id": "PE-002", "phase": "Q05a", "sample_type": "prompt-eval"})
    save_json(case_dir / "input" / "input.json", {"requirements": ["REQ-1"]})
    (case_dir / "prompt_versions" / "v1.md").write_text("# Prompt v1", encoding="utf-8")
    (case_dir / "prompt_versions" / "v2.md").write_text("# Prompt v2", encoding="utf-8")

    def executor(version_name, prompt, fixed_input, meta):
        assert prompt.startswith("# Prompt")
        assert fixed_input == {"requirements": ["REQ-1"]}
        if version_name == "v1":
            return {"eut_matrix": [{"id": "EUT-1", "path_type": "Happy"}]}
        return {
            "eut_matrix": [
                {"id": "EUT-1", "path_type": "Happy"},
                {"id": "EUT-2", "path_type": "Exception"},
            ]
        }

    result = run_prompt_eval_case(case_dir, executor=executor)

    rows = {row["version"]: row for row in result["rows"]}
    assert rows["v1"]["scores"]["eut_count"] == 1
    assert rows["v2"]["scores"]["eut_count"] == 2
    assert rows["v1"]["execution"]["source"] == "executor"
    assert rows["v2"]["execution"]["source"] == "executor"


def test_run_prompt_eval_case_uses_offline_prompt_outputs(tmp_path) -> None:
    case_dir = tmp_path / "case"
    (case_dir / "input").mkdir(parents=True)
    (case_dir / "prompt_versions").mkdir()
    (case_dir / "prompt_outputs").mkdir()
    save_json(case_dir / "case.json", {"case_id": "PE-003", "phase": "Q06", "sample_type": "prompt-eval"})
    save_json(case_dir / "input" / "input.json", {"seed": "fixed"})
    (case_dir / "prompt_versions" / "v1.md").write_text("# Prompt v1", encoding="utf-8")
    save_json(case_dir / "prompt_outputs" / "v1.json", {"se_coverage": [{"status": "COVERED"}, {"status": "MISSING"}]})

    result = run_prompt_eval_case(case_dir)

    row = result["rows"][0]
    assert row["scores"]["covered_rate"] == 0.5
    assert row["scores"]["missing_count"] == 1
    assert row["execution"]["source"] == "prompt_outputs"


def test_format_comparison_table_includes_execution_source(tmp_path) -> None:
    result = {
        "case_id": "PE-004",
        "phase": "Q05a",
        "metric_ids": ["eut_count"],
        "metric_names": {"eut_count": "EUT 数量"},
        "rows": [
            {
                "version": "v1",
                "prompt_hash": "abcdef123456",
                "assembly_order": ["goal"],
                "execution": {"source": "executor"},
                "scores": {"eut_count": 2},
            }
        ],
    }

    table = format_comparison_table(result)

    assert "execution" in table
    assert "executor" in table
    assert "| --- | ---: | ---: | ---: | ---: |" in table


def test_builtin_prompt_eval_cases_use_offline_outputs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    q05 = run_prompt_eval_case(repo_root / "regression" / "cases" / "prompt-eval" / "Q05-basic")
    q06 = run_prompt_eval_case(repo_root / "regression" / "cases" / "prompt-eval" / "Q06-basic")

    q05_rows = {row["version"]: row for row in q05["rows"]}
    q06_rows = {row["version"]: row for row in q06["rows"]}
    assert {row["execution"]["source"] for row in q05["rows"]} == {"prompt_outputs"}
    assert {row["execution"]["source"] for row in q06["rows"]} == {"prompt_outputs"}
    assert q05_rows["v2_enhanced"]["scores"]["eut_count"] > q05_rows["v1_baseline"]["scores"]["eut_count"]
    assert q06_rows["v2_enhanced"]["scores"]["covered_rate"] > q06_rows["v1_baseline"]["scores"]["covered_rate"]
