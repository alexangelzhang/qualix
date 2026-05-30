"""Bug Case Lesson 自动推断：从结构化字段推断缺失的 lesson.

对 lesson 为空的 case，基于 title/tags/error_type/root_cause/source 字段
自动推断失败模式标签，提升 Skill Factory 的学习信号覆盖率。

不修改原始 case.json 文件——推断结果存入 SQLite 的 inferred_lessons 表，
供 Skill Factory 查询时合并使用。
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Final

from qualix.log import get_logger
from qualix.tracking.bug_cases import load_cases

log = get_logger(__name__)


# tag → lesson 映射（从 bitable 的 category2 标签推断）
_TAG_LESSON_MAP: Final = MappingProxyType(
    {
        "函数未覆盖": "新增/修改的函数缺少对应单测，需要补充单测覆盖",
        "函数正常分支未覆盖": "函数的正常业务分支缺少单测覆盖，需要补充 Happy Path 测试",
        "函数异常分支未覆盖": "函数的异常分支缺少单测覆盖，需要补充 Exception Path 测试",
        "有单测未运行": "单测存在但未被 CI 执行，检查测试配置和运行范围",
        "需求理解未对齐": "开发对需求的理解与产品意图不一致，需要在 Phase A 阶段加强需求确认",
        "产品需求不明确": "PRD 描述模糊导致实现偏差，应在 Phase A 标记为 GAP/OPEN",
        "需求遗漏": "PRD 遗漏了关键需求点，Phase A 的完备性检查未覆盖",
        "性能问题": "代码存在性能瓶颈，Phase D 评审应包含性能维度检查",
    }
)

# title 模式 → lesson 映射（从 AUTO 生成的 schema error 推断）
_TITLE_PATTERNS: Final[list[tuple[str, str]]] = [
    (r"validation errors? for Phase[A-Z]", "结构化输出不符合 schema 约束，检查字段类型和必填项"),
    (r"mapped_to_req_br", "SE 的 mapped_to_req_br 字段格式错误，应为字符串而非列表"),
    (r"bool_type.*input_value=\[", "布尔字段传入了列表值，schema 类型定义与实际输出不匹配"),
    (r"pydantic", "Pydantic 校验失败，结构化输出的字段类型与 schema 定义不一致"),
    (r"string_type", "字符串字段传入了非字符串值"),
    (r"missing", "必填字段缺失"),
    (
        r"failure_modes?\[\d+\]",
        "Failure Mode 矩阵条目缺字段：按 schema 补全 business_path、failure_scenario、has_exception_handling、status",
    ),
    (r"issues\.\d+\.issue_id", "issues 条目 issue_id 或 severity 不符合 schema，禁止自造枚举词"),
    (r"findings?\[\d+\]|finding", "findings 条目缺 id/severity 等必填字段，与 phase_c 契约对齐"),
    (r"eut_id|phantom|不存在.*eut", "EUT 编号须来自 Q05 phase_b_structured.json，禁止按测试代码臆造编号"),
    (r"then|弱断言|vague", "EUT then 须写具体断言与期望值，禁止「验证成功」等模糊描述"),
]

# error_type + root_cause 组合 → 通用 lesson
_COMBO_LESSON_MAP: Final = MappingProxyType(
    {
        ("WRONG", "SCHEMA"): "结构化输出格式错误，需要修正 schema 定义或输出逻辑",
        ("FN", "SCHEMA"): "结构化输出遗漏了必要字段，schema 校验未能拦截",
        ("FN", "SKILL_RULE"): "Skill 规则未覆盖此失败场景，需要补充检查项",
        ("FN", "KNOWLEDGE"): "缺少领域知识导致遗漏，需要补充知识库",
        ("FN", "CONTEXT"): "上下文加载不完整导致遗漏，需要改进输入解析",
        ("FP", "SKILL_RULE"): "Skill 规则过于激进导致误报，需要增加排除条件",
    }
)


def infer_lesson(case: dict[str, Any]) -> str | None:
    """为单个 case 推断 lesson.

    Returns:
        推断的 lesson 字符串，或 None（无法推断时）
    """
    # 已有 lesson 的不推断
    if case.get("lesson", "").strip():
        return None

    title = case.get("title", "")
    tags = case.get("tags", [])
    error_type = case.get("error_type", "")
    root_cause = case.get("root_cause", "")
    source = case.get("source", {})

    # 优先级 1：从 source.category2 推断（bitable 导入的 case 有这个字段）
    if isinstance(source, dict):
        category2 = source.get("category2", "")
        if category2 and category2 in _TAG_LESSON_MAP:
            return _TAG_LESSON_MAP[category2]

    # 优先级 2：从 tags 推断
    for tag in tags:
        if tag in _TAG_LESSON_MAP:
            return _TAG_LESSON_MAP[tag]

    # 优先级 3：从 title 模式匹配推断
    for pattern, lesson in _TITLE_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return lesson

    # 优先级 4：从 error_type + root_cause 组合推断
    combo = (error_type, root_cause)
    if combo in _COMBO_LESSON_MAP:
        return _COMBO_LESSON_MAP[combo]

    return None


def infer_all_lessons() -> dict[str, Any]:
    """为所有缺失 lesson 的 case 推断 lesson.

    Returns:
        {
            "total_cases": N,
            "already_has_lesson": M,
            "inferred": K,
            "still_missing": L,
            "inferred_lessons": [{"case_id": "...", "lesson": "...", "source": "..."}],
            "coverage_before": float,
            "coverage_after": float,
        }
    """
    cases = load_cases()
    total = len(cases)
    already_has = sum(1 for c in cases if c.get("lesson", "").strip())

    inferred_lessons: list[dict[str, str]] = []
    for case in cases:
        if case.get("lesson", "").strip():
            continue
        lesson = infer_lesson_with_fallback(case)
        inferred_lessons.append(
            {
                "case_id": case.get("case_id", ""),
                "phase": case.get("phase", ""),
                "inferred_lesson": lesson,
            }
        )

    inferred_count = len(inferred_lessons)
    still_missing = total - already_has - inferred_count

    return {
        "total_cases": total,
        "already_has_lesson": already_has,
        "inferred": inferred_count,
        "still_missing": still_missing,
        "inferred_lessons": inferred_lessons,
        "coverage_before": already_has / total if total > 0 else 0,
        "coverage_after": (already_has + inferred_count) / total if total > 0 else 0,
    }


def infer_lesson_with_fallback(case: dict[str, Any]) -> str:
    """推断 lesson；无法匹配模式时用 root_cause 兜底（T4 批量补齐用）."""
    from qualix.tracking.case_category import fallback_lesson_for_root_cause

    base = infer_lesson(case)
    if base:
        return base
    return fallback_lesson_for_root_cause(str(case.get("root_cause", "")))


def get_case_with_inferred_lesson(case: dict[str, Any]) -> dict[str, Any]:
    """返回 case 的副本，如果 lesson 为空则填入推断值.

    不修改原始 case，返回新 dict。
    """
    if case.get("lesson", "").strip():
        return case

    from qualix.tracking.case_category import fallback_lesson_for_root_cause

    direct = infer_lesson(case)
    lesson = direct if direct else fallback_lesson_for_root_cause(str(case.get("root_cause", "")))
    enriched = dict(case)
    enriched["lesson"] = lesson
    enriched["_lesson_inferred"] = not bool(direct)
    return enriched
