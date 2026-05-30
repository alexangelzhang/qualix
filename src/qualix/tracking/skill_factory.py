"""Skill Factory：基于 bug case 库自动生成 skill 规则补充建议.

分析 bug case 的失败模式，自动生成：
1. Anti-Rationalization 条目（常见偷懒借口 + 反驳）
2. 红线规则补充建议
3. 已知错误模式更新

输出到 _skill_suggestions.md 供人工 review 后合入 skill 文件。
不直接修改 skill 文件——生成的建议必须经过人工审核。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from qualix.log import get_logger
from qualix.tracking.bug_cases import load_cases, load_cases_by_phase

log = get_logger(__name__)


# 失败模式 → 规则模板映射
_FAILURE_PATTERN_TEMPLATES: Final = MappingProxyType({
    # error_type 级别的模板
    "FN": MappingProxyType({
        "anti_rationalization": "{title} → 漏报是最危险的失败模式，宁可多报不可漏报",
        "red_line": "存在 FN 模式的场景必须在 skill 中显式列为检查项",
    }),
    "FP": MappingProxyType({
        "anti_rationalization": "{title} → 误报会侵蚀信任，标记前必须有充分证据",
        "red_line": "标记问题前必须排除合理的设计决策",
    }),
    "WRONG": MappingProxyType({
        "anti_rationalization": "{title} → 错判比漏判更隐蔽，因为它给出了错误的安全感",
        "red_line": "判定结论必须有原文/代码证据，不能基于推测",
    }),
})

# root_cause → 修复方向映射
_ROOT_CAUSE_ACTIONS: Final = MappingProxyType({
    "SKILL_RULE": "更新 skill 文件的执行规则或检查清单",
    "KNOWLEDGE": "补充领域知识到 references/ 或 knowledge base",
    "CONTEXT": "改进上下文加载策略或输入解析",
    "SCHEMA": "更新 schemas/ 下的校验规则",
})


def analyze_failure_patterns(
    phase: str | None = None,
) -> dict[str, Any]:
    """分析 bug case 库的失败模式.

    Returns:
        {
            "phase_distribution": {"Q01": 192, ...},
            "top_patterns": [{"pattern": "...", "count": N, "examples": [...]}],
            "lessons_by_phase": {"Q01": ["lesson1", ...], ...},
            "root_cause_distribution": {"SKILL_RULE": 257, ...},
        }
    """
    cases = load_cases_by_phase(phase, exclude_holdout=True) if phase else load_cases(exclude_holdout=True)

    # 按 phase 分组
    phase_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        phase_groups[c.get("phase", "?")].append(c)

    # 提取有 lesson 的 case
    lessons_by_phase: dict[str, list[dict[str, str]]] = defaultdict(list)
    for c in cases:
        lesson = c.get("lesson", "").strip()
        if lesson:
            lessons_by_phase[c.get("phase", "?")].append({
                "case_id": c.get("case_id", ""),
                "title": c.get("title", ""),
                "error_type": c.get("error_type", ""),
                "root_cause": c.get("root_cause", ""),
                "lesson": lesson,
                "tags": c.get("tags", []),
            })

    # 按 tags 聚合失败模式
    tag_counter: Counter = Counter()
    for c in cases:
        for tag in c.get("tags", []):
            if not tag.startswith("auto-generated") and not tag.startswith("project:"):
                tag_counter[tag] += 1

    # 按 error_type + root_cause 聚合
    pattern_counter: Counter = Counter()
    for c in cases:
        key = f"{c.get('error_type', '?')}:{c.get('root_cause', '?')}"
        pattern_counter[key] += 1

    return {
        "total_cases": len(cases),
        "phase_distribution": dict(Counter(c.get("phase", "?") for c in cases)),
        "error_type_distribution": dict(Counter(c.get("error_type", "?") for c in cases)),
        "root_cause_distribution": dict(Counter(c.get("root_cause", "?") for c in cases)),
        "top_tags": tag_counter.most_common(20),
        "top_patterns": pattern_counter.most_common(10),
        "lessons_by_phase": dict(lessons_by_phase),
        "cases_with_lesson": sum(len(v) for v in lessons_by_phase.values()),
        "cases_without_lesson": len(cases) - sum(len(v) for v in lessons_by_phase.values()),
    }


def generate_skill_suggestions(
    phase: str,
) -> dict[str, Any]:
    """为指定 Phase 生成 skill 规则补充建议.

    自动合并 lesson_inference 推断的 lesson，提升学习信号覆盖率。

    Returns:
        {
            "phase": "Q01",
            "anti_rationalization_suggestions": [...],
            "red_line_suggestions": [...],
            "error_pattern_updates": [...],
            "summary": "..."
        }
    """
    from qualix.tracking.lesson_inference import get_case_with_inferred_lesson

    raw_cases = load_cases_by_phase(phase, exclude_holdout=True)
    if not raw_cases:
        return {"phase": phase, "anti_rationalization_suggestions": [], "red_line_suggestions": [], "error_pattern_updates": [], "summary": "No cases found"}

    # 合并推断的 lesson
    cases = [get_case_with_inferred_lesson(c) for c in raw_cases]

    # 只分析有 lesson 的 case（含推断的）
    cases_with_lesson = [c for c in cases if c.get("lesson", "").strip()]

    anti_rat: list[dict[str, str]] = []
    red_lines: list[dict[str, str]] = []
    error_patterns: list[dict[str, str]] = []

    for c in cases_with_lesson:
        lesson = c["lesson"].strip()
        title = c.get("title", "")[:60]
        error_type = c.get("error_type", "")
        root_cause = c.get("root_cause", "")
        case_id = c.get("case_id", "")

        # 生成 Anti-Rationalization 条目
        template = _FAILURE_PATTERN_TEMPLATES.get(error_type, {})
        if template.get("anti_rationalization"):
            anti_rat.append({
                "source_case": case_id,
                "excuse": _infer_excuse(title, error_type, lesson),
                "rebuttal": lesson,
                "error_type": error_type,
            })

        # 生成红线规则建议
        if error_type in ("FN", "WRONG") and root_cause == "SKILL_RULE":
            red_lines.append({
                "source_case": case_id,
                "rule": lesson,
                "severity": "FAIL" if c.get("severity") in ("critical", "high") else "WARNING",
                "action": _ROOT_CAUSE_ACTIONS.get(root_cause, ""),
            })

        # 生成已知错误模式
        error_patterns.append({
            "source_case": case_id,
            "pattern": title,
            "error_type": error_type,
            "lesson": lesson,
        })

    # 去重（相似 lesson 合并）
    anti_rat = _deduplicate_suggestions(anti_rat, "rebuttal")
    red_lines = _deduplicate_suggestions(red_lines, "rule")

    # 分析无 lesson 的 case，找出高频失败模式
    cases_without_lesson = [c for c in cases if not c.get("lesson", "").strip()]
    unlabeled_patterns: Counter = Counter()
    for c in cases_without_lesson:
        # 从 title 和 tags 提取模式
        for tag in c.get("tags", []):
            if not tag.startswith("auto-generated") and not tag.startswith("project:"):
                unlabeled_patterns[tag] += 1

    return {
        "phase": phase,
        "anti_rationalization_suggestions": anti_rat[:10],
        "red_line_suggestions": red_lines[:10],
        "error_pattern_updates": error_patterns[:15],
        "unlabeled_high_freq_tags": unlabeled_patterns.most_common(10),
        "summary": (
            f"Phase {phase}: {len(cases)} cases, {len(cases_with_lesson)} with lessons. "
            f"Generated {len(anti_rat)} anti-rationalization, {len(red_lines)} red-line suggestions."
        ),
    }


def write_skill_suggestions(
    output_dir: Path,
    project_id: str,
    phase: str,
) -> Path | None:
    """生成 skill 补充建议并写入文件.

    Returns:
        写入的文件路径
    """
    suggestions = generate_skill_suggestions(phase)
    if not suggestions["anti_rationalization_suggestions"] and not suggestions["red_line_suggestions"]:
        return None

    suggestions_dir = output_dir / project_id / "_skill_factory"
    suggestions_dir.mkdir(parents=True, exist_ok=True)
    md_path = suggestions_dir / f"_skill_suggestions_{phase}.md"
    md_path.write_text(_render_suggestions_md(suggestions), encoding="utf-8")

    log.info("Skill Factory: %s", suggestions["summary"])
    return md_path


def write_all_skill_suggestions(output_dir: Path, project_id: str) -> list[Path]:
    """为所有 Phase 生成 skill 补充建议."""
    from qualix.core.phase_registry import PHASE_ORDER

    paths: list[Path] = []
    for phase in PHASE_ORDER:
        path = write_skill_suggestions(output_dir, project_id, phase)
        if path:
            paths.append(path)
    return paths


def _infer_excuse(title: str, error_type: str, lesson: str) -> str:
    """从失败标题和类型推断常见借口."""
    if error_type == "FN":
        if "覆盖" in title or "缺失" in title or "未覆盖" in title:
            return "这个场景不太重要，不需要覆盖"
        if "断言" in title or "assert" in title.lower():
            return "现有的断言已经够了"
        if "异常" in title or "分支" in title:
            return "异常路径不太可能触发"
        if "并发" in title or "幂等" in title:
            return "并发场景很少发生"
        return "这个应该没问题"
    if error_type == "FP":
        return "这看起来像是一个问题"
    if error_type == "WRONG":
        if "状态" in title:
            return "状态机建模看起来是对的"
        if "detail" in title.lower() or "细节" in title:
            return "这个描述已经够详细了"
        return "我的判断应该是正确的"
    return "这个不需要特别处理"


def _deduplicate_suggestions(
    items: list[dict[str, str]],
    key: str,
    similarity_threshold: int = 20,
) -> list[dict[str, str]]:
    """去重相似的建议（基于 key 字段的前 N 个字符）."""
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        fingerprint = item.get(key, "")[:similarity_threshold]
        if fingerprint not in seen:
            seen.add(fingerprint)
            result.append(item)
    return result


def _render_suggestions_md(suggestions: dict[str, Any]) -> str:
    """渲染建议为 Markdown."""
    lines = [
        f"# Skill Factory — Phase {suggestions['phase']} 规则补充建议",
        "",
        f"> {suggestions['summary']}",
        "> **注意：以下建议由 Skill Factory 自动生成，必须经过人工 review 后才能合入 skill 文件。**",
        "",
    ]

    # Anti-Rationalization
    anti_rat = suggestions.get("anti_rationalization_suggestions", [])
    if anti_rat:
        lines.append("## 建议新增的 Anti-Rationalization 条目")
        lines.append("")
        lines.append("| 常见借口 | 为什么不能接受 | 来源 Case |")
        lines.append("|---------|--------------|----------|")
        for item in anti_rat:
            lines.append(f"| \"{item['excuse']}\" | {item['rebuttal'][:80]} | `{item['source_case']}` |")
        lines.append("")

    # 红线规则
    red_lines = suggestions.get("red_line_suggestions", [])
    if red_lines:
        lines.append("## 建议新增的红线规则")
        lines.append("")
        for item in red_lines:
            lines.append(f"- **[{item['severity']}]** {item['rule'][:100]}")
            lines.append(f"  - 来源: `{item['source_case']}` | 修复方向: {item['action']}")
        lines.append("")

    # 已知错误模式
    patterns = suggestions.get("error_pattern_updates", [])
    if patterns:
        lines.append("## 已知错误模式（建议更新到 skill 的「已知错误模式」节）")
        lines.append("")
        for item in patterns:
            lines.append(f"- **[{item['error_type']}]** {item['pattern'][:60]}")
            lines.append(f"  - 教训: {item['lesson'][:100]}")
        lines.append("")

    # 未标注的高频 tag
    unlabeled = suggestions.get("unlabeled_high_freq_tags", [])
    if unlabeled:
        lines.append("## 未标注 lesson 的高频失败标签（建议人工分析后补充 lesson）")
        lines.append("")
        for tag, count in unlabeled:
            lines.append(f"- `{tag}`: {count} 次")
        lines.append("")

    return "\n".join(lines)
