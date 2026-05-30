"""Tests for qualix.quality.trajectory."""

import json
import tempfile
from pathlib import Path

from qualix.quality.trajectory import (
    CompressedTrajectory,
    compress_trajectory,
    save_trajectories,
)


def _make_trajectory(turns: int = 8) -> list[dict[str, str]]:
    """生成一个模拟的多轮 trajectory."""
    messages = [
        {"role": "system", "content": "你是一个需求分析专家。按照 skill 执行 Phase A。"},
        {"role": "user", "content": "执行 Phase 任务，输出报告和结构化 JSON。"},
    ]
    for i in range(turns - 4):
        messages.append({
            "role": "assistant",
            "content": f'中间推理第 {i+1} 步...\n<tool_call name="search_upstream_context">\n{{"query_keyword": "工单"}}\n</tool_call>',
        })
        messages.append({
            "role": "user",
            "content": f'<tool_result name="search_upstream_context">\n{{"facts": [{{"id": "REQ-{i+1}", "desc": "工单创建需要校验幂等性" * 50}}]}}\n</tool_result>',
        })
    messages.append({"role": "assistant", "content": "# Phase A 报告\n\n## REQ-001\n工单创建..."})
    messages.append({"role": "assistant", "content": "最终输出完成。"})
    return messages


class TestCompressTrajectory:

    def test_basic_compression(self):
        traj = _make_trajectory(8)
        result = compress_trajectory(
            traj, project_id="test", phase_id="Q01",
            agent_name="worker", agent_role="worker",
        )
        assert isinstance(result, CompressedTrajectory)
        # _make_trajectory(8) 生成 2 头 + (8-4)*2 中间 + 2 尾 = 12 条
        assert result.original_turns == 12
        assert result.compressed_turns <= result.original_turns
        assert result.project_id == "test"
        assert result.phase_id == "Q01"

    def test_protects_head_and_tail(self):
        traj = _make_trajectory(8)
        result = compress_trajectory(traj, project_id="t", phase_id="Q01")
        # 头部 system + 首个 user 应该原样保留
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        # 尾部最终输出应该保留
        assert result.messages[-1]["content"] == traj[-1]["content"]

    def test_tool_results_are_summarized(self):
        traj = _make_trajectory(8)
        result = compress_trajectory(traj, project_id="t", phase_id="Q01")
        for msg in result.messages:
            if "tool_result" in msg.get("content", ""):
                # tool_result 内容应该被截断
                assert len(msg["content"]) <= 600  # 500 limit + tag overhead

    def test_empty_trajectory(self):
        result = compress_trajectory([], project_id="t", phase_id="Q01")
        assert result.original_turns == 0
        assert result.compressed_turns == 0
        assert result.messages == []

    def test_short_trajectory_no_compression(self):
        traj = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "do task"},
            {"role": "assistant", "content": "done"},
        ]
        result = compress_trajectory(traj, project_id="t", phase_id="Q01")
        assert result.original_turns == 3
        assert result.compressed_turns == 3


class TestSaveTrajectories:

    def test_saves_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            traj = compress_trajectory(
                _make_trajectory(6), project_id="proj1", phase_id="Q01",
                agent_name="worker", agent_role="worker",
            )
            path = save_trajectories(output_dir, "proj1", "Q01", [traj])
            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["project_id"] == "proj1"
            assert data["phase_id"] == "Q01"
            assert "messages" in data

    def test_appends_multiple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            t1 = compress_trajectory(
                _make_trajectory(6), project_id="p", phase_id="Q01",
                agent_name="worker", agent_role="worker",
            )
            t2 = compress_trajectory(
                _make_trajectory(6), project_id="p", phase_id="Q01",
                agent_name="judge", agent_role="judge",
            )
            save_trajectories(output_dir, "p", "Q01", [t1])
            save_trajectories(output_dir, "p", "Q01", [t2])
            path = output_dir / "p" / "_trajectories" / "Q01.jsonl"
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2
