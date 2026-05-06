"""Tests for JudgeRunner canonical schema normalization."""

from dqg.quality.judge_runner import JudgeResult, JudgeRunner


def test_normalize_adaptive_format():
    """Adaptive output uses 'overall' not 'overall_score', and scores dict."""
    raw = {
        "overall": 3.5,
        "verdict": "PASS_WITH_CONCERNS",
        "scores": {"faithfulness": 4, "completeness": 3},
        "issues": [{"severity": "medium", "description": "missing edge case"}],
    }
    result = JudgeRunner.normalize(raw, raw_output="raw text here")
    assert result.overall_score == 3.5
    assert result.verdict == "PASS_WITH_CONCERNS"
    assert isinstance(result.dimensions, list)
    assert result.dimensions[0]["id"] == "faithfulness"
    assert result.raw_output == "raw text here"
    assert result.health == "HEALTHY"


def test_normalize_manual_format():
    """Manual judge output uses 'overall_score' and dimensions list."""
    raw = {
        "overall_score": 4.0,
        "verdict": "PASS",
        "dimensions": [
            {"id": "faithfulness", "name": "忠实度", "score": 4, "weight": 0.25, "issues": []},
        ],
        "issues": [],
    }
    result = JudgeRunner.normalize(raw, raw_output="raw")
    assert result.overall_score == 4.0
    assert result.dimensions[0]["id"] == "faithfulness"


def test_normalize_empty_returns_infra_failure():
    """Empty parsed dict → INFRA_FAILURE."""
    result = JudgeRunner.normalize({}, raw_output="garbage")
    assert result.health == "INFRA_FAILURE"
    assert result.overall_score == 0
    assert result.verdict == "FAIL"


def test_normalize_preserves_dimensions_list():
    """If dimensions is already a list, keep it as-is."""
    dims = [{"id": "d1", "name": "D1", "score": 5, "weight": 0.5, "issues": []}]
    raw = {"overall_score": 5.0, "verdict": "PASS", "dimensions": dims, "issues": []}
    result = JudgeRunner.normalize(raw)
    assert result.dimensions == dims


def test_judge_result_schema_version():
    r = JudgeResult(overall_score=4.0, verdict="PASS", dimensions=[], issues=[], raw_output="")
    assert r._schema_version == 1
