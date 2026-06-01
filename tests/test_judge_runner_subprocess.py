"""Tests for judge_runner_subprocess — JudgeRunner subprocess wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def _make_fake_judge_result():
    """Return a real JudgeResult dataclass with known values."""
    from qualix.quality.judge.judge_runner import JudgeResult

    return JudgeResult(
        overall_score=4.2,
        verdict="PASS",
        dimensions=[{"id": "D1", "name": "Coverage", "score": 4, "weight": 1, "issues": []}],
        issues=[],
        raw_output="Good report.",
        health="HEALTHY",
        model="claude-sonnet-4-6",
        duration=1.5,
        token_usage={"input_tokens": 100, "output_tokens": 50},
        failing_dimensions=[],
    )


def _subprocess_env() -> dict[str, str]:
    """Build env dict with worktree src on PYTHONPATH for subprocess calls."""
    env = os.environ.copy()
    worktree_src = str(Path(__file__).parent.parent / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{worktree_src}:{existing}" if existing else worktree_src
    return env


class TestJudgeRunnerSubprocess:
    """Tests for judge_runner_subprocess module."""

    def test_valid_round_trip(self, tmp_path: Path) -> None:
        """Mock JudgeRunner.run and verify run_subprocess serializes result correctly.

        Calls run_subprocess() in-process (not as a subprocess) so that
        unittest.mock.patch can intercept JudgeRunner.run.
        Verifies:
          - output has verdict, overall_score, issues fields
          - schema_version is explicitly serialized (dataclasses.asdict skips _schema_version)
          - output JSON contains no <thinking> content
        """
        from qualix.agents.judge_runner_subprocess import run_subprocess

        report_file = tmp_path / "phase_a_report.md"
        report_file.write_text("# Fake report", encoding="utf-8")

        input_data = {
            "report_path": str(report_file),
            "output_dir": str(tmp_path),
            "model": "claude-sonnet-4-6",
            "fallback": None,
            "rubric": "Test rubric",
            "warning_override": None,
            "rubric_dims": None,
        }

        fake_result = _make_fake_judge_result()

        with patch("qualix.quality.judge_runner.JudgeRunner.run", return_value=fake_result):
            result_dict = run_subprocess(input_data)

        # Required fields
        assert "verdict" in result_dict, "Missing 'verdict' in output"
        assert "overall_score" in result_dict, "Missing 'overall_score' in output"
        assert "issues" in result_dict, "Missing 'issues' in output"

        # schema_version must be explicitly included (dataclasses.asdict drops _schema_version)
        assert "schema_version" in result_dict, "Missing 'schema_version' — asdict() bug would cause this"
        assert result_dict["schema_version"] == 1

        # Verify actual values from mock
        assert result_dict["verdict"] == "PASS"
        assert result_dict["overall_score"] == 4.2

        # Context isolation guarantee: no <thinking> content in serialized output
        output_text = json.dumps(result_dict)
        assert "<thinking>" not in output_text, "Output must not contain <thinking> content"

    def test_missing_input_file_exits_with_code_1(self, tmp_path: Path) -> None:
        """Subprocess with --input pointing to nonexistent file exits with code 1."""
        output_file = tmp_path / "output.json"
        env = _subprocess_env()

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "qualix.agents.judge_runner_subprocess",
                "--input",
                str(tmp_path / "nonexistent_input.json"),
                "--output",
                str(output_file),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

        assert proc.returncode == 1, f"Expected exit code 1; got {proc.returncode}"
        assert proc.stderr.strip(), "Expected error message in stderr"

    def test_help_exits_with_code_0(self) -> None:
        """--help must exit with code 0."""
        env = _subprocess_env()

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "qualix.agents.judge_runner_subprocess",
                "--help",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        assert proc.returncode == 0, f"--help exited with {proc.returncode}; stderr: {proc.stderr}"
