"""Skill Evolution：技能自进化闭环.

升级 Skill Factory 从"生成建议文件"到"进化闭环"：
1. 对比现有 skill 文件和建议，生成具体的 diff
2. 记录进化谱系（哪个 bug case 触发了哪条规则的变更）
3. 高置信度规则（3+ case 支撑）标记为"建议自动合入"

进化模式（借鉴 OpenSpace）：
- FIX：现有规则导致反复误判时修正
- DERIVED：从通用规则派生项目特化版本
- CAPTURED：从成功模式中捕获新规则（Skill Factory 已有）
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.constants import SKILL_FILE_MAP
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger
from dqg.tracking.skill_factory import generate_skill_suggestions

log = get_logger(__name__)

# 高置信度阈值：同一条建议被 N+ 个 case 支撑时标记为"建议自动合入"
HIGH_CONFIDENCE_THRESHOLD = 3


def generate_skill_diff(
    phase: str,
) -> dict[str, Any] | None:
    """对比现有 skill 文件和 Skill Factory 建议，生成具体 diff.

    Returns:
        {
            "phase": "Q01",
            "skill_file": "skills/requirement-structuring.md",
            "diffs": [
                {
                    "type": "ADD_ANTI_RAT",
                    "content": "| excuse | rebuttal |",
                    "source_cases": ["case_id1", ...],
                    "confidence": "high" | "medium",
                    "auto_merge_suggested": bool,
                }
            ],
            "evolution_type": "FIX" | "CAPTURED",
            "summary": "..."
        }
    """
    suggestions = generate_skill_suggestions(phase)
    if not suggestions:
        return None

    skill_path = _get_skill_path(phase)
    if not skill_path or not skill_path.exists():
        return None

    skill_content = skill_path.read_text(encoding="utf-8")

    diffs: list[dict[str, Any]] = []

    # 1. Anti-Rationalization diff
    existing_excuses = _extract_existing_excuses(skill_content)
    for ar in suggestions.get("anti_rationalization_suggestions", []):
        excuse = ar.get("excuse", "")
        if not _is_duplicate_excuse(excuse, existing_excuses):
            source_cases = [ar.get("source_case", "")]
            # 统计同一 excuse 被多少 case 支撑
            support_count = _count_case_support(
                ar.get("rebuttal", ""),
                suggestions.get("anti_rationalization_suggestions", []),
            )
            diffs.append({
                "type": "ADD_ANTI_RAT",
                "section": "Anti-Rationalization",
                "content": f'| "{excuse}" | {ar.get("rebuttal", "")} |',
                "source_cases": source_cases,
                "support_count": support_count,
                "confidence": "high" if support_count >= HIGH_CONFIDENCE_THRESHOLD else "medium",
                "auto_merge_suggested": support_count >= HIGH_CONFIDENCE_THRESHOLD,
            })

    # 2. 红线规则 diff
    existing_rules = _extract_existing_rules(skill_content)
    for rl in suggestions.get("red_line_suggestions", []):
        rule_text = rl.get("rule", "")
        if not _is_duplicate_rule(rule_text, existing_rules):
            diffs.append({
                "type": "ADD_RED_LINE",
                "section": "红线规则 / 禁止事项",
                "content": f'- {rule_text}',
                "source_cases": [rl.get("source_case", "")],
                "severity": rl.get("severity", "WARNING"),
                "support_count": 1,
                "confidence": "medium",
                "auto_merge_suggested": False,
            })

    if not diffs:
        return None

    # 判断进化类型
    has_fix = any(d["type"] == "ADD_RED_LINE" and d["severity"] == "FAIL" for d in diffs)
    evolution_type = "FIX" if has_fix else "CAPTURED"

    auto_count = sum(1 for d in diffs if d["auto_merge_suggested"])

    return {
        "phase": phase,
        "skill_file": str(skill_path),
        "diffs": diffs,
        "evolution_type": evolution_type,
        "total_diffs": len(diffs),
        "auto_merge_count": auto_count,
        "summary": (
            f"Phase {phase}: {len(diffs)} diffs ({auto_count} high-confidence). "
            f"Evolution type: {evolution_type}"
        ),
    }


def record_evolution(
    output_dir: Path,
    project_id: str,
    phase: str,
    diff_result: dict[str, Any],
) -> Path:
    """记录进化谱系到 SQLite 和文件.

    Returns:
        谱系文件路径
    """
    lineage_dir = output_dir / project_id / "_skill_evolution"
    lineage_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lineage_file = lineage_dir / f"evolution_{phase}_{timestamp}.json"

    lineage = {
        "phase": phase,
        "timestamp": datetime.now().isoformat(),
        "evolution_type": diff_result.get("evolution_type", "CAPTURED"),
        "skill_file": diff_result.get("skill_file", ""),
        "diffs": diff_result.get("diffs", []),
        "summary": diff_result.get("summary", ""),
    }

    save_json(lineage_file, lineage)
    log.info("Evolution recorded: %s", lineage_file)

    # 追加到谱系索引
    _append_lineage_index(lineage_dir, lineage)

    return lineage_file


def generate_evolution_report(
    output_dir: Path,
    project_id: str,
    phase: str,
) -> Path | None:
    """生成进化报告（diff + 谱系 + 合入建议）.

    Returns:
        报告文件路径
    """
    diff_result = generate_skill_diff(phase)
    if not diff_result:
        return None

    # 记录谱系
    lineage_path = record_evolution(output_dir, project_id, phase, diff_result)

    # 生成可读报告
    report_dir = output_dir / project_id / "_skill_evolution"
    report_path = report_dir / f"report_{phase}.md"
    report_path.write_text(
        _render_evolution_report(diff_result), encoding="utf-8",
    )

    log.info("Skill evolution: %s", diff_result["summary"])
    return report_path


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _get_skill_path(phase: str) -> Path | None:
    """获取 Phase 对应的 skill 文件路径."""
    skill_file = SKILL_FILE_MAP.get(phase)
    if not skill_file:
        # fallback: 从 PHASE_DEFS 获取
        from dqg.core.phase_registry import PHASE_DEFS
        phase_def = PHASE_DEFS.get(phase, {})
        skill_file = phase_def.get("skill", "")
    if not skill_file:
        return None
    path = Path(skill_file)
    return path if path.exists() else None


def _extract_existing_excuses(content: str) -> list[str]:
    """从 skill 文件中提取已有的 Anti-Rationalization 借口."""
    excuses: list[str] = []
    in_table = False
    for line in content.splitlines():
        if "Anti-Rationalization" in line:
            in_table = True
            continue
        if in_table and line.startswith("|") and "常见借口" not in line and "---" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                excuses.append(parts[1].strip('"').lower())
        if in_table and line.startswith("##") and "Anti" not in line:
            break
    return excuses


def _extract_existing_rules(content: str) -> list[str]:
    """从 skill 文件中提取已有的红线规则/禁止事项."""
    rules: list[str] = []
    in_section = False
    for line in content.splitlines():
        if "红线规则" in line or "禁止事项" in line:
            in_section = True
            continue
        if in_section and line.strip().startswith(("-", "1.", "2.", "3.")):
            rules.append(line.strip().lstrip("-0123456789. ").lower())
        if in_section and line.startswith("##") and "红线" not in line and "禁止" not in line:
            break
    return rules


def _is_duplicate_excuse(excuse: str, existing: list[str]) -> bool:
    """检查借口是否与已有的重复（模糊匹配前 15 字符）."""
    excuse_lower = excuse.lower()[:15]
    return any(excuse_lower in e or e in excuse_lower for e in existing)


def _is_duplicate_rule(rule: str, existing: list[str]) -> bool:
    """检查规则是否与已有的重复."""
    rule_lower = rule.lower()[:20]
    return any(rule_lower in r or r in rule_lower for r in existing)


def _count_case_support(rebuttal: str, all_suggestions: list[dict]) -> int:
    """统计同一 rebuttal 被多少个不同 case 支撑."""
    rebuttal_prefix = rebuttal[:30]
    return sum(
        1 for s in all_suggestions
        if s.get("rebuttal", "")[:30] == rebuttal_prefix
    )


def _append_lineage_index(lineage_dir: Path, lineage: dict[str, Any]) -> None:
    """追加到谱系索引文件."""
    index_path = lineage_dir / "lineage_index.json"
    index: list[dict] = []
    if index_path.exists():
        data = load_json(index_path)
        if isinstance(data, list):
            index = data

    index.append({
        "phase": lineage["phase"],
        "timestamp": lineage["timestamp"],
        "evolution_type": lineage["evolution_type"],
        "diff_count": len(lineage.get("diffs", [])),
        "summary": lineage["summary"],
    })

    # 只保留最近 50 条
    index = index[-50:]
    save_json(index_path, index)


def _render_evolution_report(diff_result: dict[str, Any]) -> str:
    """渲染进化报告为 Markdown."""
    lines = [
        f"# Skill Evolution Report — Phase {diff_result['phase']}",
        "",
        f"> {diff_result['summary']}",
        f"> Evolution type: **{diff_result['evolution_type']}**",
        "",
    ]

    # 高置信度（建议自动合入）
    auto_diffs = [d for d in diff_result["diffs"] if d.get("auto_merge_suggested")]
    if auto_diffs:
        lines.append("## 建议自动合入（高置信度，3+ case 支撑）")
        lines.append("")
        for d in auto_diffs:
            lines.append(f"**[{d['type']}]** → `{d['section']}`")
            lines.append(f"```")
            lines.append(d["content"])
            lines.append(f"```")
            lines.append(f"来源: {', '.join(d['source_cases'])} | 支撑: {d['support_count']} cases")
            lines.append("")

    # 中等置信度（需人工 review）
    manual_diffs = [d for d in diff_result["diffs"] if not d.get("auto_merge_suggested")]
    if manual_diffs:
        lines.append("## 需人工 Review（中等置信度）")
        lines.append("")
        for d in manual_diffs:
            lines.append(f"**[{d['type']}]** → `{d['section']}`")
            lines.append(f"```")
            lines.append(d["content"])
            lines.append(f"```")
            lines.append(f"来源: {', '.join(d['source_cases'])}")
            lines.append("")

    # 谱系信息
    lines.append("## 进化谱系")
    lines.append("")
    lines.append(f"- Skill 文件: `{diff_result['skill_file']}`")
    lines.append(f"- 总 diff 数: {diff_result['total_diffs']}")
    lines.append(f"- 自动合入建议: {diff_result['auto_merge_count']}")
    lines.append(f"- 进化类型: {diff_result['evolution_type']}")

    return "\n".join(lines)
