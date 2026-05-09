"""失败案例五类细分（与 2026-05-09 健康报告 T4 对齐）.

用于 case.json 的 case_category 字段，便于统计与治理；与 lesson 互补。
"""

from __future__ import annotations

import re
from typing import Any, Final

# 五类枚举（全大写，写入 case.json）
CASE_CATEGORIES: Final[tuple[str, ...]] = (
    "STRUCTURED_SCHEMA",  # 缺字段、矩阵不全、Pydantic 校验失败
    "ENUM_VOCABULARY",  # severity 等枚举自造词
    "CROSS_PHASE_IDS",  # phantom EUT、SE/REQ 引用漂移
    "ASSERTION_QUALITY",  # then 弱断言、断言不指向业务后果
    "DOC_SKILL_DRIFT",  # skill 示例与 schema 冲突、prompt 未列必填
)

_FALLBACK_LESSON_BY_RC: Final[dict[str, str]] = {
    "SCHEMA": "对齐 Pydantic schema 与结构化 JSON：逐字段核对必填项与枚举，禁止自造字段名或省略键。",
    "SKILL_RULE": "对照对应 Phase 的 SKILL.md 与 references：补齐规则要求的表格/矩阵/证据后再产出。",
    "KNOWLEDGE": "补充 profiles/references 中的领域基线，避免凭常识编造接口或异常语义。",
    "CONTEXT": "检查上游产物与 _upstream_context 是否完整加载；缺输入时显式标注而非猜测。",
}

_DEFAULT_FALLBACK_LESSON: Final[str] = (
    "对照 Phase skill、schema 与历史反例复盘本案例；修复后更新 case 状态并补充可复现片段。"
)


def infer_case_category(case: dict[str, Any]) -> str:
    """从 title/phase/tags/source 推断 case_category（五选一）."""
    title = (case.get("title") or "").lower()
    phase = str(case.get("phase", "")).upper()
    tags = [str(t).lower() for t in case.get("tags", [])]
    blob = " ".join([title, phase, " ".join(tags)])
    src = case.get("source", {})
    val_err = ""
    if isinstance(src, dict):
        val_err = str(src.get("validation_error", "") or "").lower()

    # 1) 结构化 / schema / 缺字段（优先）
    if re.search(
        r"validation|pydantic|string_type|bool_type|missing|required|schema|structured|issue_id|failure_mode|finding",
        title + " " + val_err,
        re.I,
    ):
        return "STRUCTURED_SCHEMA"

    # 2) 跨 Phase / phantom EUT
    if any(
        k in title or k in val_err for k in ("phantom", "不存在于 q05", "eut-", "audit_items", "bound_se", "跨phase")
    ):
        return "CROSS_PHASE_IDS"
    if phase in ("Q06", "C") and ("eut" in title or "audit" in title):
        return "CROSS_PHASE_IDS"
    if phase in ("Q05", "B") and "bound_se" in title:
        return "CROSS_PHASE_IDS"

    # 3) 弱断言 / then
    if any(
        k in title + " " + blob for k in ("then", "弱断言", "assertnotnull", "weak_assert", "模糊描述", "vague_then")
    ):
        return "ASSERTION_QUALITY"

    # 4) 枚举词汇
    if any(k in title + " " + blob for k in ("severity", "important", "suggestion", "nit", "枚举错乱")):
        return "ENUM_VOCABULARY"

    # 5) 文档 / 示例 / skill 与约束漂移
    if any(k in title + " " + blob for k in ("示例", "skill", "prompt", "文档冲突", "铁律", "skill 示例")):
        return "DOC_SKILL_DRIFT"

    rc = case.get("root_cause", "")
    if rc == "SCHEMA":
        return "STRUCTURED_SCHEMA"
    if rc == "SKILL_RULE":
        return "DOC_SKILL_DRIFT"
    if rc == "CONTEXT":
        return "DOC_SKILL_DRIFT"

    return "STRUCTURED_SCHEMA"


def fallback_lesson_for_root_cause(root_cause: str) -> str:
    """lesson 无法从模式推断时的兜底文案."""
    return _FALLBACK_LESSON_BY_RC.get(root_cause, _DEFAULT_FALLBACK_LESSON)
