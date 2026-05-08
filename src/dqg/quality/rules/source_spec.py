"""Phase 级来源标注契约.

统一定义：
1. 通用基线 `[来源: xxx]` / `[Source: xxx]`
2. 每个 Phase 允许的额外来源形式（与该 Phase 业务语义对齐）
3. 结论行扫描（跳过表头/分隔线/标题/纯标签/自我评审章节）
4. 共享的行覆盖率计算

供 `rule_checks._check_source_annotation` 和
`report_quality_checks.check_source_annotations` 共享。
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# ---------------------------------------------------------------------------
# 来源形式
# ---------------------------------------------------------------------------

# 通用基线：任何 Phase 都接受 [来源: xxx] / [Source: xxx]
RE_SOURCE_BASE = re.compile(r"\[来源[:：]\s*.+?\]|\[Source:\s*.+?\]", re.IGNORECASE)

# 每个 Phase 允许的额外来源形式（叠加在基线之上）
PHASE_SOURCE_EXTRA: dict[str, re.Pattern[str]] = {
    # Q01: PRD 阶段，不允许用需求 ID 自证来源，必须 [来源: xxx]
    "Q01": re.compile(r"(?!)"),  # 永不匹配
    # Q02: 技术方案生成类——来源是 tech_design 原文或架构/接口/数据/异常/性能 ID，以及代码行号
    # 不允许用 REQ/BR/SE/GAP 做"来源"，那是追溯覆盖，归 R-TRACEABILITY 管
    "Q02": re.compile(r"tech_design\.md|ARCH-\d+|API-\d+|DATA-\d+|EXC-\d+|PERF-\d+|\.java:\d+"),
    # Q03: 技术方案五维度
    "Q03": re.compile(r"tech_design\.md|ARCH-\d+|API-\d+|DATA-\d+|EXC-\d+|PERF-\d+"),
    # Q04: 覆盖度审计，需求 + 技术方案 + 代码都可能是来源
    "Q04": re.compile(r"REQ-\d+|BR-\d+|SE-\d+|GAP-\d+|tech_design\.md|\.java:\d+"),
    # Q05: 单测设计
    "Q05": re.compile(r"SE-\d+|EUT-\d+|target_class|target_method"),
    # Q06: 单测实现审计（剔除 assertEquals/assertThrows/A组/B组，那是断言方法不是来源）
    "Q06": re.compile(r"SE-\d+|EUT-\d+|Test\.java|\.java:\d+"),
    # Q07: 代码评审
    "Q07": re.compile(r"D-\d+|\.java:\d+|行\d+|line\s*\d+"),
}


def is_source_annotated(line: str, phase_id: str) -> bool:
    """该行是否挂了基线或该 Phase 允许的来源."""
    if RE_SOURCE_BASE.search(line):
        return True
    extra = PHASE_SOURCE_EXTRA.get(phase_id)
    return bool(extra is not None and extra.search(line))


# ---------------------------------------------------------------------------
# 结论行扫描
# ---------------------------------------------------------------------------

# 判定性词汇：出现这些词的行视为"结论行"，需要挂来源
_CONCLUSION_PATTERN = re.compile(
    r"(缺失|遗漏|未覆盖|不完整|风险|问题|建议|BLOCKER|CRITICAL|WARNING"
    r"|COVERED|NOT_COVERED|PARTIAL|WRONG_TARGET|CONFLICT)",
)

# 合法 ID 格式（用于判断表格行是否有实质内容）
_VALID_ID_PATTERN = re.compile(r"\b(REQ|BR|SE|GAP|OPEN)-\d{1,4}\b")

# 自我评审章节起止
_SELF_REVIEW_HEADING = re.compile(r"^#{1,3}\s*(自我评审|Judge|Critique|Step\s+\d)")


def iter_conclusion_lines(text: str) -> Iterator[tuple[int, str]]:
    """产出所有判定性结论行（1-indexed line number + 行内容）.

    跳过：
    - 不含判定性词汇的行
    - 表头和 |---| 分隔线
    - Markdown 标题、空行
    - 纯标签行（如 severity: HIGH）
    - 自我评审/Judge/Critique/Step 章节内的行
    - 无具体 ID 的统计表格行
    """
    lines = text.splitlines()

    # 预扫描：定位表头（分隔线前一行）和分隔线本身
    table_header_lines: set[int] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and "---" in stripped and i > 0:
            table_header_lines.add(i)
            table_header_lines.add(i - 1)

    in_self_review = False
    for i, line in enumerate(lines):
        stripped = line.strip()

        # 自我评审章节切换
        if _SELF_REVIEW_HEADING.match(stripped):
            in_self_review = True
        elif stripped.startswith("#"):
            in_self_review = False

        if not _CONCLUSION_PATTERN.search(line):
            continue
        if i in table_header_lines:
            continue
        if stripped.startswith("|") and "---" in stripped:
            continue
        if stripped.startswith("#") or not stripped:
            continue
        # 纯标签行（冒号 + 少量词）
        if ":" in stripped and len(stripped.split()) <= 3:
            continue
        if in_self_review:
            continue
        # 统计行：表格里没有具体 ID
        if stripped.startswith("|") and not _VALID_ID_PATTERN.search(stripped):
            continue

        yield i + 1, stripped


def compute_source_coverage(text: str, phase_id: str) -> tuple[int, int, list[int]]:
    """计算结论行的来源标注覆盖率.

    Returns:
        (annotated_count, total_conclusion_count, missing_line_numbers)
    """
    annotated = 0
    total = 0
    missing: list[int] = []
    for lineno, content in iter_conclusion_lines(text):
        total += 1
        if is_source_annotated(content, phase_id):
            annotated += 1
        else:
            missing.append(lineno)
    return annotated, total, missing
