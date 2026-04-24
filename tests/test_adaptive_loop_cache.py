from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from dqg.agents.adaptive_loop import AdaptiveLoop, multi_judge_vote
from dqg.agents.llm_backends import StructuredChatResult, _extract_json

if TYPE_CHECKING:
    from pathlib import Path


class _FakeBackend:
    def __init__(self, name: str, response: tuple[str, dict[str, int]]) -> None:
        self._name = name
        self._response = response
        self.calls = 0

    def chat(self, messages, **kwargs):
        del messages, kwargs
        self.calls += 1
        return self._response

    def chat_structured(self, messages, response_schema, **kwargs):
        del response_schema
        raw_text, usage = self.chat(messages, **kwargs)
        parsed = _extract_json(raw_text)
        return StructuredChatResult(parsed=parsed or {}, raw_text=raw_text, provider_meta={"usage": usage})

    def name(self) -> str:
        return self._name


def test_multi_judge_vote_reuses_agent_query_cache(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = tmp_path / "report.md"
    report_path.write_text("# report\n\nbody", encoding="utf-8")

    backend_by_model = {
        "judge-a": _FakeBackend(
            "judge-a",
            (
                json.dumps(
                    {"scores": {"quality": 5}, "overall": 4.5, "verdict": "PASS", "issues": []}, ensure_ascii=False
                ),
                {"input_tokens": 11, "output_tokens": 5},
            ),
        ),
        "judge-b": _FakeBackend(
            "judge-b",
            (
                json.dumps(
                    {"scores": {"quality": 4}, "overall": 4.0, "verdict": "PASS", "issues": []}, ensure_ascii=False
                ),
                {"input_tokens": 10, "output_tokens": 4},
            ),
        ),
    }

    monkeypatch.setattr(
        "dqg.agents.llm_backends.create_backend",
        lambda model, api_key: backend_by_model.get(model, backend_by_model.get("judge-a")),
    )
    monkeypatch.setattr(
        "dqg.quality.judge_runner.create_backend",
        lambda model, api_key: backend_by_model.get(model, backend_by_model.get("judge-a")),
    )

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
    assert backend_by_model["judge-a"].calls == 2
    assert backend_by_model["judge-b"].calls == 0


def test_multi_judge_vote_boundary_triggers_secondary(monkeypatch, tmp_path: Path) -> None:
    """当 primary 分数在边界区间时，secondary 应被调用."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = tmp_path / "report.md"
    report_path.write_text("# report\n\nbody", encoding="utf-8")

    backend_by_model = {
        "judge-a": _FakeBackend(
            "judge-a",
            (
                json.dumps(
                    {"scores": {"quality": 3}, "overall": 3.5, "verdict": "PASS_WITH_CONCERNS", "issues": []},
                    ensure_ascii=False,
                ),
                {"input_tokens": 11, "output_tokens": 5},
            ),
        ),
        "judge-b": _FakeBackend(
            "judge-b",
            (
                json.dumps(
                    {"scores": {"quality": 4}, "overall": 4.0, "verdict": "PASS", "issues": []}, ensure_ascii=False
                ),
                {"input_tokens": 10, "output_tokens": 4},
            ),
        ),
    }

    monkeypatch.setattr(
        "dqg.agents.llm_backends.create_backend",
        lambda model, api_key: backend_by_model.get(model, backend_by_model.get("judge-a")),
    )
    monkeypatch.setattr(
        "dqg.quality.judge_runner.create_backend",
        lambda model, api_key: backend_by_model.get(model, backend_by_model.get("judge-a")),
    )

    result = multi_judge_vote(
        output_dir,
        report_path,
        "judge rubric",
        ["judge-a", "judge-b"],
        fallback="fallback-model",
    )

    # Primary score=3.5 在边界区间 [3.0, 4.0]，secondary 应被调用
    assert len(result.votes) == 2
    assert backend_by_model["judge-a"].calls == 1
    assert backend_by_model["judge-b"].calls == 1


def test_adaptive_loop_passes_output_dir_to_all_agents(monkeypatch, tmp_path: Path) -> None:
    created: list[tuple[str, str | None]] = []

    class _FakeAgent:
        def __init__(self, name: str, role: str, system_prompt: str, model, output_dir=None) -> None:
            del system_prompt, model
            created.append((name, str(output_dir) if output_dir is not None else None))
            self.role = role

        def run(self, user_message: str, context_files=None):
            del user_message, context_files
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

    # Judge 直接调 LLM backend，mock 它
    class _FakeBackendInner:
        def chat(self, messages, **kwargs):
            return (
                json.dumps(
                    {"scores": {"quality": 2}, "overall": 2.0, "verdict": "FAIL", "issues": []}, ensure_ascii=False
                ),
                {"input_tokens": 10, "output_tokens": 5},
            )

        def chat_structured(self, messages, response_schema, **kwargs):
            raw_text, usage = self.chat(messages, **kwargs)
            parsed = _extract_json(raw_text)
            return StructuredChatResult(parsed=parsed or {}, raw_text=raw_text, provider_meta={"usage": usage})

        def name(self):
            return "fake"

    monkeypatch.setattr("dqg.agents.adaptive_loop.Agent", _FakeAgent)
    monkeypatch.setattr("dqg.agents.llm_backends.create_backend", lambda model, api_key: _FakeBackendInner())
    monkeypatch.setattr("dqg.quality.judge_runner.create_backend", lambda model, api_key: _FakeBackendInner())

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
