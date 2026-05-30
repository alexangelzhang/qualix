"""覆盖超集 gate：重跑时当前版本的被测方法集合必须是前一版本的超集."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.runtime.events import EventType

from .handler_utils import async_write_json as _async_write_json
from .handler_utils import emit_handler_event as _emit_handler

if TYPE_CHECKING:
    from qualix.runtime.execution_context import ExecutionContext
    from qualix.runtime.result import PhaseResult


def handle_superset_gate(ctx: ExecutionContext, result: PhaseResult) -> None:
    """覆盖超集检测：重跑时当前版本的被测方法集合必须是前一版本的超集."""
    from qualix.json_utils import load_json

    archive_root = ctx.phase_root / "_archive"
    if not archive_root.exists():
        return

    ver_dirs = sorted(
        (d for d in archive_root.iterdir() if d.is_dir() and d.name.startswith("v")),
        key=lambda d: d.name,
    )
    if not ver_dirs:
        return

    prev_path = ver_dirs[-1] / "phase_b_structured.json"
    if not prev_path.exists():
        return

    prev_data = load_json(prev_path)
    if not prev_data:
        return
    prev_tcs = prev_data.get("test_cases", prev_data.get("eut_items", []))
    prev_coverage = {(tc.get("class_under_test", ""), tc.get("method", "")) for tc in prev_tcs}
    prev_coverage.discard(("", ""))

    curr_path = ctx.phase_root / "phase_b_structured.json"
    if not curr_path.exists():
        return
    curr_data = load_json(curr_path)
    if not curr_data:
        return
    curr_tcs = curr_data.get("test_cases", curr_data.get("eut_items", []))
    curr_coverage = {(tc.get("class_under_test", ""), tc.get("method", "")) for tc in curr_tcs}
    curr_coverage.discard(("", ""))

    regressions = prev_coverage - curr_coverage

    if regressions:
        result.add_error(
            f"BLOCKED: 覆盖回退: 当前版本丢失了 {len(regressions)} 个被测方法 "
            f"(前版本 {len(prev_coverage)} → 当前 {len(curr_coverage)})"
        )
        for cls, method in sorted(regressions)[:5]:
            result.add_error(f"  REGRESSION: {cls}.{method}")
        if len(regressions) > 5:
            result.add_error(f"  ... 及另外 {len(regressions) - 5} 个")
        _emit_handler(
            ctx,
            EventType.SUPERSET_REGRESSION,
            f"Coverage regression: {len(regressions)} methods lost",
            regressions=len(regressions),
            prev_count=len(prev_coverage),
            curr_count=len(curr_coverage),
        )

    check_result = {
        "prev_version": ver_dirs[-1].name,
        "prev_coverage_count": len(prev_coverage),
        "curr_coverage_count": len(curr_coverage),
        "new_methods": len(curr_coverage - prev_coverage),
        "regressions": [{"class": c, "method": m} for c, m in sorted(regressions)],
        "blocked": bool(regressions),
    }
    _async_write_json(ctx.internal_dir / "_superset_check.json", check_result)
