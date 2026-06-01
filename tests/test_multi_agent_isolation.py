"""Tests for U9: context isolation via subprocess dispatch.

Verifies:
1. Context isolation — Worker <thinking> content never leaks into JudgeVote output.
2. Subprocess failure → RuntimeError raised.
3. Concurrent dispatch via multi_judge_vote produces consensus from both models.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_judge_result_dict(
    model: str = "claude-sonnet-4-6",
    overall_score: float = 4.2,
    verdict: str = "PASS",
) -> dict:
    """Build a serialized JudgeResult dict (as judge_runner_subprocess would write)."""
    return {
        "overall_score": overall_score,
        "verdict": verdict,
        "dimensions": [{"id": "D1", "name": "Coverage", "score": 4, "weight": 1, "issues": []}],
        "issues": [],
        "raw_output": "Good report.",
        "health": "HEALTHY",
        "model": model,
        "duration": 1.5,
        "token_usage": {"input_tokens": 100, "output_tokens": 50},
        "failing_dimensions": [],
        "schema_version": 1,
    }


def _make_completed_process_ok(output_json_path: Path, result_dict: dict) -> CompletedProcess:
    """Side-effect factory: writes result JSON to output_path and returns exit-0 process."""
    def _side_effect(cmd, **kwargs):
        # Find --output argument in cmd
        out_idx = cmd.index("--output") + 1
        out_path = Path(cmd[out_idx])
        out_path.write_text(json.dumps(result_dict, ensure_ascii=False), encoding="utf-8")
        return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    return _side_effect


# ---------------------------------------------------------------------------
# Test 1: Context isolation
# ---------------------------------------------------------------------------


class TestContextIsolation:
    """Worker <thinking> content must not appear in JudgeVote output."""

    def test_thinking_content_not_in_judge_vote(self, tmp_path: Path) -> None:
        """Even if the report contains <thinking>SECRET WORKER DATA</thinking>,
        the returned JudgeVote must not contain that string.

        The subprocess mock returns clean JSON — simulating that the judge process
        never had access to the Worker's reasoning traces.
        """
        from qualix.agents.judge_vote import _run_single_judge

        # Create a fake report with embedded <thinking> content
        report_file = tmp_path / "Q01" / "phase_a_report.md"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            "# Phase A Report\n\n<thinking>SECRET WORKER DATA</thinking>\n\nSome analysis.",
            encoding="utf-8",
        )

        result_dict = _make_judge_result_dict()
        side_effect = _make_completed_process_ok(tmp_path, result_dict)

        with patch("subprocess.run", side_effect=side_effect):
            vote = _run_single_judge(
                output_dir=tmp_path,
                report_path=report_file,
                rubric="Test rubric",
                model="claude-sonnet-4-6",
                fallback="claude-haiku-4-6",
            )

        assert vote is not None, "Expected a JudgeVote, got None"

        # Serialize entire vote to JSON and check for thinking leakage
        vote_text = json.dumps(
            {
                "model": vote.model,
                "scores": vote.scores,
                "overall": vote.overall,
                "verdict": vote.verdict,
                "issues": vote.issues,
                "raw_output": vote.raw_output,
                "health": vote.health,
                "token_usage": vote.token_usage,
            },
            ensure_ascii=False,
        )
        assert "<thinking>" not in vote_text, (
            "JudgeVote output must not contain <thinking> content — "
            "subprocess isolation should have prevented leakage"
        )
        assert "SECRET WORKER DATA" not in vote_text

        # Sanity-check returned values match the mocked subprocess output
        assert vote.verdict == "PASS"
        assert vote.overall == 4.2
        assert vote.model == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Test 2: Subprocess failure → RuntimeError
# ---------------------------------------------------------------------------


class TestSubprocessFailure:
    """Non-zero subprocess exit must raise RuntimeError."""

    def test_subprocess_exit_1_raises_runtime_error(self, tmp_path: Path) -> None:
        """Mock subprocess.run to return exit code 1 and verify RuntimeError is raised."""
        import pytest

        from qualix.agents.judge_vote import _run_single_judge

        report_file = tmp_path / "phase_a_report.md"
        report_file.write_text("# Report", encoding="utf-8")

        failed_proc = CompletedProcess(
            args=[], returncode=1, stdout="", stderr="model error: rate limit exceeded"
        )

        with patch("subprocess.run", return_value=failed_proc):
            with pytest.raises(RuntimeError, match="Judge subprocess failed"):
                _run_single_judge(
                    output_dir=tmp_path,
                    report_path=report_file,
                    rubric="Test rubric",
                    model="claude-sonnet-4-6",
                    fallback="claude-haiku-4-6",
                )

    def test_subprocess_failure_stderr_in_message(self, tmp_path: Path) -> None:
        """RuntimeError message should include a fragment of stderr."""
        import pytest

        from qualix.agents.judge_vote import _run_single_judge

        report_file = tmp_path / "phase_a_report.md"
        report_file.write_text("# Report", encoding="utf-8")

        failed_proc = CompletedProcess(
            args=[], returncode=1, stdout="", stderr="specific error detail here"
        )

        with patch("subprocess.run", return_value=failed_proc):
            with pytest.raises(RuntimeError) as exc_info:
                _run_single_judge(
                    output_dir=tmp_path,
                    report_path=report_file,
                    rubric="Test rubric",
                    model="claude-sonnet-4-6",
                    fallback=None,
                )

        assert "specific error detail here" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 3: Concurrent dispatch via multi_judge_vote
# ---------------------------------------------------------------------------


class TestConcurrentDispatch:
    """multi_judge_vote with two models must collect both votes and compute consensus."""

    def test_two_model_concurrent_dispatch(self, tmp_path: Path) -> None:
        """Both subprocess calls return valid results; consensus is computed."""
        from qualix.agents.judge_vote import multi_judge_vote

        report_file = tmp_path / "proj" / "Q03" / "phase_a_report.md"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text("# Report\n\nAnalysis content.", encoding="utf-8")

        result_a = _make_judge_result_dict(model="model-a", overall_score=4.5, verdict="PASS")
        result_b = _make_judge_result_dict(model="model-b", overall_score=4.0, verdict="PASS")

        call_count = {"n": 0}

        def _side_effect(cmd, **kwargs):
            # Determine which model this call is for by reading the input file
            in_idx = cmd.index("--input") + 1
            in_path = Path(cmd[in_idx])
            out_idx = cmd.index("--output") + 1
            out_path = Path(cmd[out_idx])

            input_data = json.loads(in_path.read_text(encoding="utf-8"))
            model = input_data["model"]
            result = result_a if model == "model-a" else result_b
            # Update model field in result to match requested model
            result = dict(result, model=model)
            out_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            call_count["n"] += 1
            return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        # Patch the rationalization and overcorrection guards to pass through
        with (
            patch("subprocess.run", side_effect=_side_effect),
            patch(
                "qualix.agents.judge_vote_guards.apply_rationalization_guard",
                side_effect=lambda primary_vote, **kwargs: primary_vote,
            ),
            patch(
                "qualix.agents.judge_vote_guards.apply_overcorrection_guard",
                side_effect=lambda primary_vote, **kwargs: primary_vote,
            ),
        ):
            vote_result = multi_judge_vote(
                output_dir=tmp_path,
                report_path=report_file,
                rubric="Test rubric",
                models=["model-a", "model-b"],
                fallback=None,
                force_secondary=True,  # force secondary so both models are called
            )

        assert vote_result is not None, "multi_judge_vote returned None unexpectedly"
        assert len(vote_result.votes) == 2, (
            f"Expected 2 votes (one per model), got {len(vote_result.votes)}"
        )
        model_names = {v.model for v in vote_result.votes}
        assert "model-a" in model_names
        assert "model-b" in model_names
        assert vote_result.consensus in {"PASS", "PASS_WITH_CONCERNS", "FAIL"}
        # Both PASS → consensus should be PASS
        assert vote_result.consensus == "PASS"
