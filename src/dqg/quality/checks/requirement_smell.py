"""Requirements Smell 检测：在 Phase Q01 提取前识别低质量需求段落.

纯规则检测（零 LLM 调用），标记歧义/不完整/矛盾的需求，
输出 _requirement_smells.json 供 Phase Q01 降低对应段落的置信度。

参考论文 2501.04810（Requirements Smell Detection）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dqg.json_utils import save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


@dataclass
class RequirementSmell:
    """一条需求异味."""

    smell_type: str  # VAGUE | INCOMPLETE | CONTRADICTORY | UNBOUNDED | SUBJECTIVE
    severity: str  # HIGH | MEDIUM | LOW
    description: str  # 异味描述
    matched_text: str  # 匹配到的原文片段
    line_number: int  # 行号（1-based）
    suggestion: str  # 修复建议


@dataclass
class SmellReport:
    """检测报告."""

    total_lines: int
    smells: list[RequirementSmell] = field(default_factory=list)
    smell_count_by_type: dict[str, int] = field(default_factory=dict)
    quality_score: float = 1.0  # 0-1，越低越差


# ---------------------------------------------------------------------------
# 检测规则
# ---------------------------------------------------------------------------

# 模糊量词（VAGUE）
_VAGUE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(适当|合理|尽量|尽可能|大概|大约|若干|一些|部分|某些)"), "模糊量词"),
    (re.compile(r"(较快|较慢|较多|较少|较大|较小|较高|较低)"), "模糊比较词"),
    (re.compile(r"(等等|之类|诸如此类|以此类推)"), "开放式枚举"),
    (re.compile(r"(可能|也许|或许|大致|基本上)"), "不确定性表述"),
    (re.compile(r"(必要时|需要时|适时|酌情)"), "条件模糊"),
]

# 缺少验收标准（INCOMPLETE）
_INCOMPLETE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(支持|实现|提供|具备).{2,20}功能", re.DOTALL), "功能描述缺少验收标准"),
    (re.compile(r"(优化|改善|提升|增强).{0,10}(性能|体验|效率|速度)"), "优化目标缺少量化指标"),
]

# 主观判断（SUBJECTIVE）
_SUBJECTIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(美观|好看|友好|简洁|优雅|直观|舒适)"), "主观审美判断"),
    (re.compile(r"(用户体验好|交互流畅|界面清晰)"), "主观体验描述"),
]

# 无边界值（UNBOUNDED）
_UNBOUNDED_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(不限|无限制|不做限制|没有上限)"), "缺少边界约束"),
    (re.compile(r"(所有|全部|任意|任何).{0,5}(用户|数据|记录|请求)"), "范围过大无约束"),
    (re.compile(r"(实时|即时|立即|秒级)(?!.{0,10}\d)"), "时效要求缺少量化"),
]

# 矛盾信号（CONTRADICTORY）— 同一段落内出现对立表述
_CONTRADICTION_PAIRS: list[tuple[re.Pattern, re.Pattern, str]] = [
    (re.compile(r"必须"), re.compile(r"可选|非必须|可以不"), "必须 vs 可选矛盾"),
    (re.compile(r"同步"), re.compile(r"异步"), "同步 vs 异步矛盾"),
    (re.compile(r"允许"), re.compile(r"禁止|不允许|不可以"), "允许 vs 禁止矛盾"),
]


def detect_smells(text: str) -> SmellReport:
    """对需求文本执行全量 smell 检测.

    Args:
        text: 需求文档全文

    Returns:
        SmellReport
    """
    lines = text.splitlines()
    smells: list[RequirementSmell] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or len(stripped) < 5:
            continue

        # VAGUE
        for pattern, desc in _VAGUE_PATTERNS:
            m = pattern.search(stripped)
            if m:
                smells.append(
                    RequirementSmell(
                        smell_type="VAGUE",
                        severity="MEDIUM",
                        description=desc,
                        matched_text=m.group(),
                        line_number=i,
                        suggestion=f"将「{m.group()}」替换为具体数值或明确条件",
                    )
                )

        # SUBJECTIVE
        for pattern, desc in _SUBJECTIVE_PATTERNS:
            m = pattern.search(stripped)
            if m:
                smells.append(
                    RequirementSmell(
                        smell_type="SUBJECTIVE",
                        severity="MEDIUM",
                        description=desc,
                        matched_text=m.group(),
                        line_number=i,
                        suggestion=f"将「{m.group()}」转化为可测量的验收标准",
                    )
                )

        # UNBOUNDED
        for pattern, desc in _UNBOUNDED_PATTERNS:
            m = pattern.search(stripped)
            if m:
                smells.append(
                    RequirementSmell(
                        smell_type="UNBOUNDED",
                        severity="HIGH",
                        description=desc,
                        matched_text=m.group(),
                        line_number=i,
                        suggestion="补充具体的上限/下限/超时/容量约束",
                    )
                )

    # INCOMPLETE: 检查功能描述段落是否缺少验收标准
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        for pattern, desc in _INCOMPLETE_PATTERNS:
            m = pattern.search(stripped)
            if m:
                # 检查同段落或下一行是否有量化指标
                context = stripped
                if i < len(lines):
                    context += " " + lines[i].strip()
                has_metric = bool(re.search(r"\d+[%秒ms毫秒分钟条个次]", context))
                if not has_metric:
                    smells.append(
                        RequirementSmell(
                            smell_type="INCOMPLETE",
                            severity="HIGH",
                            description=desc,
                            matched_text=m.group(),
                            line_number=i,
                            suggestion="补充可量化的验收标准（如响应时间、成功率、覆盖范围）",
                        )
                    )

    # CONTRADICTORY: 按段落检测矛盾
    paragraphs = text.split("\n\n")
    para_start = 1
    for para in paragraphs:
        para_lines = para.count("\n") + 1
        for pat_a, pat_b, desc in _CONTRADICTION_PAIRS:
            if pat_a.search(para) and pat_b.search(para):
                smells.append(
                    RequirementSmell(
                        smell_type="CONTRADICTORY",
                        severity="HIGH",
                        description=desc,
                        matched_text=para.strip()[:80],
                        line_number=para_start,
                        suggestion="消除矛盾表述，明确唯一行为",
                    )
                )
        para_start += para_lines

    # 去重（同行同类型只保留一条）
    seen: set[tuple[int, str]] = set()
    unique: list[RequirementSmell] = []
    for s in smells:
        key = (s.line_number, s.smell_type)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    # 统计
    count_by_type: dict[str, int] = {}
    for s in unique:
        count_by_type[s.smell_type] = count_by_type.get(s.smell_type, 0) + 1

    # 质量分：每个 HIGH smell 扣 0.05，MEDIUM 扣 0.02，最低 0
    penalty = sum(0.05 if s.severity == "HIGH" else 0.02 for s in unique)
    quality_score = max(0.0, round(1.0 - penalty, 2))

    return SmellReport(
        total_lines=len(lines),
        smells=unique,
        smell_count_by_type=count_by_type,
        quality_score=quality_score,
    )


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def write_requirement_smells(
    output_dir: Path,
    project_id: str,
    text: str,
) -> Path | None:
    """检测并写入需求异味报告到 Phase Q01 目录.

    Returns:
        写入的 JSON 文件路径
    """
    report = detect_smells(text)
    if not report.smells:
        log.info("Requirement smells: none detected (quality=%.2f)", report.quality_score)
        return None

    from dqg.constants import PHASE_DIR_MAP

    dir_suffix = PHASE_DIR_MAP.get("Q01", "phaseA")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "total_lines": report.total_lines,
        "quality_score": report.quality_score,
        "smell_count": len(report.smells),
        "smell_count_by_type": report.smell_count_by_type,
        "smells": [
            {
                "smell_type": s.smell_type,
                "severity": s.severity,
                "description": s.description,
                "matched_text": s.matched_text,
                "line_number": s.line_number,
                "suggestion": s.suggestion,
            }
            for s in report.smells
        ],
    }

    json_path = int_dir / "_requirement_smells.json"
    save_json(json_path, data)

    log.info(
        "Requirement smells: %d detected (quality=%.2f) — %s",
        len(report.smells),
        report.quality_score,
        report.smell_count_by_type,
    )
    return json_path


def get_smell_lines(report: SmellReport) -> set[int]:
    """返回有 smell 的行号集合，供 Phase Q01 降低置信度."""
    return {s.line_number for s in report.smells}
