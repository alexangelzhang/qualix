"""Deterministic semantic-quality checks for Q01 structured output."""

from __future__ import annotations

import re
from typing import Any

_BR_DETAIL_KEYWORDS = re.compile(
    r"字段|枚举|校验|提示|格式|长度|范围|默认值|必填|可选|状态|金额|数量|时间|角色|权限|错误码"
    r"|field|enum|validation|format|length|range|default|required|optional|status|errorCode",
    re.IGNORECASE,
)

_VAGUE_BR_PATTERNS = re.compile(
    r"^(支持|处理|展示|校验|管理|维护|实现|提供|完成|优化).{0,18}$"
    r"|相关信息|相关逻辑|相关功能|等信息|等等|按需|合理处理|正常处理|自动处理|正确处理",
    re.IGNORECASE,
)

_WEAK_VERIFICATION_PATTERNS = re.compile(
    r"^(验证|校验|检查|确保|确认).{0,10}(正确|成功|通过|生效)$"
    r"|需要.*控制|需要.*处理|保证.*一致|防止重复|正常返回|符合预期",
    re.IGNORECASE,
)

_VERIFICATION_ANCHORS = (
    "断言",
    "assert",
    "expect(",
    "SELECT",
    "HTTP",
    "errorCode",
    "status",
    "Mock",
    "verify(",
    "CountDownLatch",
    "pytest",
    "go test",
)

_SOURCE_PATTERN = re.compile(r"(?:plain_text\.txt|blocks\.raw\.json|comments\.md):\d+")


def check_q01_semantic_quality(structured_data: dict[str, Any]) -> list[str]:
    """Return Q01 quality errors and warnings derived from structured JSON."""
    if not structured_data:
        return []

    errors: list[str] = []
    requirements = structured_data.get("requirements", [])
    known_req_ids = {item.get("req_id", "") for item in requirements if isinstance(item, dict)}

    errors.extend(_check_br_quality(requirements))
    errors.extend(_check_se_quality(structured_data.get("semantic_expectations", []), known_req_ids))
    errors.extend(_check_gap_quality(structured_data.get("gaps", []), known_req_ids))
    errors.extend(_check_open_quality(structured_data.get("open_items", []), known_req_ids))
    return errors


def _check_br_quality(requirements: list[Any]) -> list[str]:
    errors: list[str] = []
    for req in requirements:
        if not isinstance(req, dict):
            continue
        req_id = str(req.get("req_id", ""))
        if not req_id.startswith("BR-"):
            continue
        text = _join_fields(req, "description", "trigger", "behavior_change", "acceptance_criteria")
        if len(text) < 24 or _VAGUE_BR_PATTERNS.search(text) or not _BR_DETAIL_KEYWORDS.search(text):
            errors.append(
                f"WARNING: Q01 {req_id} br_too_vague — BR 描述缺少字段/枚举/校验/状态/错误码等可验收细节，"
                "容易导致 Q05a 只能生成空泛 EUT。"
            )
        source = str(req.get("source", ""))
        if source and not _SOURCE_PATTERN.search(source):
            errors.append(f"WARNING: Q01 {req_id} source_format — source 应指向 PRD 原文行号，如 plain_text.txt:12。")
    return errors


def _check_se_quality(items: list[Any], known_req_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for se in items:
        if not isinstance(se, dict):
            continue
        se_id = str(se.get("se_id", "SE-?"))
        verification = str(se.get("verification", "")).strip()
        if _is_weak_verification(verification):
            errors.append(
                f"FAIL: Q01 {se_id} verification_too_vague — verification 必须能直接转成测试步骤和断言，"
                "不能只写验证正确/防止重复/保证一致。"
            )
        source = str(se.get("source", "")).strip()
        if not _SOURCE_PATTERN.search(source):
            errors.append(f"FAIL: Q01 {se_id} source_required — SE 必须引用 PRD 原文行号，如 plain_text.txt:12。")
        bound_reqs = se.get("bound_reqs", []) or []
        missing = [ref for ref in bound_reqs if ref not in known_req_ids]
        if missing:
            errors.append(f"FAIL: Q01 {se_id} bound_reqs_invalid — 引用了不存在的 REQ/BR: {', '.join(missing)}。")
    return errors


def _check_gap_quality(items: list[Any], known_req_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for gap in items:
        if not isinstance(gap, dict):
            continue
        gap_id = str(gap.get("gap_id", "GAP-?"))
        risk = str(gap.get("risk_level", gap.get("severity", ""))).strip()
        if risk not in {"P0", "P1", "P2"}:
            errors.append(f"FAIL: Q01 {gap_id} risk_level_required — GAP risk_level 必须是 P0/P1/P2。")
        if not str(gap.get("required_clarification", "")).strip():
            errors.append(f"FAIL: Q01 {gap_id} required_clarification_empty — GAP 必须说明需要补充什么口径。")
        errors.extend(_check_related_ids(gap_id, gap.get("related_ids", []), known_req_ids))
    return errors


def _check_open_quality(items: list[Any], known_req_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        open_id = str(item.get("open_id", "OPEN-?"))
        if not str(item.get("decision_owner", "")).strip():
            errors.append(f"FAIL: Q01 {open_id} decision_owner_required — OPEN 必须填写决策方。")
        errors.extend(_check_related_ids(open_id, item.get("related_ids", []), known_req_ids))
    return errors


def _check_related_ids(item_id: str, related_ids: Any, known_req_ids: set[str]) -> list[str]:
    if not isinstance(related_ids, list) or not related_ids:
        return [f"WARNING: Q01 {item_id} related_ids_empty — GAP/OPEN 应绑定具体 REQ/BR。"]
    missing = [str(ref) for ref in related_ids if str(ref) not in known_req_ids]
    if missing:
        return [f"FAIL: Q01 {item_id} related_ids_invalid — 引用了不存在的 REQ/BR: {', '.join(missing)}。"]
    return []


def _is_weak_verification(text: str) -> bool:
    if not text:
        return True
    if len(text) < 20:
        return True
    if _WEAK_VERIFICATION_PATTERNS.search(text):
        return True
    return not any(anchor in text for anchor in _VERIFICATION_ANCHORS)


def _join_fields(item: dict[str, Any], *fields: str) -> str:
    return " ".join(str(item.get(field, "") or "") for field in fields).strip()

