"""自动 Bug Case 生成：从 validation errors 和 judge results 提取."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from dqg.constants import CASES_DIR, PHASE_DIR_MAP, SKILL_FILE_MAP
from dqg.json_utils import save_json


# Judge 维度 → error_type 映射
_JUDGE_DIM_TO_ERROR_TYPE: Final = MappingProxyType({
    "faithfulness": "FP",
    "completeness": "FN",
    "se_explicitness": "FN",
    "gap_detection": "FN",
    "coverage_accuracy": "WRONG",
    "missing_detection": "FN",
    "reverse_audit": "FN",
    "issue_validity": "FP",
    "failure_mode_coverage": "FN",
    "exception_coverage": "FN",
    "audit_accuracy": "WRONG",
    "wrong_target_detection": "FN",
    "exception_branch": "FN",
})


def auto_generate_bug_case(
    project_id: str,
    phase_id: str,
    validation_errors: list[str],
    structured_output: dict[str, Any] | None = None,
    output_base: Path | None = None,
) -> list[dict[str, Any]]:
    """从 validation errors 自动生成 bug case."""
    if not validation_errors:
        return []

    base = output_base or Path(CASES_DIR)
    phase_dir = PHASE_DIR_MAP.get(phase_id)
    if not phase_dir:
        return []

    generated: list[dict[str, Any]] = []
    now = datetime.now()
    ts = now.strftime("%Y%m%d%H%M%S")
    today = now.strftime("%Y-%m-%d")
    now_iso = now.isoformat()

    for i, error in enumerate(validation_errors):
        case_id = f"AUTO-{phase_dir}-{ts}-{i:02d}"
        error_type, root_cause, fix_target = _classify_validation_error(error, phase_id)

        case = {
            "case_id": case_id,
            "phase": phase_id,
            "error_type": error_type,
            "severity": "medium",
            "title": error[:100],
            "root_cause": root_cause,
            "fix_target": fix_target,
            "tags": ["auto-generated", f"project:{project_id}"],
            "created_at": today,
            "status": "open",
            "source": {
                "project_id": project_id,
                "auto_generated": True,
                "validation_error": error,
            },
            "expected": {"content": "（需人工确认）"},
            "actual": {"content": error},
            "lesson": "",
        }

        case_dir = base / phase_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        save_json(case_dir / "case.json", case)
        (case_dir / "input.md").write_text(
            f"# 自动生成的 Bug Case\n\n"
            f"- 项目: {project_id}\n"
            f"- Phase: {phase_id}\n"
            f"- 时间: {now_iso}\n\n"
            f"## Validation Error\n\n{error}\n",
            encoding="utf-8",
        )
        generated.append(case)

    return generated


def _classify_validation_error(error: str, phase_id: str) -> tuple[str, str, str]:
    """根据 validation error 内容自动归因."""
    err_lower = error.lower()
    default_target = SKILL_FILE_MAP.get(phase_id, "")

    if "validation error" in err_lower or "field required" in err_lower:
        return "WRONG", "SCHEMA", f"src/dqg/schemas/phase_{phase_id.lower().replace('.', '')}.py"

    if "引用了" in error and "不存在" in error:
        return "WRONG", "SKILL_RULE", default_target

    return "FN", "SKILL_RULE", default_target


def suggest_prompt_fix(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    """根据 bug cases 生成 prompt 修改建议."""
    suggestions: list[dict[str, str]] = []
    by_target: dict[str, list[dict]] = defaultdict(list)

    for c in cases:
        if c.get("status") != "open":
            continue
        target = c.get("fix_target", "")
        if target:
            by_target[target].append(c)

    for target, target_cases in by_target.items():
        if not target.endswith(".md"):
            continue

        lessons = [c.get("lesson", "") for c in target_cases if c.get("lesson")]
        categories = list({c.get("source", {}).get("category2", "") for c in target_cases if c.get("source", {}).get("category2")})

        suggestion = {
            "file": target,
            "case_count": len(target_cases),
            "action": f"在 {target} 中补充以下规则:",
            "rules": [],
        }

        if lessons:
            suggestion["rules"] = lessons[:5]
        if categories:
            suggestion["categories"] = categories

        suggestions.append(suggestion)

    return suggestions


def extract_judge_cases(
    project_id: str,
    phase_id: str,
    judge_result: dict[str, Any],
    output_base: Path | None = None,
    min_score_to_extract: float = 4.0,
) -> list[dict[str, Any]]:
    """从 judge_result 的 dimension issues 提取 bug case 写入 failure-library."""
    phase_dir = PHASE_DIR_MAP.get(phase_id)
    if not phase_dir:
        return []

    base = output_base or Path(CASES_DIR)
    now = datetime.now()
    ts = now.strftime("%Y%m%d%H%M%S")
    today = now.strftime("%Y-%m-%d")
    now_iso = now.isoformat()
    generated: list[dict[str, Any]] = []

    for dim in judge_result.get("dimensions", []):
        dim_id = dim.get("id", "")
        score = dim.get("score", 5)
        max_score = dim.get("max_score", 5)
        issues = dim.get("issues", [])

        if score >= min_score_to_extract or not issues:
            continue

        for i, issue in enumerate(issues):
            description = issue.get("description", "")
            evidence = issue.get("evidence", "")
            issue_type = issue.get("type", "FN")

            if not description:
                continue

            error_type = _JUDGE_DIM_TO_ERROR_TYPE.get(dim_id, issue_type)
            case_id = f"JUDGE-{phase_dir}-{ts}-{dim_id}-{i:02d}"

            case = {
                "case_id": case_id,
                "phase": phase_id,
                "error_type": error_type,
                "severity": "high" if score <= 2 else "medium",
                "title": description[:100],
                "root_cause": "SKILL_RULE",
                "fix_target": SKILL_FILE_MAP.get(phase_id, ""),
                "tags": ["judge-extracted", f"dim:{dim_id}", f"project:{project_id}"],
                "created_at": today,
                "status": "open",
                "source": {
                    "project_id": project_id,
                    "judge_extracted": True,
                    "dimension": dim_id,
                    "dim_score": score,
                    "dim_max_score": max_score,
                },
                "expected": {"content": "（需人工补充期望行为）"},
                "actual": {"content": description},
                "lesson": description,
            }

            case_dir = base / phase_dir / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            save_json(case_dir / "case.json", case)
            input_md = (
                f"# Judge 提取的 Bug Case\n\n"
                f"- 项目: {project_id}\n"
                f"- Phase: {phase_id}\n"
                f"- 维度: {dim_id} ({score}/{max_score})\n"
                f"- 时间: {now_iso}\n\n"
                f"## 问题描述\n\n{description}\n\n"
            )
            if evidence:
                input_md += f"## 证据\n\n{evidence}\n"
            (case_dir / "input.md").write_text(input_md, encoding="utf-8")
            generated.append(case)

    return generated
