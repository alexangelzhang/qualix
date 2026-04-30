"""轻量文档摘要：纯规则提取，零 LLM 调用.

策略：保留标题层级 + 每个章节首段 + 表格 + 关键词行。
将 5000 行 PRD 压缩到 ~1000 行，token 降 80%。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def extract_summary(text: str, max_lines: int = 1000) -> str:
    """从文档中提取结构化摘要."""
    lines = text.split("\n")
    summary_lines: list[str] = []
    in_table = False
    lines_since_heading = 0
    max_lines_after_heading = 5  # 每个标题后保留的行数

    for line in lines:
        stripped = line.strip()

        # 标题：全部保留
        if re.match(r"^#{1,6}\s+", stripped):
            summary_lines.append(line)
            lines_since_heading = 0
            in_table = False
            continue

        # 表格行：全部保留
        if "|" in stripped and (stripped.startswith("|") or "---" in stripped):
            summary_lines.append(line)
            in_table = True
            continue
        elif in_table and stripped:
            in_table = False

        # 标题后的前 N 行：保留
        lines_since_heading += 1
        if lines_since_heading <= max_lines_after_heading and stripped:
            summary_lines.append(line)
            continue

        # 关键词行：保留
        if _is_key_line(stripped):
            summary_lines.append(line)
            continue

        # 超过 max_lines 停止
        if len(summary_lines) >= max_lines:
            summary_lines.append(f"\n... (已截取前 {max_lines} 行摘要)")
            break

    return "\n".join(summary_lines)


def _is_key_line(line: str) -> bool:
    """判断是否是关键行（包含重要业务信息）."""
    # 状态枚举
    if re.search(r"状态|枚举|类型|权限|角色", line):
        return True
    # 校验规则
    if re.search(r"校验|必填|必须|禁止|不允许|阻断", line):
        return True
    # 业务 ID
    if re.search(r"REQ-|BR-|SE-|GAP-|OPEN-", line):
        return True
    # 数字规则（金额、天数、数量限制）
    return bool(re.search(r"\d+天|\d+小时|\d+元|\d+条|\d+张|≤|≥|上限|下限", line))


def generate_summary_file(
    phase_dir: Path,
    max_lines: int = 1000,
) -> Path | None:
    """从文档生成摘要. 优先用 aggregate_plain_text.txt，其次 plain_text.txt."""
    ingest_subdir = phase_dir / "ingest"
    # 优先 aggregate（含子文档）
    for filename in ("aggregate_plain_text.txt", "plain_text.txt"):
        # 新路径优先，旧路径 fallback
        path = ingest_subdir / filename
        if not path.exists():
            path = phase_dir / filename
        if path.exists():
            text = path.read_text(encoding="utf-8")
            lines = text.split("\n")
            if len(lines) > max_lines:
                summary = extract_summary(text, max_lines)
                out = ingest_subdir / "plain_text_summary.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(summary, encoding="utf-8")
                return out
    return None
