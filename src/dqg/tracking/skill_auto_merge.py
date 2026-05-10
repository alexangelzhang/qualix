"""Skill Auto-Merge：高置信度规则自动合入 SKILL.md + holdout 验证 + hints 写入.

从 skill_reflector.py 拆分，处理自动合入逻辑和 hints/suggestion 文件写入。

2026-05-10 增强：
- `apply_to_skill_file` 返回 `ApplyResult`（含 inserted/skipped/diff），支持 dry_run 与幂等检查
- 用 `MarkdownSectionEditor`（regex-based heading 扫描，不引入新依赖）精确定位 section
- `verify_with_holdout` 关 fail-open：异常或 holdout 未 ready 时默认拒绝 merge，保留 `allow_fail_open=True` 作为 escape hatch
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dqg.constants import PHASE_DIR_MAP
from dqg.log import get_logger

log = get_logger(__name__)

# 匹配 Markdown ATX heading（#、##、### ...）；忽略代码块内部的 `#` 由 MarkdownSectionEditor 处理
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class _Section:
    """一个 heading 划定的 section。body 范围是 [body_start, body_end)（行下标）."""

    heading_idx: int  # heading 行本身的下标
    level: int
    title: str
    body_start: int  # heading 之后第一行
    body_end: int  # 下一个 <= level 的 heading 前（或文件末）


class MarkdownSectionEditor:
    """轻量级 Markdown section 查找器，用 regex 扫 ATX heading，跳过围栏代码块.

    能做的事：
    - 把文件按 H1-H6 切成 sections，每个 section 知道自己的 body 范围
    - 按标题关键词找 section（子串 / 大小写敏感，按项目约定 SKILL.md 里是中文/英文混排）
    - 判断一个文本是否已经出现在 section body 里（幂等检查）

    不做的事：
    - 不解析列表 / 表格 / 链接（不需要）；调用方自己处理 `|` 表格或 `-` 列表
    """

    def __init__(self, lines: list[str]):
        self._lines = lines
        self._sections = self._scan_sections(lines)

    @staticmethod
    def _scan_sections(lines: list[str]) -> list[_Section]:
        sections: list[_Section] = []
        in_fence = False
        heading_rows: list[tuple[int, int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 围栏代码块开关：``` 或 ~~~
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = _HEADING_RE.match(line)
            if m:
                heading_rows.append((i, len(m.group(1)), m.group(2).strip()))
        # 用堆栈式逻辑计算每个 heading 的 body_end
        for idx, (row, level, title) in enumerate(heading_rows):
            body_start = row + 1
            body_end = len(lines)
            for j in range(idx + 1, len(heading_rows)):
                nxt_row, nxt_level, _ = heading_rows[j]
                if nxt_level <= level:
                    body_end = nxt_row
                    break
            sections.append(
                _Section(heading_idx=row, level=level, title=title, body_start=body_start, body_end=body_end)
            )
        return sections

    def find_section(self, *keywords: str) -> _Section | None:
        """按关键词查 section（第一个 title 包含任一关键词的）."""
        for s in self._sections:
            if any(kw in s.title for kw in keywords):
                return s
        return None

    def section_body(self, section: _Section) -> list[str]:
        return self._lines[section.body_start : section.body_end]

    def contains_in_body(self, section: _Section, needle: str, *, min_match_len: int = 12) -> bool:
        """幂等检查：needle 是否已出现在 section body 里（用 needle 的前 N 字符做子串匹配）."""
        if not needle:
            return False
        probe = needle.strip()[:min_match_len]
        if not probe:
            return False
        body = "\n".join(self.section_body(section))
        return probe in body


@dataclass
class ApplyResult:
    applied: bool  # 是否真正写了盘（dry_run=True 时永远 False）
    inserted_entries: list[str] = field(default_factory=list)  # 实际新增的 markdown 片段
    skipped_duplicates: list[str] = field(default_factory=list)  # 被幂等检查跳过的规则原文
    sections_touched: list[str] = field(default_factory=list)  # 插入点的 section title
    rendered_diff: str = ""  # 人类可读的 before→after 差异摘要


def _format_anti_rat_entry(rule_text: str) -> str:
    """构造 Anti-Rationalization 表格的一行：| excuse | rebuttal |."""
    text = rule_text.strip()
    # 约定：短句当 excuse，长句当 rebuttal；没法干净切分时两者同文
    return f'| "{text}" | {text} |'


def _format_red_line_entry(rule_text: str) -> str:
    return f"- {rule_text.strip()}"


def _render_apply_diff(
    inserted: list[tuple[str, str]],  # (section_title, entry)
    skipped: list[str],
) -> str:
    parts: list[str] = []
    if inserted:
        parts.append("Inserted:")
        for section, entry in inserted:
            parts.append(f"  [{section}] {entry}")
    if skipped:
        parts.append("Skipped as duplicate:")
        for rule in skipped:
            parts.append(f"  - {rule[:80]}")
    return "\n".join(parts) if parts else "(no changes)"


def apply_to_skill_file(
    skill_path: str,
    suggested_changes: list[str],
    *,
    dry_run: bool = False,
) -> ApplyResult:
    """Parse SKILL.md and append new rules to the appropriate section.

    对每条 suggested_change：
    1. 优先插入 Anti-Rationalization 表格（在 H2/H3 "Anti-Rationalization" 下）
    2. 找不到就退到 "红线规则" / "禁止事项" 列表
    3. 还不行就 append 到文件末的 "Auto-merged Rules" 区（不存在则创建）
    4. 每条插入前用 `contains_in_body` 做幂等检查，已存在则 skip（不截断 rule_text）
    5. dry_run=True 时只返回 rendered_diff，不写盘

    Returns:
        ApplyResult（即使 applied=False 也返回，不再用 bool）
    """
    path = Path(skill_path)
    if not path.exists() or not suggested_changes:
        return ApplyResult(applied=False, rendered_diff="(skipped: no file or no changes)")

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    editor = MarkdownSectionEditor(lines)

    anti_rat = editor.find_section("Anti-Rationalization")
    red_line = editor.find_section("红线规则", "禁止事项")

    inserted_entries: list[str] = []
    inserted_with_section: list[tuple[str, str]] = []
    skipped: list[str] = []
    sections_touched_set: set[str] = set()
    insertions: list[tuple[int, str, str]] = []  # (insert_at, line_to_insert, section_title)

    for rule_text in suggested_changes:
        rt = rule_text.strip()
        if not rt:
            continue

        target_section: _Section | None = None
        entry: str = ""

        if anti_rat is not None:
            target_section = anti_rat
            entry = _format_anti_rat_entry(rt)
        elif red_line is not None:
            target_section = red_line
            entry = _format_red_line_entry(rt)

        if target_section is not None:
            if editor.contains_in_body(target_section, rt):
                skipped.append(rt)
                continue
            # 插入点：section body 末尾（跳过尾部连续空行）
            insert_at = target_section.body_end
            while insert_at - 1 > target_section.body_start and not lines[insert_at - 1].strip():
                insert_at -= 1
            insertions.append((insert_at, entry, target_section.title))
            inserted_entries.append(entry)
            inserted_with_section.append((target_section.title, entry))
            sections_touched_set.add(target_section.title)
            continue

        # Fallback: "Auto-merged Rules" section at EOF
        entry = _format_red_line_entry(rt)
        eof_section = editor.find_section("Auto-merged Rules")
        if eof_section is not None and editor.contains_in_body(eof_section, rt):
            skipped.append(rt)
            continue
        inserted_entries.append(entry)
        inserted_with_section.append(("Auto-merged Rules", entry))
        sections_touched_set.add("Auto-merged Rules")
        insertions.append((len(lines), entry, "Auto-merged Rules"))

    rendered_diff = _render_apply_diff(inserted_with_section, skipped)

    if not inserted_entries:
        return ApplyResult(
            applied=False,
            inserted_entries=[],
            skipped_duplicates=skipped,
            sections_touched=[],
            rendered_diff=rendered_diff,
        )

    if dry_run:
        return ApplyResult(
            applied=False,
            inserted_entries=inserted_entries,
            skipped_duplicates=skipped,
            sections_touched=sorted(sections_touched_set),
            rendered_diff=rendered_diff,
        )

    # 真写盘：倒序 insert 防 index 漂移；需要创建 "Auto-merged Rules" 时集中 append EOF
    eof_entries: list[str] = []
    sorted_inserts = sorted(insertions, key=lambda x: x[0], reverse=True)
    existing_eof = editor.find_section("Auto-merged Rules") is not None
    for insert_at, line_to_insert, section_title in sorted_inserts:
        if section_title == "Auto-merged Rules" and not existing_eof:
            eof_entries.append(line_to_insert)
        else:
            lines.insert(insert_at, line_to_insert)

    if eof_entries:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("## Auto-merged Rules")
        lines.append("")
        for entry in reversed(eof_entries):
            lines.append(entry)

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info(
        "apply_to_skill_file: %s, inserted=%d, skipped=%d",
        skill_path,
        len(inserted_entries),
        len(skipped),
    )
    return ApplyResult(
        applied=True,
        inserted_entries=inserted_entries,
        skipped_duplicates=skipped,
        sections_touched=sorted(sections_touched_set),
        rendered_diff=rendered_diff,
    )


def verify_with_holdout(phase: str, *, allow_fail_open: bool = False) -> bool:
    """Run holdout validation after auto-merge. Returns True if safe to keep the merge.

    行为（2026-05-10 起关 fail-open）：
    - validate_against_holdout 抛异常 → 返回 False（除非 allow_fail_open=True）
    - overfitting_signal=True → False
    - holdout_ready=False（holdout 不足或未标记）→ False（除非 allow_fail_open=True）
    - 只有 overfitting_signal=False AND holdout_ready=True → True

    allow_fail_open 用作 escape hatch：holdout 基础设施尚未搭好时手动开启允许 merge。
    """
    from dqg.quality.eval.eval_holdout import validate_against_holdout

    try:
        result = validate_against_holdout(phase)
    except Exception as e:
        if allow_fail_open:
            log.warning("Holdout validation errored for %s: %s, allow_fail_open=True → allowing merge", phase, e)
            return True
        log.warning("Holdout validation errored for %s: %s, rejecting merge", phase, e)
        return False

    reason = result.get("decision_reason", "")
    if result.get("overfitting_signal"):
        log.warning(
            "Holdout overfitting detected for %s: %s (coverage_gap=%.2f, divergence=%.2f, hit_rate=%.2f)",
            phase,
            reason,
            result.get("coverage_gap", 0.0),
            result.get("distribution_divergence", 0.0),
            result.get("holdout_hit_rate", 0.0),
        )
        return False

    if not result.get("holdout_ready", False):
        if allow_fail_open:
            log.warning(
                "Holdout not ready for %s (%s), allow_fail_open=True → allowing merge",
                phase,
                reason,
            )
            return True
        log.warning(
            "Holdout not ready for %s (%s), rejecting merge",
            phase,
            reason,
        )
        return False

    return True


def _write_hints_file(
    project_id: str,
    phase: str,
    hint_type: str,
    failure_patterns: list[str],
    suggested_changes: list[str],
) -> str:
    """Append hints to _{hint_type}_hints.md in phase _internal/ dir."""
    dir_suffix = PHASE_DIR_MAP.get(phase, phase)
    hints_dir = Path("output") / project_id / dir_suffix / "_internal"
    hints_dir.mkdir(parents=True, exist_ok=True)
    path = hints_dir / f"_{hint_type}_hints.md"

    label = "context gap" if hint_type == "context" else "schema issue"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## [{timestamp}] Auto-detected {label}\n\n"
    for p in failure_patterns[:3]:
        entry += f"- {p}\n"
    if suggested_changes:
        entry += f"\n**建议**: {suggested_changes[0]}\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(entry)
    log.info("%s hints written: %s", hint_type.capitalize(), path)
    return str(path)


def write_context_hints(
    project_id: str,
    phase: str,
    failure_patterns: list[str],
    suggested_changes: list[str],
) -> str:
    return _write_hints_file(project_id, phase, "context", failure_patterns, suggested_changes)


def write_schema_hints(
    project_id: str,
    phase: str,
    failure_patterns: list[str],
    suggested_changes: list[str],
) -> str:
    return _write_hints_file(project_id, phase, "schema", failure_patterns, suggested_changes)


def write_suggestion_file(
    project_id: str,
    phase: str,
    root_cause: str,
    failure_patterns: list[str],
    suggested_changes: list[str],
) -> str:
    """Write suggestion file for human review."""
    suggestion_dir = Path("output") / project_id / PHASE_DIR_MAP.get(phase, phase)
    suggestion_dir.mkdir(parents=True, exist_ok=True)
    path = suggestion_dir / f"_skill_suggestions_{phase}.md"

    content = f"# Skill Evolution Suggestions — Phase {phase}\n\n"
    content += f"Root Cause: {root_cause}\n\n"
    content += "## Failure Patterns\n\n"
    for p in failure_patterns:
        content += f"- {p}\n"
    content += "\n## Suggested Changes\n\n"
    for c in suggested_changes:
        content += f"- {c}\n"

    path.write_text(content, encoding="utf-8")
    return str(path)


__all__ = [
    "ApplyResult",
    "MarkdownSectionEditor",
    "apply_to_skill_file",
    "verify_with_holdout",
    "write_context_hints",
    "write_schema_hints",
    "write_suggestion_file",
]
