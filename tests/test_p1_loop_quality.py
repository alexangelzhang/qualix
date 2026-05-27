"""Tests for P1 loop quality improvements."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Task 1: data_patterns sidecar
# ---------------------------------------------------------------------------


def test_write_data_patterns_uses_phase_id(tmp_path):
    """write_data_patterns 必须用 phase_id 调用 analyze_data_patterns，而非硬编码 'Q06'."""
    from unittest.mock import patch as _patch

    from dqg.tracking.data_patterns import write_data_patterns

    captured_phase = []

    def _fake_analyze(phase=None):
        captured_phase.append(phase)
        return {
            "top_patterns": [
                {"id": "DP-X", "name": "测试", "count": 1, "suggestions": [], "example_cases": [], "top_lessons": []}
            ],
            "total_cases": 1,
            "pattern_distribution": {"DP-X": 1},
            "cases_by_pattern": {},
        }

    with _patch("dqg.tracking.data_patterns.analyze_data_patterns", side_effect=_fake_analyze):
        result_path = write_data_patterns(tmp_path, "proj", "Q05")

    assert captured_phase == ["Q05"], f"Expected ['Q05'], got {captured_phase}"
    assert result_path is not None, "write_data_patterns should return a path when patterns exist"


def test_analyze_data_patterns_includes_top_lessons():
    """analyze_data_patterns 返回的 top_patterns 每条应包含 top_lessons 列表."""
    from unittest.mock import patch as _patch

    from dqg.tracking.data_patterns import analyze_data_patterns

    fake_cases = [
        {
            "case_id": "c1",
            "phase": "Q05",
            "lesson": "字段映射必须显式转换枚举值",
            "title": "字段映射错误",
            "description": "金额字段未转换",
            "error_type": "field_mapping",
        },
    ]

    with (
        _patch("dqg.tracking.data_patterns.load_cases_by_phase", return_value=fake_cases),
        _patch("dqg.tracking.data_patterns.get_case_with_inferred_lesson", side_effect=lambda c: c),
    ):
        result = analyze_data_patterns("Q05")

    for pattern in result.get("top_patterns", []):
        assert "top_lessons" in pattern, f"Pattern {pattern['id']} missing top_lessons"
        assert isinstance(pattern["top_lessons"], list)


# ---------------------------------------------------------------------------
# Task 2: PIVOT snapshot
# ---------------------------------------------------------------------------


def _make_adaptive_loop_fixtures(tmp_path):
    """构造 AdaptiveLoop 测试所需的最小 fixtures."""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop = AdaptiveLoop(output_dir=tmp_path)
    pd = tmp_path / "proj" / "phase_a"
    pd.mkdir(parents=True)
    (pd / "_internal").mkdir()

    (pd / "phase_a_structured.json").write_text('{"project_id": "proj"}')
    (pd / "phase_a_report.md").write_text("# Report v1")
    (pd / "_internal" / "_reasoning_log.md").write_text("## Step 1")

    return loop, pd


def test_pivot_snapshot_creates_dir_on_judge_fail(tmp_path):
    """Judge FAIL 时应创建 _pivot_v1/ 目录并包含主 JSON."""
    from dqg.constants import STRUCTURED_JSON_MAP

    loop, pd = _make_adaptive_loop_fixtures(tmp_path)
    phase_id = "Q01"
    json_fname = STRUCTURED_JSON_MAP.get(phase_id, "phase_a_structured.json")
    (pd / json_fname).write_text('{"project_id": "proj"}')

    loop._save_pivot_snapshot(pd=pd, iteration_n=0, phase_id=phase_id)

    pivot_dir = pd / "_pivot_v1"
    assert pivot_dir.is_dir(), "_pivot_v1 目录未创建"
    assert (pivot_dir / json_fname).exists(), "主 JSON 未复制"


def test_pivot_snapshot_writes_latest_pointer(tmp_path):
    """_save_pivot_snapshot 应更新 _pivot_latest 文件."""

    loop, pd = _make_adaptive_loop_fixtures(tmp_path)
    loop._save_pivot_snapshot(pd=pd, iteration_n=1, phase_id="Q01")

    pointer = pd / "_pivot_latest"
    assert pointer.exists()
    assert pointer.read_text().strip() == "_pivot_v2"


def test_pivot_snapshot_skips_missing_files(tmp_path):
    """不存在的文件不应导致 snapshot 抛出异常."""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop = AdaptiveLoop(output_dir=tmp_path)
    pd = tmp_path / "proj" / "phaseX"
    pd.mkdir(parents=True)

    # No files exist — must not raise
    loop._save_pivot_snapshot(pd=pd, iteration_n=0, phase_id="Q99")
    # Just verifying no exception was raised
