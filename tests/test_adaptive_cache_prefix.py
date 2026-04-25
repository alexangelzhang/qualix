"""Test that AdaptiveLoop keeps static context_files byte-identical across iterations.

Worker (iter 1): context_files=evidence, dynamic_context_files=None
Fixer  (iter 2): context_files=SAME evidence, dynamic_context_files=[handoff, report]
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _make_fake_result(role: str = "worker") -> SimpleNamespace:
    return SimpleNamespace(
        status="success",
        content="## 报告\n内容",
        model_used="fake-model",
        duration_seconds=0.01,
        agent_name=role,
        role=role,
        token_usage={"input_tokens": 10, "output_tokens": 5},
        cache_hit=False,
        prompt_hash="fake",
    )


def _make_vote_result(verdict: str, score: float):
    from dqg.agents.judge_vote import JudgeVote, VoteResult

    vote = JudgeVote(model="fake-judge", verdict=verdict, overall=score, scores={}, issues=[])
    return VoteResult(votes=[vote], consensus=verdict, avg_score=score, disagreements=[])


def test_fixer_uses_dynamic_context_files(monkeypatch, tmp_path: Path) -> None:
    """Fixer iteration must pass handoff+report as dynamic_context_files, not prepend to context_files."""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    # Track all Agent.run() calls: list of (name, context_files, dynamic_context_files)
    run_calls: list[tuple[str, list | None, list | None]] = []

    class _FakeAgent:
        def __init__(self, name: str, role: str, system_prompt: str, model, output_dir=None) -> None:
            self._name = name
            self.role = role

        def run(self, user_message: str, context_files=None, dynamic_context_files=None):
            run_calls.append((self._name, list(context_files) if context_files else None, dynamic_context_files))
            return _make_fake_result(self.role)

    # Judge: FAIL on first call, PASS on second
    judge_call_count = [0]

    def _fake_multi_judge_vote(output_dir, report_path, judge_rubric, judge_models, fallback, **kwargs):
        judge_call_count[0] += 1
        if judge_call_count[0] == 1:
            return _make_vote_result("FAIL", 1.0)
        return _make_vote_result("PASS", 5.0)

    monkeypatch.setattr("dqg.agents.adaptive_loop.Agent", _FakeAgent)
    monkeypatch.setattr("dqg.agents.adaptive_loop.multi_judge_vote", _fake_multi_judge_vote)

    # Stub out task_store functions
    monkeypatch.setattr("dqg.runtime.task_store.create_task_run", lambda *a, **kw: "task-1")
    monkeypatch.setattr("dqg.runtime.task_store.complete_task_run", lambda *a, **kw: None)
    monkeypatch.setattr("dqg.runtime.task_store.add_task_event", lambda *a, **kw: None)
    monkeypatch.setattr("dqg.runtime.task_store.save_checkpoint", lambda *a, **kw: None)

    # Create fake evidence files
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    ev1 = evidence_dir / "evidence1.md"
    ev2 = evidence_dir / "evidence2.md"
    ev1.write_text("evidence 1", encoding="utf-8")
    ev2.write_text("evidence 2", encoding="utf-8")

    loop = AdaptiveLoop(tmp_path / "output")
    loop.run(
        project_id="demo",
        phase_id="Q01",
        worker_prompt="worker prompt",
        judge_rubric="judge rubric",
        critique_prompt="critique prompt",
        context_files=[ev1, ev2],
        max_iterations=3,
        judge_models=["judge-a"],
        fallback="fallback-model",
    )

    # Filter to worker/fixer calls only (not critique)
    worker_fixer_calls = [(name, cf, dcf) for name, cf, dcf in run_calls if "critique" not in name]
    assert len(worker_fixer_calls) >= 2, f"Expected at least 2 worker/fixer calls, got: {run_calls}"

    worker_name, worker_cf, worker_dcf = worker_fixer_calls[0]
    fixer_name, fixer_cf, fixer_dcf = worker_fixer_calls[1]

    assert "worker" in worker_name, f"First call should be worker, got: {worker_name}"
    assert "fixer" in fixer_name, f"Second call should be fixer, got: {fixer_name}"

    # Worker: dynamic_context_files should be None
    assert worker_dcf is None, f"Worker should have no dynamic_context_files, got: {worker_dcf}"

    # Fixer: context_files must be byte-identical to worker's (same evidence, no handoff prepended)
    assert worker_cf == fixer_cf, (
        f"Static context_files must be identical between worker and fixer.\nWorker: {worker_cf}\nFixer:  {fixer_cf}"
    )

    # Fixer: dynamic_context_files must contain handoff + report (2 files)
    assert fixer_dcf is not None, "Fixer must have dynamic_context_files"
    assert len(fixer_dcf) == 2, f"Fixer dynamic_context_files should have 2 files (handoff+report), got: {fixer_dcf}"

    # The dynamic files should include a handoff doc and the report
    dynamic_names = [str(p.name) for p in fixer_dcf]
    assert any("handoff" in n for n in dynamic_names), (
        f"Expected handoff file in dynamic_context_files: {dynamic_names}"
    )
