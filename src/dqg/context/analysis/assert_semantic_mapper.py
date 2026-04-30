"""弱断言与业务语义映射：将测试断言与 Phase A SE / Phase B EUT 关联.

通过测试方法名、断言内容、被测方法名等信号，自动匹配对应的语义期望。
"""

from __future__ import annotations

import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)


def map_asserts_to_semantics(
    test_analysis: list[dict[str, Any]],
    se_list: list[dict[str, Any]] | None = None,
    eut_list: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """将测试方法的断言分析结果与 SE/EUT 关联.

    Args:
        test_analysis: analyze_assert_strength() 的结果列表
        se_list: Phase A structured JSON 中的 semantic_expectations
        eut_list: Phase B structured JSON 中的 eut_matrix (如有)

    Returns:
        增强后的分析结果，每个方法增加 semantic_mapping 字段
    """
    se_index = _build_se_index(se_list or [])
    eut_index = _build_eut_index(eut_list or [])

    for method_result in test_analysis:
        method_name = method_result.get("method_name", "")
        evidence = method_result.get("evidence", [])
        helper_calls = method_result.get("helper_calls", [])

        # 收集匹配信号
        signals = _extract_match_signals(method_name, evidence, helper_calls)

        # 匹配 SE
        matched_se = _match_semantics(signals, se_index)
        # 匹配 EUT
        matched_eut = _match_semantics(signals, eut_index)

        method_result["semantic_mapping"] = {
            "matched_se": matched_se,
            "matched_eut": matched_eut,
            "coverage_gap": not matched_se and not matched_eut,
        }

        # 如果有弱断言且关联了 SE，提升风险等级描述
        if method_result.get("signals") and matched_se:
            se_ids = [m["id"] for m in matched_se]
            for sig in method_result["signals"]:
                sig["related_se"] = se_ids

    return test_analysis


def load_se_from_phase_a(
    output_dir: str | Path,
    project_id: str,
) -> list[dict[str, Any]]:
    """从 Phase A 结构化产物加载 SE 列表."""
    phase_a_json = Path(output_dir) / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]
    if not phase_a_json.exists():
        return []
    data = load_json(phase_a_json)
    if not data:
        return []
    return data.get("semantic_expectations", [])


def load_eut_from_phase_b(
    output_dir: str | Path,
    project_id: str,
) -> list[dict[str, Any]]:
    """从 Phase B 结构化产物加载 EUT 列表."""
    phase_b_json = Path(output_dir) / project_id / PHASE_DIR_MAP["Q05"] / STRUCTURED_JSON_MAP["Q05"]
    if not phase_b_json.exists():
        return []
    data = load_json(phase_b_json)
    if not data:
        return []
    return data.get("eut_matrix", data.get("test_cases", []))


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------

# 从方法名/断言内容中提取的关键词 → 业务概念映射
_KEYWORD_CONCEPT_MAP: Final = MappingProxyType(
    {
        # 状态机
        "status": ["状态", "status", "迁移"],
        "state": ["状态", "state", "迁移"],
        "transition": ["状态", "迁移", "转换"],
        # 并发/幂等
        "concurrent": ["并发", "concurrent"],
        "idempotent": ["幂等", "idempotent"],
        "lock": ["锁", "并发", "lock"],
        "duplicate": ["幂等", "重复", "duplicate"],
        # 金额
        "amount": ["金额", "amount", "费用"],
        "price": ["金额", "price", "单价"],
        "total": ["总额", "total", "合计"],
        # 校验
        "valid": ["校验", "valid", "验证"],
        "check": ["校验", "check", "检查"],
        # 提交
        "submit": ["提交", "submit"],
        "save": ["保存", "save", "草稿"],
        "create": ["创建", "create", "发起"],
        "delete": ["删除", "delete"],
        # 回调
        "callback": ["回调", "callback"],
        "notify": ["通知", "notify", "消息"],
        # 转译
        "translat": ["转译", "translat", "映射"],
        # 导入
        "import": ["导入", "import"],
        # 异常
        "exception": ["异常", "exception", "错误"],
        "error": ["异常", "error", "错误"],
        "throw": ["异常", "throw", "抛出"],
        "reject": ["驳回", "reject"],
        # PDF
        "pdf": ["PDF", "pdf", "定损单"],
    }
)


def _extract_match_signals(
    method_name: str,
    evidence: list[str],
    helper_calls: list[str],
) -> set[str]:
    """从方法名、断言证据、helper 调用中提取匹配信号（业务概念关键词）."""
    signals: set[str] = set()
    all_text = " ".join(
        [
            _camel_to_words(method_name),
            " ".join(evidence),
            " ".join(_camel_to_words(h) for h in helper_calls),
        ]
    ).lower()

    for keyword, concepts in _KEYWORD_CONCEPT_MAP.items():
        if keyword.lower() in all_text:
            signals.update(concepts)

    return signals


def _build_se_index(se_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构建 SE 索引：每个 SE 提取关键词集合."""
    indexed: list[dict[str, Any]] = []
    for se in se_list:
        se_id = se.get("se_id", se.get("id", ""))
        desc = se.get("description", "")
        keywords = _extract_keywords_from_description(desc)
        indexed.append({"id": se_id, "description": desc, "keywords": keywords})
    return indexed


def _build_eut_index(eut_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构建 EUT 索引."""
    indexed: list[dict[str, Any]] = []
    for eut in eut_list:
        eut_id = eut.get("eut_id", eut.get("id", ""))
        desc = eut.get("description", eut.get("scenario", ""))
        keywords = _extract_keywords_from_description(desc)
        indexed.append({"id": eut_id, "description": desc, "keywords": keywords})
    return indexed


def _extract_keywords_from_description(desc: str) -> set[str]:
    """从 SE/EUT 描述中提取关键词."""
    keywords: set[str] = set()
    desc_lower = desc.lower()
    for _keyword, concepts in _KEYWORD_CONCEPT_MAP.items():
        for concept in concepts:
            if concept.lower() in desc_lower or concept in desc:
                keywords.update(concepts)
                break
    # 直接提取中文词
    chinese_words = re.findall(r"[\u4e00-\u9fff]{2,}", desc)
    keywords.update(chinese_words)
    return keywords


def _match_semantics(
    signals: set[str],
    index: list[dict[str, Any]],
    min_overlap: int = 2,
) -> list[dict[str, Any]]:
    """信号与 SE/EUT 索引匹配."""
    matches: list[dict[str, Any]] = []
    for entry in index:
        overlap = signals & entry["keywords"]
        if len(overlap) >= min_overlap:
            matches.append(
                {
                    "id": entry["id"],
                    "description": entry["description"][:80],
                    "matched_keywords": sorted(overlap)[:5],
                    "confidence": "high" if len(overlap) >= 3 else "medium",
                }
            )
    # 按匹配关键词数量降序
    matches.sort(key=lambda m: len(m["matched_keywords"]), reverse=True)
    return matches[:3]  # 最多返回 3 个匹配


_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def _camel_to_words(name: str) -> str:
    """camelCase/PascalCase → 空格分隔的小写词."""
    parts = _CAMEL_RE.findall(name)
    return " ".join(p.lower() for p in parts)
