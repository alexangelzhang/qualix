"""Tests for multi_model_judge: 跨模型 Judge 一致性评估."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from qualix.tracking.multi_model_judge import (
    ModelJudgeRun,
    MultiJudgeReport,
    _compute_stats,
    run_multi_model_judge,
)

# ---------------------------------------------------------------------------
# _compute_stats
# ---------------------------------------------------------------------------


def _make_report(
    scores: dict[str, float], verdicts: dict[str, str], dims: dict[str, dict] | None = None
) -> MultiJudgeReport:
    """Helper: build a MultiJudgeReport with given model scores."""
    report = MultiJudgeReport(phase_id="Q03", project_id="test", report_path="/tmp/report.md")
    for model, score in scores.items():
        dim_list = []
        if dims and model in dims:
            dim_list = [{"id": k, "score": v} for k, v in dims[model].items()]
        report.results[model] = ModelJudgeRun(
            model=model,
            overall_score=score,
            verdict=verdicts.get(model, "PASS"),
            dimensions=dim_list,
        )
    return report


def test_consistent_two_models_close_scores():
    """同 PASS/FAIL + 分差 ≤0.5 → CONSISTENT."""
    report = _make_report({"A": 4.0, "B": 4.3}, {"A": "PASS", "B": "PASS"})
    _compute_stats(report)
    assert report.consistency_verdict == "CONSISTENT"
    assert report.verdict_agreement is True
    assert report.score_range == pytest.approx(0.3, abs=1e-6)


def test_marginal_two_models_medium_gap():
    """分差 0.5~1.0 → MARGINAL."""
    report = _make_report({"A": 3.0, "B": 3.8}, {"A": "PASS_WITH_CONCERNS", "B": "PASS"})
    _compute_stats(report)
    assert report.consistency_verdict == "MARGINAL"
    assert report.verdict_agreement is True


def test_diverged_high_score_range():
    """分差 > 1.0 → DIVERGED."""
    report = _make_report({"A": 2.0, "B": 3.5}, {"A": "FAIL", "B": "PASS_WITH_CONCERNS"})
    _compute_stats(report)
    assert report.consistency_verdict == "DIVERGED"
    assert report.verdict_agreement is False


def test_verdict_disagreement_detected():
    """PASS vs FAIL → agreement=False."""
    report = _make_report({"A": 4.0, "B": 2.0}, {"A": "PASS", "B": "FAIL"})
    _compute_stats(report)
    assert report.verdict_agreement is False


def test_fragile_dimension_detected():
    """维度分差 > 1.0 → 标记为 fragile."""
    report = _make_report(
        {"A": 3.5, "B": 3.5},
        {"A": "PASS", "B": "PASS"},
        dims={
            "A": {"faithfulness": 4.0, "completeness": 3.0},
            "B": {"faithfulness": 2.5, "completeness": 3.5},
        },
    )
    _compute_stats(report)
    assert "faithfulness" in report.fragile_dimensions
    assert "completeness" not in report.fragile_dimensions


def test_no_fragile_when_dimensions_agree():
    """维度分差 ≤1.0 → 无 fragile dimensions."""
    report = _make_report(
        {"A": 3.5, "B": 3.8},
        {"A": "PASS", "B": "PASS"},
        dims={
            "A": {"faithfulness": 4.0, "completeness": 3.5},
            "B": {"faithfulness": 3.5, "completeness": 3.8},
        },
    )
    _compute_stats(report)
    assert report.fragile_dimensions == []


def test_infra_failure_excluded_from_stats():
    """INFRA_FAILURE 的模型不参与统计."""
    report = _make_report({"A": 4.0, "B": 0.0}, {"A": "PASS", "B": "FAIL"})
    report.results["B"].health = "INFRA_FAILURE"
    _compute_stats(report)
    # Only 1 healthy model → no stats computed
    assert report.score_range == 0.0
    assert report.consistency_verdict == "CONSISTENT"  # unchanged default


def test_single_healthy_model_no_stats():
    """只有 1 个健康模型时不计算统计（需 ≥2）."""
    report = _make_report({"A": 4.0}, {"A": "PASS"})
    _compute_stats(report)
    assert report.score_range == 0.0
    assert report.score_stddev == 0.0


# ---------------------------------------------------------------------------
# summary_lines
# ---------------------------------------------------------------------------


def test_summary_lines_format():
    report = _make_report(
        {"deepseek-chat": 4.0, "claude-opus-4-6": 3.5},
        {"deepseek-chat": "PASS", "claude-opus-4-6": "PASS_WITH_CONCERNS"},
    )
    _compute_stats(report)
    lines = report.summary_lines()
    assert any("MARGINAL" in line or "CONSISTENT" in line or "DIVERGED" in line for line in lines)
    assert any("deepseek-chat" in line for line in lines)
    assert any("claude-opus-4-6" in line for line in lines)


# ---------------------------------------------------------------------------
# run_multi_model_judge (integration stub)
# ---------------------------------------------------------------------------


def test_run_multi_model_judge_uses_judge_runner(tmp_path: Path):
    """验证 run_multi_model_judge 对每个模型各调用一次 JudgeRunner.run."""
    from qualix.core.state_machine import PHASE_DEFS

    phase_def = PHASE_DEFS.get("Q03")
    assert phase_def, "Q03 must be in PHASE_DEFS"

    # 创建最小目录结构
    proj_dir = tmp_path / "test-proj" / "Q03"
    proj_dir.mkdir(parents=True)
    report_file = proj_dir / "tech_design_quality_review.md"
    report_file.write_text("# Tech Quality Review\n\n## Quality\n\nGood design.", encoding="utf-8")

    fake_result = MagicMock()
    fake_result.overall_score = 4.0
    fake_result.verdict = "PASS"
    fake_result.dimensions = [{"id": "coverage_accuracy", "score": 4.0}]
    fake_result.health = "HEALTHY"
    fake_result.duration = 1.0
    fake_result.raw_output = ""

    with patch("qualix.quality.judge.judge_runner.JudgeRunner") as MockRunner:
        mock_instance = MagicMock()
        mock_instance.run.return_value = fake_result
        MockRunner.return_value = mock_instance

        result = run_multi_model_judge(tmp_path, "test-proj", "Q03", ["model-a", "model-b"])

    assert mock_instance.run.call_count == 2
    assert "model-a" in result.results
    assert "model-b" in result.results
    assert result.results["model-a"].overall_score == 4.0
    assert result.consistency_verdict in {"CONSISTENT", "MARGINAL", "DIVERGED"}


def test_run_raises_on_missing_report(tmp_path: Path):
    """报告文件不存在时抛出 FileNotFoundError."""

    proj_dir = tmp_path / "test-proj" / "Q03"
    proj_dir.mkdir(parents=True)
    # 故意不创建 tech_design_quality_review.md

    with pytest.raises(FileNotFoundError):
        run_multi_model_judge(tmp_path, "test-proj", "Q03", ["model-a", "model-b"])
