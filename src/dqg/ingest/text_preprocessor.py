"""文本预处理器：将 PRD 原始 Markdown 中的隐式结构显式化。

在 ingest 完成后、Phase 执行前运行，输出 plain_text_enhanced.txt。
处理：版本颜色标注 → [V1.x] 标签，删除线 → [DELETED]，
功能描述表格展开，未解决评论摘要。
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from dqg.json_utils import dump_json_str

if TYPE_CHECKING:
    from pathlib import Path

_SPAN_RE = re.compile(
    r'<span\s+style="color:\s*([^"]+)">(.*?)</span>',
    re.DOTALL,
)
_STRIKETHROUGH_RE = re.compile(r"~~(.*?)~~", re.DOTALL)
_IMG_TAG_RE = re.compile(r'<img\s+src="feishu://image/([^"]+)"[^>]*>')
_BR_TAG_RE = re.compile(r"<br\s*/?>")

DEFAULT_VERSION_COLOR_MAP: dict[str, str] = {
    "#8F959E": "V1.1",
    "#E6B800": "V1.2",
    "#3370FF": "V1.3",
    "#34C759": "V1.3",
}


def preprocess_plain_text(
    plain_text_path: Path,
    output_dir: Path,
    comments_path: Path | None = None,
) -> dict[str, str]:
    """对 plain_text.txt 做预处理，输出增强版本。

    Returns:
        {"enhanced": str, "version_changes": str, "unresolved_comments": str}
        值为输出文件路径，空字符串表示未生成。
    """
    if not plain_text_path.exists():
        return {"enhanced": "", "version_changes": "", "unresolved_comments": ""}

    text = plain_text_path.read_text(encoding="utf-8")
    color_map = _extract_version_color_map(text)
    if not color_map:
        color_map = DEFAULT_VERSION_COLOR_MAP

    version_changes = _collect_version_changes(text, color_map)
    text = _replace_version_spans(text, color_map)
    text = _replace_strikethroughs(text)
    text = _expand_feature_tables(text)
    text = _clean_img_tags(text)
    text = _clean_br_tags(text)

    output_dir.mkdir(parents=True, exist_ok=True)
    enhanced_path = output_dir / "plain_text_enhanced.txt"
    enhanced_path.write_text(text, encoding="utf-8")

    vc_path = output_dir / "version_changes.json"
    vc_path.write_text(dump_json_str(version_changes), encoding="utf-8")

    result = {
        "enhanced": str(enhanced_path),
        "version_changes": str(vc_path),
        "unresolved_comments": "",
    }

    if comments_path and comments_path.exists():
        unresolved = _extract_unresolved_comments(comments_path)
        if unresolved:
            uc_path = output_dir / "_unresolved_comments.md"
            uc_path.write_text(unresolved, encoding="utf-8")
            result["unresolved_comments"] = str(uc_path)

    _info(f"预处理完成: {enhanced_path.name} ({len(text)} chars, {len(version_changes)} versions)")
    return result


def _extract_version_color_map(text: str) -> dict[str, str]:
    """从版本历史表自动提取颜色→版本号映射。"""
    color_map: dict[str, str] = {}
    lines = text.split("\n")

    for line in lines:
        if not _is_table_row(line):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 3:
            continue

        version_match = re.search(r"V\d+\.\d+", cells[1] if len(cells) > 1 else "")
        if not version_match:
            continue
        version = version_match.group()

        for span_match in _SPAN_RE.finditer(line):
            color = span_match.group(1).strip()
            if color and color not in color_map:
                color_map[color] = version

    return color_map


def _replace_version_spans(text: str, color_map: dict[str, str]) -> str:
    """将 <span style="color:...">text</span> 替换为 [V1.x] text。"""

    def _replacer(m: re.Match) -> str:
        color = m.group(1).strip()
        content = m.group(2)
        version = color_map.get(color)
        if version:
            return f"[{version}] {content}"
        return content

    return _SPAN_RE.sub(_replacer, text)


def _replace_strikethroughs(text: str) -> str:
    """将 ~~text~~ 替换为 [DELETED] text。"""

    def _replacer(m: re.Match) -> str:
        content = m.group(1).strip()
        if not content:
            return ""
        return f"[DELETED] {content}"

    return _STRIKETHROUGH_RE.sub(_replacer, text)


def _collect_version_changes(text: str, color_map: dict[str, str]) -> dict[str, list[str]]:
    """按版本分组收集变更内容。"""
    changes: dict[str, list[str]] = {}
    for m in _SPAN_RE.finditer(text):
        color = m.group(1).strip()
        content = m.group(2).strip()
        version = color_map.get(color)
        if version and content:
            clean = _SPAN_RE.sub(lambda x: x.group(2), content)
            clean = _STRIKETHROUGH_RE.sub("", clean).strip()
            if clean and len(clean) > 2:
                changes.setdefault(version, []).append(clean)

    for v in changes:
        changes[v] = list(dict.fromkeys(changes[v]))

    return changes


def _expand_feature_tables(text: str) -> str:
    """将功能描述表格展开为独立段落。

    识别 | 模块 | ... | 功能描述 | 格式的表格，
    将功能描述列展开，保留模块名作为子标题。
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if _is_feature_table_header(line):
            header_cells = [c.strip() for c in line.split("|")[1:-1]]
            desc_col = _find_description_column(header_cells)

            if desc_col >= 0 and i + 1 < len(lines) and _is_table_separator(lines[i + 1]):
                i += 2
                while i < len(lines) and _is_table_row(lines[i]):
                    cells = _split_table_row(lines[i])
                    module_name = _clean_cell(cells[0]) if cells else ""
                    desc = _clean_cell(cells[desc_col]) if len(cells) > desc_col else ""

                    if module_name and desc:
                        result.append(f"\n**[{module_name}]**\n")
                        expanded = _expand_br_to_lines(desc)
                        result.append(expanded)
                        result.append("")
                    elif desc:
                        expanded = _expand_br_to_lines(desc)
                        result.append(expanded)
                        result.append("")
                    i += 1
                continue

        result.append(line)
        i += 1

    return "\n".join(result)


def _clean_img_tags(text: str) -> str:
    """将 <img src="feishu://image/xxx"> 替换为 [图片: xxx]。"""
    return _IMG_TAG_RE.sub(r"[图片: \1]", text)


def _clean_br_tags(text: str) -> str:
    """将残留的 <br> 替换为换行。"""
    return _BR_TAG_RE.sub("\n", text)


def _extract_unresolved_comments(comments_path: Path) -> str:
    """从 comments.md 提取未解决评论，生成摘要。"""
    text = comments_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    unresolved: list[dict[str, str]] = []

    for line in lines:
        if not _is_table_row(line):
            continue
        if "💬" not in line:
            continue
        if "↳ 回复" in line:
            continue

        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 7:
            continue

        num = cells[0].strip()
        section = cells[1].strip()
        quote = cells[3].strip()
        comment = cells[6].strip()

        if num and comment:
            unresolved.append(
                {
                    "num": num,
                    "section": section,
                    "quote": quote,
                    "comment": comment,
                }
            )

    if not unresolved:
        return ""

    md_lines = [
        "# 未解决评论摘要（GAP/OPEN 候选）",
        "",
        f"共 {len(unresolved)} 条未解决评论：",
        "",
        "| # | 章节 | 引用 | 评论内容 |",
        "|---|------|------|---------|",
    ]
    for item in unresolved:
        md_lines.append(f"| {item['num']} | {item['section']} | {item['quote']} | {item['comment']} |")

    return "\n".join(md_lines) + "\n"


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 3


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|[\s\-:|]+\|", line))


def _is_feature_table_header(line: str) -> bool:
    if not _is_table_row(line):
        return False
    lower = line.lower()
    return "功能描述" in lower or "功能说明" in lower


def _find_description_column(headers: list[str]) -> int:
    for i, h in enumerate(headers):
        clean = re.sub(r"\*+", "", h).strip()
        if "功能描述" in clean or "功能说明" in clean:
            return i
    return -1


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.split("|")[1:-1]]


def _clean_cell(cell: str) -> str:
    cell = _IMG_TAG_RE.sub("", cell)
    cell = re.sub(r"https?://\S+", "", cell)
    cell = re.sub(r"\*+", "", cell)
    cell = _BR_TAG_RE.sub("\n", cell)
    return cell.strip()


def _expand_br_to_lines(text: str) -> str:
    text = _BR_TAG_RE.sub("\n", text)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def _info(msg: str) -> None:
    print(f"[text_preprocessor] {msg}")


def _warn(msg: str) -> None:
    print(f"[text_preprocessor][WARN] {msg}", file=sys.stderr)
