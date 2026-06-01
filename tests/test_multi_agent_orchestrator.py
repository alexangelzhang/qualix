"""Tests for agent_orchestrator.AgentOrchestrator run_pipeline() and
concurrent-Critique behaviour (U10).

Note: MultiAgentOrchestrator.run_phase() was removed as a shallow wrapper.
Callers should use AgentOrchestrator.run_pipeline() directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from qualix.agents.agent import AgentResult
from qualix.agents.agent_orchestrator import AgentOrchestrator
from qualix.agents.multi_agent import MultiAgentOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_result(role: str, status: str = "success") -> AgentResult:
    return AgentResult(
        agent_name=f"test-Q01-{role}",
        role=role,
        status=status,
        content=f"mock {role} output",
        model_used="mock-model",
    )


# ---------------------------------------------------------------------------
# AgentOrchestrator.run_pipeline() core behaviour
# ---------------------------------------------------------------------------


class TestRunPhase:
    def test_run_pipeline_returns_results(self, tmp_path: Path):
        """run_pipeline() 应当执行 Worker→Judge→Critique 并返回结果 dict."""
        expected_results = {
            "worker": _make_agent_result("worker"),
            "judge": _make_agent_result("judge"),
            "critique": _make_agent_result("critique"),
        }

        orch = AgentOrchestrator(tmp_path)
        with (
            patch.object(orch, "_run_worker") as mock_worker,
            patch.object(orch, "_run_judge") as mock_judge,
            patch.object(orch, "_run_critique") as mock_critique,
            patch.object(orch, "_save_trajectories"),
            patch.object(orch, "_auto_remediate_gaps"),
        ):
            w_result = _make_agent_result("worker")
            mock_worker.return_value = (
                w_result,
                tmp_path / "Q01",
                tmp_path / "Q01" / "report.md",
                None,
            )
            mock_judge.return_value = (_make_agent_result("judge"), tmp_path / "Q01" / "_det.md")
            mock_critique.return_value = _make_agent_result("critique")

            result = orch.run_pipeline(
                project_id="test-project",
                phase_id="Q01",
                worker_prompt="wp",
                judge_rubric="jr",
                critique_prompt="cp",
            )

        assert result["worker"].status == "success"
        assert result["judge"].status == "success"
        assert result["critique"].status == "success"

    def test_run_pipeline_stops_after_worker_failure(self, tmp_path: Path):
        """Worker 失败时 pipeline 提前返回，不启动 Judge 和 Critique."""
        orch = AgentOrchestrator(tmp_path)
        with (
            patch.object(orch, "_run_worker") as mock_worker,
            patch.object(orch, "_run_judge") as mock_judge,
            patch.object(orch, "_run_critique") as mock_critique,
        ):
            failed = _make_agent_result("worker", "failed")
            mock_worker.return_value = (
                failed,
                tmp_path / "Q01",
                tmp_path / "Q01" / "report.md",
                None,
            )

            result = orch.run_pipeline(
                project_id="proj",
                phase_id="Q01",
                worker_prompt="wp",
                judge_rubric="jr",
                critique_prompt="cp",
            )

        assert "judge" not in result
        mock_judge.assert_not_called()
        mock_critique.assert_not_called()

    def test_run_pipeline_returns_cleanly_when_all_succeed(self, tmp_path: Path):
        """三个 agent 均成功时返回完整 dict，无异常."""
        orch = AgentOrchestrator(tmp_path)
        with (
            patch.object(orch, "_run_worker") as mock_worker,
            patch.object(orch, "_run_judge") as mock_judge,
            patch.object(orch, "_run_critique") as mock_critique,
            patch.object(orch, "_save_trajectories"),
            patch.object(orch, "_auto_remediate_gaps"),
        ):
            mock_worker.return_value = (
                _make_agent_result("worker"),
                tmp_path / "Q01",
                tmp_path / "Q01" / "r.md",
                None,
            )
            mock_judge.return_value = (_make_agent_result("judge"), tmp_path / "Q01" / "_d.md")
            mock_critique.return_value = _make_agent_result("critique")

            returned = orch.run_pipeline(
                project_id="proj",
                phase_id="Q01",
                worker_prompt="wp",
                judge_rubric="jr",
                critique_prompt="cp",
            )

        assert returned["worker"].status == "success"
        assert returned["judge"].status == "success"
        assert returned["critique"].status == "success"


# ---------------------------------------------------------------------------
# AgentOrchestrator: Critique dispatched after Judge completes
# ---------------------------------------------------------------------------


class TestCritiqueAfterJudge:
    """Verify that Critique is only started after Judge result file exists,
    and that the call ordering in run_pipeline() is Worker → Judge → Critique.
    """

    def test_critique_dispatched_after_judge_result(self, tmp_path: Path):
        """Critique 开始时，_judge_result_v2.json 应当已经存在."""
        from qualix.agents.agent_orchestrator import AgentOrchestrator

        call_order: list[str] = []

        worker_result = _make_agent_result("worker")
        judge_result = _make_agent_result("judge")
        critique_result = _make_agent_result("critique")

        def fake_run_worker(*args, **kwargs):
            call_order.append("worker")
            pd = tmp_path / "Q01"
            pd.mkdir(parents=True, exist_ok=True)
            worker_output = pd / "_worker_output.md"
            worker_output.write_text("worker output", encoding="utf-8")
            return worker_result, pd, worker_output, None

        def fake_run_judge(*args, **kwargs):
            call_order.append("judge")
            pd = tmp_path / "Q01"
            judge_file = pd / "_judge_result_v2.json"
            judge_file.write_text('{"score": 4}', encoding="utf-8")
            det_path = pd / "_deterministic_check.md"
            det_path.write_text("# det", encoding="utf-8")
            return judge_result, det_path

        def fake_run_critique(*args, **kwargs):
            # 此时 Judge 文件应当已存在
            pd = tmp_path / "Q01"
            assert (pd / "_judge_result_v2.json").exists(), (
                "Judge result file must exist before Critique starts"
            )
            call_order.append("critique")
            return critique_result

        orch = AgentOrchestrator(tmp_path)

        with (
            patch.object(orch, "_run_worker", side_effect=fake_run_worker),
            patch.object(orch, "_run_judge", side_effect=fake_run_judge),
            patch.object(orch, "_run_critique", side_effect=fake_run_critique),
            patch.object(orch, "_save_trajectories"),
            patch(
                "qualix.agents.agent_orchestrator.build_builtin_tools",
                return_value=[],
            ),
        ):
            results = orch.run_pipeline(
                project_id="test",
                phase_id="Q01",
                worker_prompt="wp",
                judge_rubric="jr",
                critique_prompt="cp",
            )

        assert call_order == ["worker", "judge", "critique"], (
            f"Expected Worker → Judge → Critique ordering, got {call_order}"
        )
        assert results["worker"].status == "success"
        assert results["judge"].status == "success"
        assert results["critique"].status == "success"

    def test_pipeline_stops_after_worker_failure(self, tmp_path: Path):
        """Worker 失败时 run_pipeline() 应当提前返回，不执行 Judge/Critique."""
        from qualix.agents.agent_orchestrator import AgentOrchestrator

        worker_result = _make_agent_result("worker", status="failed")

        def fake_run_worker(*args, **kwargs):
            pd = tmp_path / "Q01"
            pd.mkdir(parents=True, exist_ok=True)
            wo = pd / "_worker_output.md"
            wo.write_text("", encoding="utf-8")
            return worker_result, pd, wo, None

        orch = AgentOrchestrator(tmp_path)
        mock_judge = MagicMock()
        mock_critique = MagicMock()

        with (
            patch.object(orch, "_run_worker", side_effect=fake_run_worker),
            patch.object(orch, "_run_judge", mock_judge),
            patch.object(orch, "_run_critique", mock_critique),
            patch(
                "qualix.agents.agent_orchestrator.build_builtin_tools",
                return_value=[],
            ),
        ):
            results = orch.run_pipeline(
                project_id="test",
                phase_id="Q01",
                worker_prompt="wp",
                judge_rubric="jr",
                critique_prompt="cp",
            )

        assert results["worker"].status == "failed"
        assert "judge" not in results
        assert "critique" not in results
        mock_judge.assert_not_called()
        mock_critique.assert_not_called()
