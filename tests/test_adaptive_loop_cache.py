from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from qualix.agents.adaptive_loop import AdaptiveLoop, multi_judge_vote
from qualix.agents.judge_vote import JudgeVote

if TYPE_CHECKING:
    from pathlib import Path


def _make_judge_vote(model: str, overall: float, verdict: str) -> JudgeVote:
    return JudgeVote(
        model=model,
        scores={"quality": int(overall)},
        overall=overall,
        verdict=verdict,
        issues=[],
        duration=0.01,
        raw_output="",
        health="HEALTHY",
        token_usage={"input_tokens": 10, "output_tokens": 5},
    )


def test_multi_judge_vote_reuses_agent_query_cache(monkeypatch, tmp_path: Path) -> None:
    """Primary judge score=4.5 (clear PASS) → secondary not called.

    Now uses subprocess dispatch: mock _run_single_judge directly to count calls.
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = tmp_path / "report.md"
    report_path.write_text("# report\n\nbody", encoding="utf-8")

    call_counts: dict[str, int] = {"judge-a": 0, "judge-b": 0}
    vote_by_model = {
        "judge-a": _make_judge_vote("judge-a", 4.5, "PASS"),
        "judge-b": _make_judge_vote("judge-b", 4.0, "PASS"),
    }

    def _fake_run_single_judge(output_dir, report_path, rubric, model, fallback, warning_override=None):
        call_counts[model] = call_counts.get(model, 0) + 1
        return vote_by_model.get(model)

    monkeypatch.setattr("qualix.agents.judge_vote._run_single_judge", _fake_run_single_judge)

    first = multi_judge_vote(
        output_dir,
        report_path,
        "judge rubric",
        ["judge-a", "judge-b"],
        fallback="fallback-model",
    )
    second = multi_judge_vote(
        output_dir,
        report_path,
        "judge rubric",
        ["judge-a", "judge-b"],
        fallback="fallback-model",
    )

    # Primary judge score=4.5 明确 PASS（不在边界区间），secondary 不被调用
    assert first.consensus == "PASS"
    assert second.consensus == "PASS"
    assert [vote.model for vote in first.votes] == ["judge-a"]
    assert [vote.model for vote in second.votes] == ["judge-a"]
    # Primary 每次调用一次，secondary 不被调用
    assert call_counts["judge-a"] == 2
    assert call_counts.get("judge-b", 0) == 0


def test_multi_judge_vote_boundary_triggers_secondary(monkeypatch, tmp_path: Path) -> None:
    """当 primary 分数在边界区间时，secondary 应被调用."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = tmp_path / "report.md"
    report_path.write_text("# report\n\nbody", encoding="utf-8")

    call_counts: dict[str, int] = {}
    vote_by_model = {
        "judge-a": _make_judge_vote("judge-a", 3.5, "PASS_WITH_CONCERNS"),
        "judge-b": _make_judge_vote("judge-b", 4.0, "PASS"),
    }

    def _fake_run_single_judge(output_dir, report_path, rubric, model, fallback, warning_override=None):
        call_counts[model] = call_counts.get(model, 0) + 1
        return vote_by_model.get(model)

    monkeypatch.setattr("qualix.agents.judge_vote._run_single_judge", _fake_run_single_judge)

    result = multi_judge_vote(
        output_dir,
        report_path,
        "judge rubric",
        ["judge-a", "judge-b"],
        fallback="fallback-model",
    )

    # Primary score=3.5 在边界区间 [3.0, 4.0]，secondary 应被调用
    assert len(result.votes) == 2
    assert call_counts["judge-a"] == 1
    assert call_counts["judge-b"] == 1


def test_adaptive_loop_passes_output_dir_to_all_agents(monkeypatch, tmp_path: Path) -> None:
    created: list[tuple[str, str | None]] = []

    class _FakeAgent:
        def __init__(self, name: str, role: str, system_prompt: str, model, output_dir=None) -> None:
            del system_prompt, model
            created.append((name, str(output_dir) if output_dir is not None else None))
            self.role = role

        def run(self, user_message: str, context_files=None, dynamic_context_files=None):
            del user_message, context_files, dynamic_context_files
            content = "report body"
            return SimpleNamespace(
                status="success",
                content=content,
                model_used="fake-model",
                duration_seconds=0.01,
                agent_name=self.role,
                role=self.role,
                token_usage={"input_tokens": 10, "output_tokens": 5},
                cache_hit=False,
                prompt_hash="fake",
            )

    # Judge 现在通过 subprocess 调用，直接 mock _run_single_judge 返回 FAIL vote
    def _fake_run_single_judge(output_dir, report_path, rubric, model, fallback, warning_override=None):
        return _make_judge_vote(model, 2.0, "FAIL")

    monkeypatch.setattr("qualix.agents.adaptive_loop.Agent", _FakeAgent)
    monkeypatch.setattr("qualix.agents.judge_vote._run_single_judge", _fake_run_single_judge)

    loop = AdaptiveLoop(tmp_path / "output")
    loop.run(
        project_id="demo",
        phase_id="Q01",
        worker_prompt="worker prompt",
        judge_rubric="judge prompt",
        critique_prompt="critique prompt",
        max_iterations=2,
        judge_models=["judge-a"],
        fallback="fallback-model",
    )

    assert created
    assert all(output_dir == str(tmp_path / "output") for _, output_dir in created)
    assert any(name.startswith("worker-iter1") for name, _ in created)
    # Judge 不再用 Agent，不检查
    assert any(name.startswith("fixer-iter2") for name, _ in created)
    assert any(name.startswith("critique-iter") for name, _ in created)
