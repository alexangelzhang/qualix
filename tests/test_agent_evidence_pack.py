from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.agents.agent import Agent
from qualix.agents.llm_backends import LLMConfig

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
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *args, **kwargs: backend)

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
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *args, **kwargs: backend)

    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    third = tmp_path / "third.md"
    fourth = tmp_path / "fourth.md"
    first.write_text("Q01" * 5000, encoding="utf-8")
    second.write_text("Q05a" * 5000, encoding="utf-8")
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


def test_agent_run_separates_dynamic_context(monkeypatch, tmp_path: Path) -> None:
    """dynamic_context_files should produce a separate user message WITHOUT cache_control."""
    backend = _FakeBackend()
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *args, **kwargs: backend)

    static_file = tmp_path / "evidence.md"
    static_file.write_text("REQ-001 需求内容", encoding="utf-8")

    dynamic_file = tmp_path / "handoff.md"
    dynamic_file.write_text("Judge 反馈：缺少异常处理分析", encoding="utf-8")

    agent = Agent(
        name="demo",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    agent.run("修正报告", context_files=[static_file], dynamic_context_files=[dynamic_file])

    assert len(backend.calls) == 1
    msgs = backend.calls[0]
    assert len(msgs) == 4  # system + static + dynamic + user
    assert msgs[0]["role"] == "system"
    assert msgs[0].get("cache_control") is True
    assert msgs[1]["role"] == "user"
    assert msgs[1].get("cache_control") is True
    assert "REQ-001" in msgs[1]["content"]
    assert msgs[2]["role"] == "user"
    assert msgs[2].get("cache_control") is None or msgs[2].get("cache_control") is False
    assert "Judge 反馈" in msgs[2]["content"]
    assert msgs[3]["content"] == "修正报告"


def test_agent_run_no_dynamic_context_unchanged(monkeypatch, tmp_path: Path) -> None:
    """When dynamic_context_files=None (default), behavior is identical to before: 3 messages."""
    backend = _FakeBackend()
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *args, **kwargs: backend)

    static_file = tmp_path / "evidence.md"
    static_file.write_text("REQ-002 静态内容", encoding="utf-8")

    agent = Agent(
        name="demo",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    agent.run("执行任务", context_files=[static_file])

    assert len(backend.calls) == 1
    msgs = backend.calls[0]
    assert len(msgs) == 3  # system + static + user
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "REQ-002" in msgs[1]["content"]
    assert msgs[2]["content"] == "执行任务"
