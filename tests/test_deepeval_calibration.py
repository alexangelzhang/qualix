"""Tests for DeepEval score calibration integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# _DQGDeepEvalModel adapter
# ---------------------------------------------------------------------------


def test_dqg_model_generate_delegates_to_backend():
    from src.dqg.quality.judge.score_calibration import _DQGDeepEvalModel

    model = _DQGDeepEvalModel("claude-haiku-4-5-20251001")
    fake_backend = MagicMock()
    fake_backend.chat.return_value = ("The output is good.", {"total_tokens": 42})
    model._backend = fake_backend

    result = model.generate("Evaluate this report")
    assert result == "The output is good."
    fake_backend.chat.assert_called_once_with([{"role": "user", "content": "Evaluate this report"}])


def test_dqg_model_get_model_name():
    from src.dqg.quality.judge.score_calibration import _DQGDeepEvalModel

    model = _DQGDeepEvalModel("claude-sonnet-4-6")
    assert model.get_model_name() == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# _run_deepeval_scoring
# ---------------------------------------------------------------------------


def test_run_deepeval_scoring_returns_none_on_import_error():
    """ImportError（未安装 deepeval）时静默返回 None."""
    import builtins

    from src.dqg.quality.judge.score_calibration import _run_deepeval_scoring

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "deepeval.metrics":
            raise ImportError("deepeval not installed")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        result = _run_deepeval_scoring("Q03", "Some report text")
    assert result is None


def test_run_deepeval_scoring_maps_score_to_1_5():
    """GEval 0-1 分映射到 DQG 1-5 分."""
    from src.dqg.quality.judge.score_calibration import _run_deepeval_scoring

    mock_metric = MagicMock()
    mock_metric.score = 0.75  # → 1 + 0.75*4 = 4.0

    mock_test_case = MagicMock()

    with (
        patch("deepeval.metrics.GEval", return_value=mock_metric),
        patch("deepeval.test_case.LLMTestCase", return_value=mock_test_case),
    ):
        result = _run_deepeval_scoring("Q03", "Some quality report text")

    assert result == 4.0


def test_run_deepeval_scoring_returns_none_on_exception():
    """任何运行时异常都应静默返回 None，不抛出."""
    from src.dqg.quality.judge.score_calibration import _run_deepeval_scoring

    mock_metric = MagicMock()
    mock_metric.measure.side_effect = RuntimeError("LLM call failed")

    with (
        patch("deepeval.metrics.GEval", return_value=mock_metric),
        patch("deepeval.test_case.LLMTestCase"),
    ):
        result = _run_deepeval_scoring("Q03", "Some report")

    assert result is None


def test_run_deepeval_scoring_score_boundaries():
    """边界值：score=0 → 1.0, score=1 → 5.0."""
    from src.dqg.quality.judge.score_calibration import _run_deepeval_scoring

    for geval_score, expected_dqg in [(0.0, 1.0), (1.0, 5.0)]:
        mock_metric = MagicMock()
        mock_metric.score = geval_score
        with (
            patch("deepeval.metrics.GEval", return_value=mock_metric),
            patch("deepeval.test_case.LLMTestCase"),
        ):
            result = _run_deepeval_scoring("Q06", "report")
        assert result == expected_dqg


# ---------------------------------------------------------------------------
# _get_phase_criteria
# ---------------------------------------------------------------------------


def test_get_phase_criteria_covers_all_known_phases():
    from src.dqg.quality.judge.score_calibration import _get_phase_criteria

    for phase_id in ("Q01", "Q03", "Q04", "Q05", "Q05a", "Q05b", "Q06", "Q07"):
        criteria = _get_phase_criteria(phase_id)
        assert isinstance(criteria, str) and len(criteria) > 20, f"Missing criteria for {phase_id}"


def test_get_phase_criteria_fallback_for_unknown():
    from src.dqg.quality.judge.score_calibration import _get_phase_criteria

    result = _get_phase_criteria("Q99")
    assert "quality" in result.lower() or "assess" in result.lower()
