"""OCR 结果语义分析 + 质量评估。

从 OCR 提取的文字推断图片语义，评估是否需要 VLM 兜底。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dqg.media.ocr.engine import OcrResult

UI_KEYWORDS = {"提交", "保存", "取消", "确认", "搜索", "筛选", "新增", "编辑", "删除", "查看", "返回", "下一步"}
FLOW_KEYWORDS = {"开始", "结束", "判断", "是", "否", "流程", "审批", "通过", "驳回", "发起"}
STATE_KEYWORDS = {"待", "已", "中", "成功", "失败", "完成", "进行", "审核", "发放", "提交"}
TABLE_KEYWORDS = {"序号", "名称", "类型", "状态", "时间", "操作", "备注", "金额", "数量"}


@dataclass
class OcrAnalysis:
    """OCR 语义分析结果。"""

    analysis: str
    summary: str
    quality_score: float
    needs_vlm: bool
    image_type: str
    entities: list[str]
    coverage_ratio: float


def analyze_ocr_result(
    ocr_result: OcrResult,
    asset: dict[str, Any],
    prd_context: str = "",
    quality_threshold: float = 0.6,
) -> OcrAnalysis:
    """从 OCR 文字推断图片语义。

    Args:
        ocr_result: OCR 提取结果
        asset: 图片元数据（kind/section_path/name）
        prd_context: PRD 文本片段，用于交叉匹配
        quality_threshold: 质量阈值，低于此值标记 needs_vlm

    Returns:
        OcrAnalysis 包含分析文本、摘要、质量评分等
    """
    if not ocr_result.text.strip():
        return OcrAnalysis(
            analysis="OCR 未提取到文字内容。",
            summary="无文字内容",
            quality_score=0.0,
            needs_vlm=True,
            image_type="unknown",
            entities=[],
            coverage_ratio=0.0,
        )

    image_type = _classify_image_type(ocr_result, asset)
    entities = _extract_entities(ocr_result)
    coverage_ratio = _compute_coverage(ocr_result, prd_context) if prd_context else 0.5

    confidence_score = ocr_result.confidence
    text_volume_score = _text_volume_score(ocr_result)
    quality_score = confidence_score * 0.4 + text_volume_score * 0.3 + coverage_ratio * 0.3

    analysis = _build_analysis_text(image_type, entities, ocr_result, asset, coverage_ratio)
    summary = _build_summary(image_type, entities, ocr_result)

    return OcrAnalysis(
        analysis=analysis,
        summary=summary,
        quality_score=quality_score,
        needs_vlm=quality_score < quality_threshold,
        image_type=image_type,
        entities=entities,
        coverage_ratio=coverage_ratio,
    )


def _classify_image_type(ocr_result: OcrResult, asset: dict[str, Any]) -> str:
    """基于 OCR 文字和元数据判断图片类型。"""
    text_lower = ocr_result.text.lower()
    kind = (asset.get("kind", "") or "").lower()
    section = (asset.get("section_path", "") or "").lower()

    if kind in ("board", "mindnote"):
        if any(kw in ocr_result.text for kw in STATE_KEYWORDS):
            return "状态图"
        if any(kw in ocr_result.text for kw in FLOW_KEYWORDS):
            return "流程图"
        return "画板"

    if "流程" in section or "flow" in text_lower:
        return "流程图"
    if "状态" in section or "state" in text_lower:
        return "状态图"

    text = ocr_result.text
    ui_count = sum(1 for kw in UI_KEYWORDS if kw in text)
    flow_count = sum(1 for kw in FLOW_KEYWORDS if kw in text)
    table_count = sum(1 for kw in TABLE_KEYWORDS if kw in text)

    if table_count >= 3:
        return "表格"
    if ui_count >= 3:
        return "UI截图"
    if flow_count >= 3:
        return "流程图"

    return "UI截图"


def _extract_entities(ocr_result: OcrResult) -> list[str]:
    """从 OCR 文字中提取业务实体（字段名、按钮文案、状态枚举等）。"""
    entities: list[str] = []
    seen: set[str] = set()

    for line in ocr_result.lines:
        line = line.strip()
        if not line or len(line) > 50:
            continue

        if any(kw in line for kw in UI_KEYWORDS | STATE_KEYWORDS | TABLE_KEYWORDS) and line not in seen:
            entities.append(line)
            seen.add(line)

        colon_match = re.match(r"^(.{2,15})[：:]\s*(.+)$", line)
        if colon_match:
            field_name = colon_match.group(1).strip()
            if field_name not in seen:
                entities.append(field_name)
                seen.add(field_name)

    return entities[:30]


def _compute_coverage(ocr_result: OcrResult, prd_context: str) -> float:
    """计算 OCR 文字在 PRD 文本中的覆盖率。"""
    if not prd_context or not ocr_result.lines:
        return 0.5

    matched = 0
    total = 0
    for line in ocr_result.lines:
        words = re.findall(r"[一-鿿]{2,}|[a-zA-Z]{3,}", line)
        for word in words:
            total += 1
            if word in prd_context:
                matched += 1

    return matched / total if total > 0 else 0.5


def _text_volume_score(ocr_result: OcrResult) -> float:
    """基于提取文字量评分。"""
    char_count = len(ocr_result.text)
    if char_count < 10:
        return 0.1
    if char_count < 50:
        return 0.3
    if char_count < 200:
        return 0.6
    if char_count < 500:
        return 0.8
    return 1.0


def _build_analysis_text(
    image_type: str,
    entities: list[str],
    ocr_result: OcrResult,
    asset: dict[str, Any],
    coverage_ratio: float,
) -> str:
    """构建分析文本。"""
    parts: list[str] = []
    section = asset.get("section_path", "")

    parts.append(f"图片类型: {image_type}")
    if section:
        parts.append(f"所属章节: {section}")
    parts.append(f"OCR 引擎: {ocr_result.engine} (置信度: {ocr_result.confidence:.0%})")
    parts.append(f"提取文字量: {len(ocr_result.text)} 字符, {len(ocr_result.lines)} 行")

    if entities:
        parts.append(f"识别到的业务实体: {', '.join(entities[:10])}")
        if len(entities) > 10:
            parts.append(f"  ...及其他 {len(entities) - 10} 个")

    if coverage_ratio > 0:
        parts.append(f"PRD 文本覆盖率: {coverage_ratio:.0%}")

    return "\n".join(parts)


def _build_summary(image_type: str, entities: list[str], ocr_result: OcrResult) -> str:
    """构建摘要（一句话）。"""
    entity_hint = f"，含 {', '.join(entities[:3])}" if entities else ""
    line_count = len(ocr_result.lines)
    return f"{image_type}（{line_count}行文字{entity_hint}）"
