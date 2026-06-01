"""Tests for multi_agent.MultiAgentOrchestrator.run_phase() and
agent_orchestrator.AgentOrchestrator concurrent-Critique behaviour (U10).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from qualix.agents.agent import AgentResult
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
# MultiAgentOrchestrator.run_phase() delegates to AgentOrchestrator
# ---------------------------------------------------------------------------


class TestRunPhase:
    def test_run_phase_calls_run_pipeline_and_returns_result(self, tmp_path: Path):
        """run_phase() 应当调用 AgentOrchestrator.run_pipeline() 并返回其结果."""
        expected_results = {
            "worker": _make_agent_result("worker"),
            "judge": _make_agent_result("judge"),
            "critique": _make_agent_result("critique"),
        }

        with patch(
            "qualix.agents.agent_orchestrator.AgentOrchestrator"
        ) as MockOrchestrator:
            mock_instance = MagicMock()
            mock_instance.run_pipeline.return_value = expected_results
            MockOrchestrator.return_value = mock_instance

            orchestrator = MultiAgentOrchestrator(tmp_path)
            result = orchestrator.run_phase("test-project", "Q01")

        assert result is expected_results
        mock_instance.run_pipeline.assert_called_once()
        call_kwargs = mock_instance.run_pipeline.call_args
        assert call_kwargs.kwargs["project_id"] == "test-project"
        assert call_kwargs.kwargs["phase_id"] == "Q01"

    def test_run_phase_passes_worker_judge_critique_prompts(self, tmp_path: Path):
        """run_phase() 应当向 run_pipeline() 传入三个 prompt 参数."""
        with patch(
            "qualix.agents.agent_orchestrator.AgentOrchestrator"
        ) as MockOrchestrator:
            mock_instance = MagicMock()
            mock_instance.run_pipeline.return_value = {}
            MockOrchestrator.return_value = mock_instance

            orchestrator = MultiAgentOrchestrator(tmp_path)
            orchestrator.run_phase("proj", "Q01", inputs={"prd_url": "https://example.com"})

        _, kwargs = mock_instance.run_pipeline.call_args
        assert "worker_prompt" in kwargs
        assert "judge_rubric" in kwargs
        assert "critique_prompt" in kwargs
        assert kwargs["worker_prompt"]   # 非空
        assert kwargs["judge_rubric"]    # 非空
        assert kwargs["critique_prompt"] # 非空

    def test_run_phase_returns_cleanly_when_all_succeed(self, tmp_path: Path):
        """run_phase() 三个 agent 均成功时返回完整 dict，无异常."""
        results = {
            "worker": _make_agent_result("worker"),
            "judge": _make_agent_result("judge"),
            "critique": _make_agent_result("critique"),
        }
        with patch(
            "qualix.agents.agent_orchestrator.AgentOrchestrator"
        ) as MockOrchestrator:
            mock_instance = MagicMock()
            mock_instance.run_pipeline.return_value = results
            MockOrchestrator.return_value = mock_instance

            orchestrator = MultiAgentOrchestrator(tmp_path)
            returned = orchestrator.run_phase("proj", "Q01")

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


# ---------------------------------------------------------------------------
# _run_critique_subprocess: graceful fallback when module not available
# ---------------------------------------------------------------------------


class TestRunCritiqueSubprocess:
    def test_fallback_when_subprocess_unavailable(self, tmp_path: Path):
        """_run_critique_subprocess 应当在 critique_runner_subprocess 不存在时回退到主进程."""
        from qualix.agents import agent_orchestrator

        pd = tmp_path / "Q01"
        pd.mkdir(parents=True, exist_ok=True)
        report_path = pd / "phase_a_report.md"
        report_path.write_text("# report", encoding="utf-8")
        judge_path = pd / "_judge_result_v2.json"
        judge_path.write_text('{"score": 3}', encoding="utf-8")

        critique_result = _make_agent_result("critique")

        orch = agent_orchestrator.AgentOrchestrator(tmp_path)

        # 确保 _CRITIQUE_SUBPROCESS_AVAILABLE = False 时走 fallback 路径
        with (
            patch.object(agent_orchestrator, "_CRITIQUE_SUBPROCESS_AVAILABLE", False),
            patch(
                "qualix.agents.agent_orchestrator.build_builtin_tools",
                return_value=[],
            ),
            patch(
                "qualix.agents.agent_orchestrator.filter_tools_by_role",
                return_value=[],
            ),
            patch.object(orch, "create_critique") as mock_create_critique,
        ):
            mock_agent = MagicMock()
            mock_agent.run.return_value = critique_result
            mock_create_critique.return_value = mock_agent

            result = orch._run_critique_subprocess(
                output_dir=tmp_path,
                project_id="test",
                phase_id="Q01",
                critique_prompt="cp",
                report_path=report_path,
                judge_result_path=judge_path,
            )

        assert result.status == "success"
        mock_agent.run.assert_called_once()
