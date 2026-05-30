"""案例相关性匹配 + Warm Start prompt 渲染."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Final

from qualix.tracking.bug_cases import load_cases_by_phase

# 同义词扩展表：复用 knowledge_network 的 pattern 关键词组
# 当 case 关键词命中某 group 中的任一词时，把该 group 所有词加入匹配集
_SYNONYM_GROUPS: Final = MappingProxyType(
    {
        "并发": ["并发", "幂等", "锁", "竞争", "冲突", "重复提交", "并发安全"],
        "权限": ["权限", "隔离", "越权", "鉴权", "角色"],
        "状态机": ["状态机", "状态流转", "状态迁移", "驳回", "循环", "非法跳转"],
        "金额": ["金额", "计算", "精度", "BigDecimal", "分", "精度丢失"],
        "超时": ["超时", "重试", "降级", "熔断", "补偿"],
        "通知": ["通知", "消息", "推送", "飞书", "提醒"],
        "导出": ["导出", "异步", "大数据量"],
        "缓存": ["缓存", "失效", "一致性"],
    }
)


def _extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词（中文分词简化版：按标点和空格切分）."""
    stopwords = {
        "的",
        "了",
        "在",
        "是",
        "和",
        "与",
        "或",
        "等",
        "为",
        "对",
        "从",
        "到",
        "中",
        "上",
        "下",
        "不",
        "有",
        "无",
    }
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_][A-Za-z0-9_]+", text)
    return {t for t in tokens if t not in stopwords and len(t) >= 2}


def _expand_synonyms(keywords: set[str]) -> set[str]:
    """基于同义词组扩展关键词集合，提升语义相似但关键词不同的案例召回率."""
    expanded = set(keywords)
    for _group_name, group_words in _SYNONYM_GROUPS.items():
        if any(kw in keywords for kw in group_words):
            expanded.update(group_words)
    return expanded


def _compute_relevance(case: dict[str, Any], input_keywords: set[str]) -> float:
    """计算案例与输入的相关性分数 (0-1).

    使用同义词扩展提升语义相似但关键词不同的案例召回率。
    """
    actual = case.get("actual", {})
    expected = case.get("expected", {})
    source = case.get("source", {})
    case_text_parts = [
        case.get("title", ""),
        case.get("lesson", ""),
        " ".join(case.get("tags", [])),
        case.get("root_cause", ""),
        case.get("fix_target", ""),
        actual.get("content", "") if isinstance(actual, dict) else str(actual),
        expected.get("content", "") if isinstance(expected, dict) else str(expected),
        source.get("validation_error", "") if isinstance(source, dict) else "",
    ]

    case_keywords = _extract_keywords(" ".join(case_text_parts))
    if not case_keywords or not input_keywords:
        return 0.0

    # 二级匹配：同义词扩展后再计算重叠
    expanded_case = _expand_synonyms(case_keywords)
    expanded_input = _expand_synonyms(input_keywords)
    overlap = expanded_case & expanded_input
    return len(overlap) / max(len(expanded_case), 1)


def select_relevant_cases(
    phase: str,
    input_text: str,
    max_cases: int = 8,
    min_relevance: float = 0.05,
) -> list[dict[str, Any]]:
    """选择与当前输入最相关的 bug 案例."""
    cases = [c for c in load_cases_by_phase(phase, exclude_holdout=True) if c.get("status") == "open"]
    if not cases:
        return []

    input_keywords = _extract_keywords(input_text)
    if not input_keywords:
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        cases.sort(key=lambda c: severity_order.get(c.get("severity", "low"), 9))
        return cases[:max_cases]

    scored: list[tuple[float, dict[str, Any]]] = []
    for case in cases:
        score = _compute_relevance(case, input_keywords)
        severity_bonus = {"critical": 0.3, "high": 0.15, "medium": 0.05, "low": 0.0}
        score += severity_bonus.get(case.get("severity", "low"), 0)
        scored.append((score, case))

    scored.sort(key=lambda x: (-x[0], x[1].get("case_id", "")))

    result = []
    for score, case in scored:
        if len(result) >= max_cases:
            break
        if score >= min_relevance or case.get("severity") in ("critical", "high"):
            result.append(case)

    return result


def render_relevant_cases_for_prompt(
    phase: str,
    input_text: str,
    max_cases: int = 8,
) -> str:
    """渲染与当前输入相关的 bug 案例为 prompt markdown."""
    cases = select_relevant_cases(phase, input_text, max_cases)
    if not cases:
        return ""

    lines = [
        "## BUG_CASES — 已知判错案例（务必避免重犯）",
        "",
        f"以下是 Phase {phase} 与当前输入最相关的历史判错案例。",
        "",
    ]

    for i, c in enumerate(cases, 1):
        error_label = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(
            c.get("error_type", ""), c.get("error_type", "")
        )
        lines.append(f"### 反例 {i}: {c.get('title', '')[:80]} [{error_label}]")
        lines.append("")

        lesson = c.get("lesson", "")
        if lesson:
            lines.append(f"**教训**: {lesson}")
            lines.append("")

    return "\n".join(lines)
