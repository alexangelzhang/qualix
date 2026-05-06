"""Tests for dqg.quality.behavioral_fingerprint."""

import json
import tempfile
from pathlib import Path

from dqg.quality.behavioral_fingerprint import (
    compare_fingerprints,
    extract_fingerprint,
    extract_fingerprints_from_file,
)


def _make_trajectory(
    phase_id: str = "Q01",
    tool_calls: list[str] | None = None,
    ids_in_output: str = "REQ-001 REQ-002 BR-001 GAP-001",
    output_length: int = 500,
) -> dict:
    messages = [
        {"role": "system", "content": "你是需求分析专家。"},
        {"role": "user", "content": "执行 Phase 任务。"},
    ]
    for tool in tool_calls or []:
        messages.append(
            {
                "role": "assistant",
                "content": f'调用工具\n<tool_call name="{tool}">\n{{"keyword": "test"}}\n</tool_call>',
            }
        )
        messages.append(
            {
                "role": "user",
                "content": f'<tool_result name="{tool}">\nresult\n</tool_result>',
            }
        )
    messages.append(
        {
            "role": "assistant",
            "content": f"最终报告 {ids_in_output}\n" + "x" * output_length,
        }
    )
    return {
        "project_id": "test",
        "phase_id": phase_id,
        "agent_role": "worker",
        "messages": messages,
    }


class TestExtractFingerprint:
    def test_basic_extraction(self):
        traj = _make_trajectory(tool_calls=["search_upstream_context", "read_wiki_page"])
        fp = extract_fingerprint(traj)
        assert fp.phase_id == "Q01"
        assert fp.tool_call_count == 2
        assert "search_upstream_context" in fp.unique_tools_used
        assert fp.id_counts.get("REQ", 0) == 2
        assert fp.id_counts.get("GAP", 0) == 1
        assert fp.total_ids == 4
        assert fp.has_tool_calls is True

    def test_no_tool_calls(self):
        traj = _make_trajectory(tool_calls=[])
        fp = extract_fingerprint(traj)
        assert fp.tool_call_count == 0
        assert fp.has_tool_calls is False

    def test_empty_trajectory(self):
        fp = extract_fingerprint({"messages": []})
        assert fp.turn_count == 0
        assert fp.total_ids == 0


class TestCompareFingerprints:
    def test_identical_passes(self):
        traj = _make_trajectory(tool_calls=["search_upstream_context"])
        baseline = extract_fingerprint(traj)
        current = extract_fingerprint(traj)
        result = compare_fingerprints(baseline, current)
        assert result.verdict == "PASS"
        assert result.deviations == []

    def test_id_regression_detected(self):
        baseline = extract_fingerprint(
            _make_trajectory(
                ids_in_output="REQ-001 REQ-002 REQ-003 REQ-004 BR-001 GAP-001",
            )
        )
        current = extract_fingerprint(
            _make_trajectory(
                ids_in_output="REQ-001",  # 大幅减少
            )
        )
        result = compare_fingerprints(baseline, current)
        assert result.verdict == "FAIL"
        assert any("ID_REGRESSION" in d for d in result.deviations)

    def test_tool_disappeared_inconclusive(self):
        baseline = extract_fingerprint(
            _make_trajectory(
                tool_calls=["search_upstream_context", "read_wiki_page"],
            )
        )
        current = extract_fingerprint(
            _make_trajectory(
                tool_calls=["search_upstream_context"],  # read_wiki_page 消失
            )
        )
        result = compare_fingerprints(baseline, current)
        assert any("TOOL_DISAPPEARED" in d for d in result.deviations)

    def test_output_shrink_detected(self):
        baseline = extract_fingerprint(_make_trajectory(output_length=1000))
        current = extract_fingerprint(_make_trajectory(output_length=100))
        result = compare_fingerprints(baseline, current)
        assert any("OUTPUT_SHRINK" in d for d in result.deviations)

    def test_phase_a6_missing_dimensions(self):
        baseline = extract_fingerprint(
            _make_trajectory(
                phase_id="Q03",
                ids_in_output="ARCH-001 API-001 DATA-001 EXC-001 PERF-001",
            )
        )
        current = extract_fingerprint(
            _make_trajectory(
                phase_id="Q03",
                ids_in_output="ARCH-001 API-001",  # 缺少 DATA/EXC/PERF
            )
        )
        result = compare_fingerprints(baseline, current)
        assert any("INVARIANT" in d for d in result.deviations)

    def test_phase_a_min_req(self):
        baseline = extract_fingerprint(_make_trajectory(ids_in_output="REQ-001"))
        current = extract_fingerprint(_make_trajectory(ids_in_output=""))  # 无 REQ
        result = compare_fingerprints(baseline, current)
        assert any("INVARIANT" in d and "REQ" in d for d in result.deviations)


class TestExtractFromFile:
    def test_reads_jsonl(self):
        traj1 = _make_trajectory(tool_calls=["search_upstream_context"])
        traj2 = _make_trajectory(tool_calls=["read_wiki_page"])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(traj1) + "\n")
            f.write(json.dumps(traj2) + "\n")
            path = Path(f.name)
        fps = extract_fingerprints_from_file(path)
        assert len(fps) == 2
        path.unlink()

    def test_missing_file_returns_empty(self):
        fps = extract_fingerprints_from_file(Path("/nonexistent.jsonl"))
        assert fps == []
