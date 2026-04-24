"""cmd_startup 快速路径：绕过 pydantic，直接读 state.json dict.

startup 只需要读取状态 + 构建菜单 JSON，不需要 pydantic 模型验证。
将 import 时间从 ~0.6s 降到 ~0.02s。
"""

from __future__ import annotations

import sys
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from dqg.constants import LEGACY_PHASE_ID_MAP
from dqg.core.phase_registry import PHASE_DEFS, PHASE_ORDER
from dqg.json_utils import dump_json_str, load_json_strict
from dqg.log import get_logger

log = get_logger(__name__)


STATUS_ICONS: Final = MappingProxyType(
    {
        "not_started": "⬜",
        "in_progress": "🔶",
        "pending_review": "🔍",
        "approved": "✅",
        "skipped": "⏭",
    }
)

_DONE_STATUSES: Final = frozenset({"approved", "skipped"})


def _load_state_dict(output_dir: Path, project_id: str) -> dict:
    """轻量加载 state.json 为 dict，不走 pydantic 验证."""
    path = output_dir / project_id / "state.json"
    if path.exists():
        data = load_json_strict(path)
        # 向后兼容：迁移旧 Phase ID
        phases = data.get("phases", {})
        for old_id, new_id in LEGACY_PHASE_ID_MAP.items():
            if old_id in phases and new_id not in phases:
                phases[new_id] = phases.pop(old_id)
        data["phases"] = phases
        # 确保所有 Phase 都有条目
        for phase_id in PHASE_ORDER:
            if phase_id not in phases:
                phases[phase_id] = {"status": "not_started"}
        return data
    return {
        "project_id": project_id,
        "profile_id": "java-ddd-tmf",
        "phases": {pid: {"status": "not_started"} for pid in PHASE_ORDER},
    }


def _check_gate(phases: dict, phase_id: str) -> bool:
    """检查 Phase 前置依赖是否满足（dict 版本）."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return False
    for dep_id in phase_def["depends_on"]:
        dep = phases.get(dep_id, {})
        if dep.get("status") not in _DONE_STATUSES:
            return False
    return phases.get(phase_id, {}).get("status") != "approved"


def _get_available(phases: dict) -> list[str]:
    """获取可执行的 Phase 列表（dict 版本）."""
    available = []
    for phase_id in PHASE_ORDER:
        status = phases.get(phase_id, {}).get("status", "not_started")
        if status in _DONE_STATUSES:
            continue
        if _check_gate(phases, phase_id):
            available.append(phase_id)
    return available


def _get_parallel_groups(phases: dict, available: list[str]) -> list[list[str]]:
    """获取可并行执行的 Phase 分组（dict 版本）."""
    if not available:
        return []
    groups: list[list[str]] = []
    used: set[str] = set()
    for phase_id in available:
        if phase_id in used:
            continue
        phase_def = PHASE_DEFS[phase_id]
        group = [phase_id]
        used.add(phase_id)
        for parallel_id in phase_def["parallel_with"]:
            if parallel_id in available and parallel_id not in used:
                group.append(parallel_id)
                used.add(parallel_id)
        groups.append(group)
    return groups


def cmd_startup(args, output_dir: Path) -> int:
    """快速 startup：直接读 dict，不走 pydantic."""
    data = _load_state_dict(output_dir, args.project_id)
    phases = data["phases"]
    available = _get_available(phases)
    groups = _get_parallel_groups(phases, available)

    menu_items = []
    for phase_id in PHASE_ORDER:
        ps = phases.get(phase_id, {})
        phase_def = PHASE_DEFS[phase_id]
        status = ps.get("status", "not_started")
        duration = ps.get("duration_seconds")
        menu_items.append(
            {
                "phase_id": phase_id,
                "name": phase_def["name"],
                "status": status,
                "icon": STATUS_ICONS.get(status, "?"),
                "available": phase_id in available,
                "skippable": phase_def.get("skippable", False),
                "skip_condition": phase_def.get("skip_condition", None),
                "skill": phase_def["skill"],
                "required_inputs": phase_def.get("required_inputs", []),
                "optional_inputs": phase_def.get("optional_inputs", []),
                "deliverables": phase_def.get("deliverables", []),
                "approve_checklist": phase_def.get("approve_checklist", []),
                "duration": f"{duration:.0f}s" if duration else None,
                "comment": ps.get("comment") or None,
            }
        )

    done = sum(1 for pid in PHASE_ORDER if phases.get(pid, {}).get("status") in _DONE_STATUSES)
    total = len(PHASE_ORDER)
    total_duration = sum(phases.get(pid, {}).get("duration_seconds") or 0.0 for pid in PHASE_ORDER)
    judge_scores = [
        phases[pid]["judge_score"] for pid in PHASE_ORDER if phases.get(pid, {}).get("judge_score") is not None
    ]
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None

    print(
        dump_json_str(
            {
                "project_id": args.project_id,
                "profile_id": data.get("profile_id", "java-ddd-tmf"),
                "all_done": done == total,
                "progress": {
                    "done": done,
                    "total": total,
                    "percent": int(done / total * 100) if total else 0,
                    "total_duration_seconds": round(total_duration, 1),
                    "avg_judge_score": round(avg_judge, 2) if avg_judge else None,
                },
                "menu": menu_items,
                "next_groups": [{"phases": g, "parallel": len(g) > 1} for g in groups],
                "shortcuts": {
                    "v": "详情模式（展示每个 Phase 的交付物和校验结果）",
                    "g": "全局进度（展示进度/耗时/质量分汇总）",
                    "数字": "选择要执行的阶段编号",
                },
            }
        )
    )

    # Session orientation：轻量版，不走 pydantic
    _print_orientation(output_dir, args.project_id, data, phases)

    return 0


def _print_orientation(output_dir: Path, project_id: str, data: dict, phases: dict) -> None:
    """轻量 orientation 输出到 stderr，不导入 state_machine/pydantic."""
    try:
        lines = [f"# Session Startup — {project_id}"]
        lines.append(f"Profile: {data.get('profile_id', 'unknown')}")
        lines.append("")

        # 进度概览
        completed = sum(1 for pid in PHASE_ORDER if phases.get(pid, {}).get("status") in _DONE_STATUSES)
        lines.append(f"## Progress: {completed}/{len(PHASE_ORDER)} phases completed")
        lines.append("")
        for pid in PHASE_ORDER:
            ps = phases.get(pid, {})
            status = ps.get("status", "not_started")
            icon = {
                "approved": "+",
                "skipped": "~",
                "in_progress": ">",
                "pending_review": "?",
                "not_started": " ",
            }.get(status, " ")
            name = PHASE_DEFS[pid]["name"]
            score = ps.get("judge_score")
            score_str = f" (Judge: {score:.1f})" if score is not None else ""
            lines.append(f"  [{icon}] {pid} {name}: {status}{score_str}")
        lines.append("")

        # 最近活跃 Phase 的 reasoning log 摘要
        last_phase = _find_last_active(phases)
        if last_phase:
            phase_def = PHASE_DEFS.get(last_phase)
            if phase_def:
                pdir = output_dir / project_id / phase_def["dir_suffix"]
                int_dir = pdir / "_internal"
                # Phase progress
                progress_path = int_dir / "_progress.json"
                if progress_path.exists():
                    progress = load_json_strict(progress_path)
                    lines.append(f"## Last Phase: {last_phase} ({phase_def['name']})")
                    counts = progress.get("artifact_counts", {})
                    if counts:
                        lines.append(f"  Artifacts: {counts}")
                    lines.append("")
                # Reasoning excerpt
                reasoning_path = int_dir / "_reasoning_log.md"
                if not reasoning_path.exists():
                    reasoning_path = pdir / "_reasoning_log.md"
                if reasoning_path.exists():
                    text = reasoning_path.read_text(encoding="utf-8").strip()
                    excerpt = text[:500] + ("..." if len(text) > 500 else "")
                    lines.append("## Last Reasoning (excerpt)")
                    lines.append(excerpt)
                    lines.append("")

        # 下一步
        actions = []
        for pid in PHASE_ORDER:
            status = phases.get(pid, {}).get("status", "not_started")
            if status == "pending_review":
                actions.append(f"Review and approve Phase {pid}({PHASE_DEFS[pid]['name']})")
        if not actions:
            all_done = all(phases.get(pid, {}).get("status") in _DONE_STATUSES for pid in PHASE_ORDER)
            if all_done:
                actions.append("All phases completed. Ready for final project review.")
        if actions:
            lines.append("## Next Actions")
            for a in actions:
                lines.append(f"  - {a}")

        print("\n".join(lines), file=sys.stderr)
    except Exception:
        log.debug("Startup orientation print failed", exc_info=True)


def _find_last_active(phases: dict) -> str | None:
    """找到最近活跃的 Phase（按时间倒序）."""
    candidates = []
    for pid in PHASE_ORDER:
        ps = phases.get(pid, {})
        ts = ps.get("finished_at") or ps.get("started_at")
        if ts and ps.get("status") != "not_started":
            candidates.append((ts, pid))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]
