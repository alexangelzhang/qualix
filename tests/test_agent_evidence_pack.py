from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.agents.agent import Agent
from dqg.agents.llm_backends import LLMConfig

if TYPE_CHECKING:
    from pathlib import Path


class _FakeBackend:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        return "done", {"input_tokens": 1, "output_tokens": 1}

    def name(self) -> str:
        return "fake-backend"


def test_agent_run_uses_excerpted_context_bundle(monkeypatch, tmp_path: Path) -> None:
    backend = _FakeBackend()
    monkeypatch.setattr("dqg.agents.agent.create_backend", lambda *args, **kwargs: backend)

    long_text = "权限校验失败\n" + ("尾部不应进入全文 prompt" * 800)
    context_file = tmp_path / "context.md"
    context_file.write_text(long_text, encoding="utf-8")

    agent = Agent(
        name="demo",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    result = agent.run("do it", context_files=[context_file])

    assert result.status == "success"
    assert backend.calls
    system_message, context_message, user_message = backend.calls[0]
    assert system_message["role"] == "system"
    assert context_message["role"] == "user"
    assert context_message["content"].startswith("## 文件: context.md")
    assert "权限校验失败" in context_message["content"]
    assert "...(截断)" in context_message["content"]
    assert len(context_message["content"]) < len(long_text)
    assert user_message["content"] == "do it"


def test_agent_run_caps_total_context_bundle_size(monkeypatch, tmp_path: Path) -> None:
    backend = _FakeBackend()
    monkeypatch.setattr("dqg.agents.agent.create_backend", lambda *args, **kwargs: backend)

    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    third = tmp_path / "third.md"
    fourth = tmp_path / "fourth.md"
    first.write_text("Q01" * 5000, encoding="utf-8")
    second.write_text("Q05" * 5000, encoding="utf-8")
    third.write_text("Q06" * 5000, encoding="utf-8")
    fourth.write_text("Q07" * 5000, encoding="utf-8")

    agent = Agent(
        name="demo",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    agent.run("do it", context_files=[first, second, third, fourth])

    _, context_message, _ = backend.calls[0]
    assert context_message["content"].count("## 文件:") <= 4
    assert len(context_message["content"]) <= 13_500
