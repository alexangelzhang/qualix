"""Tests for JudgeRunner canonical schema normalization."""

from qualix.quality.judge_runner import JudgeResult, JudgeRunner


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


# ============ fail_threshold 门限机制 ============

_RUBRIC_WITH_THRESHOLDS = [
    {"id": "dyn_state_machine", "fail_threshold": 2},
    {"id": "dyn_concurrency", "fail_threshold": 2},
    {"id": "dyn_external_dependency", "fail_threshold": 2},
]


def test_threshold_triggers_fail_even_when_overall_high():
    """任一维度 score < fail_threshold 时整体强制降为 FAIL，不受加权平均稀释."""
    raw = {
        "overall": 4.5,
        "verdict": "PASS",
        "scores": {
            "dyn_state_machine": 5,
            "dyn_concurrency": 5,
            "dyn_external_dependency": 1,  # < 2 → FAIL
        },
    }
    result = JudgeRunner.normalize(raw, rubric_dims=_RUBRIC_WITH_THRESHOLDS)
    assert result.verdict == "FAIL"
    assert result.overall_score == 4.5  # overall 保留原值
    assert result.failing_dimensions == ["dyn_external_dependency"]


def test_threshold_no_trigger_when_all_above():
    """所有维度 >= fail_threshold 时 verdict 保持原值."""
    raw = {
        "overall": 4.0,
        "verdict": "PASS",
        "scores": {"dyn_state_machine": 4, "dyn_concurrency": 3, "dyn_external_dependency": 2},
    }
    result = JudgeRunner.normalize(raw, rubric_dims=_RUBRIC_WITH_THRESHOLDS)
    assert result.verdict == "PASS"
    assert result.failing_dimensions == []


def test_threshold_collects_multiple_failing_dims():
    """多个维度低于阈值时全部收集，verdict = FAIL."""
    raw = {
        "overall": 3.0,
        "verdict": "PASS_WITH_CONCERNS",
        "scores": {"dyn_state_machine": 1, "dyn_concurrency": 1, "dyn_external_dependency": 4},
    }
    result = JudgeRunner.normalize(raw, rubric_dims=_RUBRIC_WITH_THRESHOLDS)
    assert result.verdict == "FAIL"
    assert set(result.failing_dimensions) == {"dyn_state_machine", "dyn_concurrency"}


def test_threshold_without_rubric_dims_keeps_original_behavior():
    """未传 rubric_dims（历史调用路径）时行为不变，verdict 不被降级."""
    raw = {
        "overall": 4.5,
        "verdict": "PASS",
        "scores": {"dyn_state_machine": 1},  # 即使 1 分也不触发
    }
    result = JudgeRunner.normalize(raw)  # 不传 rubric_dims
    assert result.verdict == "PASS"
    assert result.failing_dimensions == []


def test_threshold_works_with_dimensions_list_format():
    """raw 用 dimensions list 而非 scores dict 时门限也能识别."""
    raw = {
        "overall_score": 4.0,
        "verdict": "PASS",
        "dimensions": [
            {"id": "dyn_state_machine", "score": 1, "weight": 0.3},
            {"id": "dyn_concurrency", "score": 5, "weight": 0.7},
        ],
        "issues": [],
    }
    result = JudgeRunner.normalize(raw, rubric_dims=_RUBRIC_WITH_THRESHOLDS)
    assert result.verdict == "FAIL"
    assert result.failing_dimensions == ["dyn_state_machine"]


def test_threshold_ignores_dims_not_in_rubric():
    """rubric_dims 没定义的维度即使低分也不触发 FAIL."""
    raw = {
        "overall": 4.5,
        "verdict": "PASS",
        "scores": {
            "faithfulness": 1,  # 不在 _RUBRIC_WITH_THRESHOLDS 里，不影响
            "dyn_state_machine": 5,
            "dyn_concurrency": 5,
            "dyn_external_dependency": 5,
        },
    }
    result = JudgeRunner.normalize(raw, rubric_dims=_RUBRIC_WITH_THRESHOLDS)
    assert result.verdict == "PASS"
    assert result.failing_dimensions == []
