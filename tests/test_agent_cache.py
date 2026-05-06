from __future__ import annotations

import json
from pathlib import Path

from dqg.agents.agent import Agent
from dqg.agents.llm_backends import LLMConfig
from dqg.core.state_machine import PHASE_DEFS
from dqg.store import get_connection


class _FakeBackend:
    def __init__(self, name: str, responses: list[tuple[str, dict[str, int]]]):
        self._name = name
        self._responses = responses
        self.calls = 0

    def chat(self, messages, **kwargs):
        if self.calls >= len(self._responses):
            raise AssertionError("unexpected extra chat call")
        response = self._responses[self.calls]
        self.calls += 1
        return response

    def name(self) -> str:
        return self._name


def _phase_root(output_dir: Path, project_id: str, phase_id: str) -> Path:
    return output_dir / project_id / PHASE_DEFS[phase_id]["dir_suffix"]


def test_agent_run_caches_final_response_and_reuses_it(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    phase_root = _phase_root(output_dir, "demo", "Q05")
    phase_root.mkdir(parents=True, exist_ok=True)
    context_file = phase_root / "context.md"
    context_file.write_text("context payload", encoding="utf-8")

    primary = _FakeBackend("openai-compat:test-model", [("final answer", {"input_tokens": 10, "output_tokens": 3})])
    fallback = _FakeBackend("openai-compat:fallback", [("fallback answer", {"input_tokens": 10, "output_tokens": 3})])

    monkeypatch.setattr(
        "dqg.agents.agent.create_backend", lambda model, api_key: primary if model == "test-model" else fallback
    )

    agent = Agent(
        name="demo-agent",
        role="worker",
        system_prompt="system prompt",
        model=LLMConfig(primary="test-model", fallback="fallback", max_tokens=128),
        output_dir=output_dir,
    )

    first = agent.run("hello", [context_file])
    second = agent.run("hello", [context_file])

    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT query_text, result_type, result_json FROM query_cache WHERE result_type = ?",
            ("agent_result",),
        ).fetchone()

    assert first.content == "final answer"
    assert first.cache_hit is False
    assert first.cached is False
    assert second.content == "final answer"
    assert second.cache_hit is True
    assert second.cached is True
    assert primary.calls == 1
    assert fallback.calls == 0
    assert row is not None
    assert row["result_type"] == "agent_result"
    cached_payload = json.loads(row["result_json"])
    assert cached_payload["content"] == "final answer"


def test_agent_run_does_not_cache_tool_call_turns(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    primary = _FakeBackend(
        "openai-compat:test-model",
        [
            (
                '<tool_call name="noop">{"x": 1}</tool_call>',
                {"input_tokens": 12, "output_tokens": 4},
            ),
            ("final after tool", {"input_tokens": 8, "output_tokens": 2}),
        ],
    )

    monkeypatch.setattr("dqg.agents.agent.create_backend", lambda model, api_key: primary)

    def noop(x: int) -> str:
        return f"noop:{x}"

    agent = Agent(
        name="demo-agent",
        role="worker",
        system_prompt="system prompt",
        model=LLMConfig(primary="test-model", fallback=None, max_tokens=128),
        tools=[noop],
        output_dir=output_dir,
    )

    result = agent.run("hello")

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM query_cache WHERE result_type = ?",
            ("agent_result",),
        ).fetchone()[0]

    assert result.content.endswith("final after tool")
    assert result.cache_hit is False
    assert result.cached is False
    assert primary.calls == 2
    assert rows == 0
