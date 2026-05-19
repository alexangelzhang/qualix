"""Tests for report structure contract check."""

from dqg.runtime.phase_contract import check_report_structure


def test_check_report_structure_all_present():
    report = """# Phase A Report

## 需求清单

REQ-001: 用户登录

## SE 关键语义清单

SE-001: 并发登录互斥

## 业务规则

BR-001: 密码复杂度

## Gap 分析

GAP-001: 未定义超时策略

## 评审结论

通过
"""
    result = check_report_structure(report, "Q01")
    assert result["passed"] is True
    assert len(result["missing"]) == 0


def test_check_report_structure_missing_section():
    report = """# Phase A Report

## 需求清单

REQ-001: 用户登录

## 业务规则

BR-001: 密码复杂度
"""
    result = check_report_structure(report, "Q01")
    assert result["passed"] is False
    assert len(result["missing"]) >= 1


def test_check_report_structure_alias_match():
    report = """# Phase A Report

## REQ/BR 需求清单

content

## SE List

content

## BR 业务规则

content

## GAP 缺口清单

content

## 结论

通过
"""
    result = check_report_structure(report, "Q01")
    assert result["passed"] is True


def test_check_report_structure_unknown_phase():
    result = check_report_structure("# Report", "Z")
    assert result["passed"] is True
    assert result["missing"] == []


def test_check_report_structure_phase_b():
    report = """# Phase B Report

## 测试用例清单

TC-001

## Coverage Matrix

| SE | Test |
"""
    result = check_report_structure(report, "Q05")
    assert result["passed"] is True
