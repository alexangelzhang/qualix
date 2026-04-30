"""Critique Feedback: 偏好数据沉淀 + 缓存查询.

从 critique.py 拆分而来，负责：
1. persist_preference — 偏好数据沉淀为 bug case
2. load/get_cached critique/preference 结果
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.cache.llm_result_cache import get_cached_result, put_cached_result
from dqg.constants import CASES_DIR, PHASE_DIR_MAP
from dqg.constants import PREFERENCE_LOG as _PREFERENCE_LOG
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import dump_jsonl, load_json, save_json


def persist_preference(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """读取 preference 结果，沉淀有效 critique 为 bug case."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    pref_path = pd / "_preference.json"
    critique_path = pd / "_critique.json"

    if not pref_path.exists():
        return None

    try:
        preference = load_json(pref_path)
        if preference is None:
            return None

        put_cached_result(output_dir, project_id, phase_id, "preference", preference)

        log_path = base_dir / _PREFERENCE_LOG if base_dir else Path(_PREFERENCE_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_entry = {
            "project_id": project_id,
            "phase": phase_id,
            "preferred": preference.get("preferred", ""),
            "confidence": preference.get("confidence", ""),
            "timestamp": datetime.now().isoformat(),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(dump_jsonl(log_entry))

        persisted_cases: list[str] = []
        persisted_genes: list[str] = []
        capsule_id: str | None = None

        if preference.get("preferred") == "v2":
            effectiveness = preference.get("critique_effectiveness", [])
            valid_critiques = [
                e
                for e in effectiveness
                if e.get("was_valid") and e.get("should_persist") and e.get("impact") in ("high", "medium")
            ]

            # Gene/Capsule 提取
            critique_data = load_json(critique_path) if critique_path.exists() else None
            if critique_data:
                from dqg.quality.regression.gene_store import extract_genes_from_preference, save_capsule, save_genes

                effective_base = base_dir or Path(".")
                genes = extract_genes_from_preference(
                    preference,
                    critique_data,
                    phase_id,
                    project_id,
                )
                if genes:
                    persisted_genes = save_genes(effective_base, genes)
                capsule_id = save_capsule(
                    effective_base,
                    phase_id,
                    project_id,
                    critique_data,
                    preference,
                )

            if valid_critiques and critique_path.exists():
                load_json(critique_path) or {}

                cases_base = base_dir / CASES_DIR if base_dir else Path(CASES_DIR)
                phase_dir_name = PHASE_DIR_MAP.get(phase_id, "")

                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                for i, vc in enumerate(valid_critiques):
                    case_id = f"RLAIF-{phase_dir_name}-{ts}-{i:02d}"
                    case_data = {
                        "case_id": case_id,
                        "phase": phase_id,
                        "error_type": "FN",
                        "severity": vc.get("impact", "medium"),
                        "title": vc.get("critique_issue", "")[:100],
                        "root_cause": "SKILL_RULE",
                        "fix_target": phase_def.get("skill", ""),
                        "tags": ["rlaif-generated", f"project:{project_id}"],
                        "created_at": datetime.now().strftime("%Y-%m-%d"),
                        "status": "open",
                        "source": {
                            "project_id": project_id,
                            "rlaif_generated": True,
                            "preference": preference.get("preferred"),
                            "confidence": preference.get("confidence"),
                        },
                        "expected": {"content": vc.get("critique_issue", "")},
                        "actual": {"content": "原始输出未覆盖此问题"},
                        "lesson": vc.get("critique_issue", ""),
                    }

                    if phase_dir_name:
                        case_dir = cases_base / phase_dir_name / case_id
                        case_dir.mkdir(parents=True, exist_ok=True)
                        save_json(case_dir / "case.json", case_data)
                        persisted_cases.append(case_id)

        return {
            "preferred": preference.get("preferred", ""),
            "confidence": preference.get("confidence", ""),
            "persisted_cases": persisted_cases,
            "persisted_genes": persisted_genes,
            "capsule_id": capsule_id,
            "log_path": str(log_path),
        }
    except Exception:
        from dqg.log import get_logger

        get_logger(__name__).warning(
            "persist_preference failed for %s/%s",
            project_id,
            phase_id,
            exc_info=True,
        )
        return None


def load_critique_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """加载 critique 结果. 加载成功后自动写入缓存."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None
    pd = _phase_dir(output_dir, project_id, phase_def)
    result_path = pd / "_critique.json"
    if not result_path.exists():
        return None
    result = load_json(result_path)
    if result:
        put_cached_result(output_dir, project_id, phase_id, "critique", result)
    return result


def get_cached_critique_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """检查是否有缓存的 critique 结果."""
    return get_cached_result(output_dir, project_id, phase_id, "critique")


def get_cached_preference_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """检查是否有缓存的 preference 结果."""
    return get_cached_result(output_dir, project_id, phase_id, "preference")
