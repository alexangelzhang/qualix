"""Root Cause 驱动的 Pipeline 参数自动调整.

在 finalize 时分析 bug case 的 root_cause 分布趋势，
自动调整 Evidence Pack token budget 和 Skill Factory 优先级。

调整逻辑：
- CONTEXT 类 root cause 占比 > 40% → 增加 Evidence Pack token budget
- SKILL_RULE 类 root cause 占比 > 40% → 标记 Skill Factory 高优先级
- SCHEMA 类 root cause 占比 > 30% → 标记 Schema 校验需要加强
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from dqg.log import get_logger
from dqg.tracking.bug_cases import load_cases_by_phase

log = get_logger(__name__)

# 默认阈值
_CONTEXT_THRESHOLD = 0.40
_SKILL_RULE_THRESHOLD = 0.40
_SCHEMA_THRESHOLD = 0.30

# Evidence Pack budget 调整幅度
_BUDGET_BOOST_FACTOR = 1.3  # 30% 增加


def analyze_root_cause_trend(phase_id: str) -> dict[str, Any]:
    """分析指定 Phase 的 root cause 分布，返回调整建议.

    Returns:
        {
            "phase": str,
            "total_cases": int,
            "distribution": {"CONTEXT": 0.45, "SKILL_RULE": 0.30, ...},
            "adjustments": [
                {"param": "evidence_pack_quote_limit", "action": "increase", "factor": 1.3, "reason": "..."},
                ...
            ],
        }
    """
    cases = load_cases_by_phase(phase_id, exclude_holdout=True)
    open_cases = [c for c in cases if c.get("status") == "open"]

    if len(open_cases) < 5:
        return {
            "phase": phase_id,
            "total_cases": len(open_cases),
            "distribution": {},
            "adjustments": [],
            "message": "Too few open cases for trend analysis",
        }

    rc_counts = Counter(c.get("root_cause", "UNKNOWN") for c in open_cases)
    total = len(open_cases)
    distribution = {rc: count / total for rc, count in rc_counts.items()}

    adjustments: list[dict[str, Any]] = []

    # CONTEXT 类占比高 → 增加 Evidence Pack token budget
    context_ratio = distribution.get("CONTEXT", 0)
    if context_ratio > _CONTEXT_THRESHOLD:
        adjustments.append({
            "param": "evidence_pack_quote_limit",
            "action": "increase",
            "factor": _BUDGET_BOOST_FACTOR,
            "reason": f"CONTEXT root cause 占比 {context_ratio:.0%} > {_CONTEXT_THRESHOLD:.0%}，"
                      f"增加 Evidence Pack 引用上限以减少上下文丢失",
        })
        adjustments.append({
            "param": "evidence_pack_total_quote_char_limit",
            "action": "increase",
            "factor": _BUDGET_BOOST_FACTOR,
            "reason": f"同步增加 Evidence Pack 总字符上限",
        })

    # SKILL_RULE 类占比高 → 触发 Skill Factory 高优先级
    skill_ratio = distribution.get("SKILL_RULE", 0)
    if skill_ratio > _SKILL_RULE_THRESHOLD:
        adjustments.append({
            "param": "skill_factory_priority",
            "action": "elevate",
            "reason": f"SKILL_RULE root cause 占比 {skill_ratio:.0%} > {_SKILL_RULE_THRESHOLD:.0%}，"
                      f"Skill 规则需要优先更新",
        })

    # SCHEMA 类占比高 → Schema 校验需要加强
    schema_ratio = distribution.get("SCHEMA", 0)
    if schema_ratio > _SCHEMA_THRESHOLD:
        adjustments.append({
            "param": "schema_validation",
            "action": "strengthen",
            "reason": f"SCHEMA root cause 占比 {schema_ratio:.0%} > {_SCHEMA_THRESHOLD:.0%}，"
                      f"结构化输出校验需要加强",
        })

    if adjustments:
        log.info(
            "Root cause auto-tune Phase %s: %d adjustments (CONTEXT=%.0f%% SKILL_RULE=%.0f%% SCHEMA=%.0f%%)",
            phase_id, len(adjustments),
            context_ratio * 100, skill_ratio * 100, schema_ratio * 100,
        )

    return {
        "phase": phase_id,
        "total_cases": total,
        "distribution": {rc: round(ratio, 2) for rc, ratio in distribution.items()},
        "adjustments": adjustments,
    }


def get_adjusted_evidence_limits(phase_id: str) -> dict[str, int]:
    """根据 root cause 趋势返回调整后的 Evidence Pack 参数.

    调用方用这些值替代 constants.py 中的默认值。
    """
    from dqg.constants import (
        EVIDENCE_PACK_MAX_QUOTES,
        EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT,
    )

    trend = analyze_root_cause_trend(phase_id)
    max_quotes = EVIDENCE_PACK_MAX_QUOTES
    total_char_limit = EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT

    for adj in trend.get("adjustments", []):
        if adj["param"] == "evidence_pack_quote_limit" and adj["action"] == "increase":
            factor = adj.get("factor", _BUDGET_BOOST_FACTOR)
            max_quotes = int(max_quotes * factor)
        if adj["param"] == "evidence_pack_total_quote_char_limit" and adj["action"] == "increase":
            factor = adj.get("factor", _BUDGET_BOOST_FACTOR)
            total_char_limit = int(total_char_limit * factor)

    return {
        "max_quotes": max_quotes,
        "total_quote_char_limit": total_char_limit,
        "adjustments_applied": len(trend.get("adjustments", [])),
    }
