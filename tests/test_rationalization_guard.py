"""Tests for RationalizationGuard two-layer detection."""
import pytest
from unittest.mock import MagicMock
from dqg.quality.rationalization_guard import (
    RationalizationGuard, GuardResult, format_rejudge_warning,
)


def test_scan_keywords_no_match():
    guard = RationalizationGuard()
    matches = guard.scan_keywords("所有维度均已严格评审，发现 3 个问题。")
    assert len(matches) == 0


def test_scan_keywords_match_basic():
    guard = RationalizationGuard()
    matches = guard.scan_keywords("虽然缺少边界测试，但整体可以接受。")
    assert len(matches) >= 1
    assert any("虽然" in m.matched_text for m in matches)


def test_scan_keywords_match_multiple():
    guard = RationalizationGuard()
    text = "基本清晰，覆盖率达标，影响不大。"
    matches = guard.scan_keywords(text)
    assert len(matches) >= 2


def test_check_passes_when_no_keywords():
    guard = RationalizationGuard()
    result = guard.check("严格评审结果：FAIL，发现 5 个严重问题。")
    assert result.passed is True
    assert result.action == "PASS"


def test_check_blocks_when_confirmed(monkeypatch):
    guard = RationalizationGuard()
    monkeypatch.setattr(guard, "confirm_with_llm", lambda matches, text: [
        MagicMock(verdict="CONFIRMED", text="虽然缺少边界测试，但整体可以接受")
    ])
    result = guard.check("虽然缺少边界测试，但整体可以接受。")
    assert result.passed is False
    assert result.action == "BLOCK_AND_REJUDGE"


def test_check_passes_on_false_positive(monkeypatch):
    guard = RationalizationGuard()
    monkeypatch.setattr(guard, "confirm_with_llm", lambda matches, text: [
        MagicMock(verdict="FALSE_POSITIVE", text="")
    ])
    result = guard.check("虽然这个接口名称不太直观，但功能实现正确，可以接受。")
    assert result.passed is True
    assert result.action == "PASS"


def test_format_rejudge_warning():
    gr = GuardResult(
        passed=False,
        confirmed_rationalizations=["虽然缺少边界测试，但整体可以接受"],
        action="BLOCK_AND_REJUDGE",
    )
    warning = format_rejudge_warning(gr)
    assert "放水信号" in warning
    assert "虽然缺少边界测试" in warning
