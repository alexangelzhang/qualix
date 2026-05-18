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
    # Q01: PRD 阶段，不允许用需求 ID（REQ/BR/SE/GAP）自证来源（循环引用），
    # 但允许 PRD 原文裸引用（plain_text.txt:行号 / blocks.raw.json:行号）——
    # 这类引用等价于 [来源: plain_text.txt:行号]，只是表格列里省去了括号格式。
    "Q01": re.compile(r"plain_text\.txt:\d+|blocks\.raw\.json:\d+|comments\.md:\d+"),
    # Q02: 技术方案生成类——来源是 tech_design 原文或架构/接口/数据/异常/性能 ID，以及代码行号
    # 不允许用 REQ/BR/SE/GAP 做"来源"，那是追溯覆盖，归 R-TRACEABILITY 管
    "Q02": re.compile(r"tech_design\.md|ARCH-\d+|API-\d+|DATA-\d+|EXC-\d+|PERF-\d+|\.java:\d+"),
    # Q03: 技术方案五维度
    "Q03": re.compile(r"tech_design\.md|ARCH-\d+|API-\d+|DATA-\d+|EXC-\d+|PERF-\d+"),
    # Q04: 覆盖度审计，来源是技术方案原文或代码坐标
    # REQ/BR/SE/GAP 是被审计的主语，不是结论的出处，不能作为来源
    "Q04": re.compile(r"tech_design\.md|HLD|\.java(?::\d+)?|ARCH-\d+|API-\d+"),
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
# "建议" 替换为更精确的复合词，避免将日常叙述性建议误识别为需要来源的结论
_CONCLUSION_PATTERN = re.compile(
    r"(缺失|遗漏|未覆盖|不完整"
    r"|存在风险|高风险|安全风险|合规风险|性能风险"
    r"|建议补充|建议修复|建议增加|建议移除|建议重构"
    r"|BLOCKER|CRITICAL|WARNING"
    r"|COVERED|NOT_COVERED|PARTIAL|WRONG_TARGET|CONFLICT)",
)

# 合法 ID 格式（用于判断表格行是否有实质内容，覆盖所有 Phase 特有 ID）
_VALID_ID_PATTERN = re.compile(
    r"\b(REQ|BR|SE|GAP|OPEN|EUT|ARCH|API|DATA|EXC|PERF|D)-\d{1,4}\b"
)

# 豁免章节：自我评审 + 叙述性章节（边界约定/评审结论/范围外发现等）
# 支持带序号标题（如 "## 11. 自我评审记录"）
_SELF_REVIEW_HEADING = re.compile(
    r"^#{1,3}\s*(\d+\.\s*)?"
    r"(自我评审|Judge|Critique|Step\s+\d"
    r"|边界约定|评审结论|范围外发现|统计|自检|修正|评审范围)",
    re.IGNORECASE,
)


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
        # GAP/OPEN 定义行：结构化声明，来源已在 JSON source 字段，不要求行内标注
        if stripped.startswith("|") and re.match(r"\|\s*(GAP|OPEN)-\d+", stripped):
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
