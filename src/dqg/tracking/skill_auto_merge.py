"""Skill Auto-Merge：高置信度规则自动合入 SKILL.md + holdout 验证 + hints 写入.

从 skill_reflector.py 拆分，处理自动合入逻辑和 hints/suggestion 文件写入。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dqg.constants import PHASE_DIR_MAP
from dqg.log import get_logger

log = get_logger(__name__)


def apply_to_skill_file(skill_path: str, suggested_changes: list[str]) -> bool:
    """Parse SKILL.md and append new rules to the appropriate section.

    Returns True if content was successfully modified.
    """
    path = Path(skill_path)
    if not path.exists():
        return False

    if not suggested_changes:
        return False

    rule_text = suggested_changes[0]
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")
    inserted = False

    # Try to append to Anti-Rationalization table
    for i, line in enumerate(lines):
        if "Anti-Rationalization" in line:
            j = i + 1
            while j < len(lines) and (lines[j].startswith("|") or lines[j].strip() == ""):
                j += 1
            entry = f'| "{rule_text[:60]}" | {rule_text} |'
            lines.insert(j, entry)
            inserted = True
            break

    if not inserted:
        # Fallback: append to 红线规则 section
        for i, line in enumerate(lines):
            if "红线规则" in line or "禁止事项" in line:
                j = i + 1
                while j < len(lines) and (lines[j].strip().startswith("-") or lines[j].strip() == ""):
                    j += 1
                lines.insert(j, f"- {rule_text}")
                inserted = True
                break

    if not inserted:
        lines.append(f"\n## Auto-merged Rules\n\n- {rule_text}")
        inserted = True

    path.write_text("\n".join(lines), encoding="utf-8")
    return True


def verify_with_holdout(phase: str) -> bool:
    """Run holdout validation after auto-merge. Returns True if safe."""
    from dqg.constants import SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD
    from dqg.quality.eval_holdout import validate_against_holdout

    try:
        result = validate_against_holdout(phase)
        if result.get("overfitting_signal"):
            log.warning(
                "Holdout overfitting detected for %s: coverage_gap=%.2f",
                phase,
                result.get("coverage_gap", 0),
            )
            return False
        gap = result.get("coverage_gap", 0)
        if gap > SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD:
            log.warning(
                "Holdout coverage gap %.2f exceeds threshold %.2f for %s",
                gap,
                SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD,
                phase,
            )
            return False
        return True
    except Exception as e:
        log.warning("Holdout validation failed for %s: %s, allowing merge", phase, e)
        return True  # Fail-open: if holdout infra broken, don't block evolution


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
