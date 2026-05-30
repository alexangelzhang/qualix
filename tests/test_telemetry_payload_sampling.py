"""P0: telemetry payload sampling."""

from __future__ import annotations

from qualix.agents.agent import AgentResult, extract_llm_call


def test_maybe_sample_agent_payload_full_rate(monkeypatch) -> None:
    monkeypatch.setenv("QUALIX_TELEMETRY_PAYLOAD_SAMPLE_RATE", "1")
    monkeypatch.setattr("qualix.reporting.telemetry_payload.random.random", lambda: 0.0)

    from qualix.reporting.telemetry_payload import maybe_sample_agent_payload

    p, r = maybe_sample_agent_payload([{"role": "user", "content": "hello"}], "world")
    assert "hello" in p
    assert r == "world"


def test_maybe_sample_disabled(monkeypatch) -> None:
    monkeypatch.setenv("QUALIX_TELEMETRY_PAYLOAD_SAMPLE_RATE", "0")
    from qualix.reporting.telemetry_payload import maybe_sample_agent_payload

    p, r = maybe_sample_agent_payload([{"role": "user", "content": "hello"}], "world")
    assert p == "" and r == ""


def test_extract_llm_call_carries_excerpts() -> None:
    ar = AgentResult(
        agent_name="w",
        role="worker",
        status="success",
        telemetry_prompt_excerpt="p",
        telemetry_response_excerpt="r",
    )
    tel = extract_llm_call(ar)
    assert tel.get("prompt_excerpt") == "p"
    assert tel.get("response_excerpt") == "r"
