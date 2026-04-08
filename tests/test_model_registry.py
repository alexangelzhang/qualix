"""Tests for dqg.core.model_registry."""

from dqg.core.model_registry import estimate_tokens


def test_estimate_tokens_handles_mixed_text() -> None:
    text = "Phase A 需求结构化 REQ-001, 这是一个测试。"
    assert estimate_tokens(text) > 0


def test_estimate_tokens_scales_with_long_text() -> None:
    text = ("需求" * 2000) + (" alpha beta gamma " * 1000)
    tokens = estimate_tokens(text)
    assert tokens > 0
    assert tokens == estimate_tokens(text)
