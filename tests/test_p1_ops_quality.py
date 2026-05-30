"""Tests for P1 ops quality improvements."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Task 1: --strict-profile-context
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, phase_id: str = "Q01", strict: bool = False):
    from qualix.runtime.execution_context import ExecutionContext

    ctx = ExecutionContext(
        output_dir=tmp_path,
        project_id="test",
        phase_id=phase_id,
        strict_profile_context=strict,
    )
    ctx.phase_root = tmp_path / "test" / phase_id
    ctx.phase_root.mkdir(parents=True, exist_ok=True)
    ctx.internal_dir = ctx.phase_root / "_internal"
    ctx.internal_dir.mkdir()
    return ctx


def _make_result():
    r = MagicMock()
    r.errors = []
    r.warnings = []
    r.add_error = lambda msg: r.errors.append(msg)
    r.add_warning = lambda msg: r.warnings.append(msg)
    return r


def test_strict_profile_context_blocks_when_section_missing(tmp_path):
    """--strict-profile-context 且报告缺 PROFILE_CONTEXT → BLOCKED."""
    from qualix.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=True)
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert any("BLOCKED" in e for e in result.errors), "严格模式应产生 BLOCKED error"
    assert not any("BLOCKED" in w for w in result.warnings), "不应在 warning 里出现 BLOCKED"


def test_non_strict_profile_context_warns_only(tmp_path):
    """非严格模式下缺 PROFILE_CONTEXT → 仅 WARNING，不 BLOCKED。"""
    from qualix.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=False)
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert result.errors == [], "非严格模式不应有 BLOCKED error"
    assert len(result.warnings) > 0, "非严格模式应有 WARNING"


# ---------------------------------------------------------------------------
# Task 2: Task store CLI
# ---------------------------------------------------------------------------


def test_cmd_task_list_returns_records(tmp_path):
    """cmd_task list 应返回已有 task runs."""
    from qualix.commands.task_cmd import cmd_task
    from qualix.runtime.task_store import complete_task_run, create_task_run

    tid1 = create_task_run(tmp_path, task_type="adaptive", project_id="p1", phase_id="Q01")
    complete_task_run(tmp_path, tid1, status="completed", result_summary="done")
    create_task_run(tmp_path, task_type="adaptive", project_id="p1", phase_id="Q05")

    args = type(
        "A",
        (),
        {
            "project_id": "p1",
            "task_action": "list",
            "task_id": None,
            "status": "all",
            "limit": 20,
            "json": False,
        },
    )()
    rc = cmd_task(args, tmp_path)
    assert rc == 0


def test_cmd_task_resume_no_tasks(tmp_path):
    """cmd_task resume 无可恢复 task 时应优雅返回（非 crash）."""
    from qualix.commands.task_cmd import cmd_task

    args = type(
        "A",
        (),
        {
            "project_id": "p1",
            "task_action": "resume",
            "task_id": None,
            "status": "all",
            "limit": 20,
            "json": False,
        },
    )()
    rc = cmd_task(args, tmp_path)
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# Task 3: 四类运营口径
# ---------------------------------------------------------------------------


def test_phase_run_record_has_force_approved_field():
    """PhaseRunRecord 应有 force_approved 字段，默认 False。"""
    from qualix.reporting.telemetry import PhaseRunRecord

    r = PhaseRunRecord(project_id="p1", phase_id="Q01", phase_name="需求分析", action="approve", status="approved")
    assert hasattr(r, "force_approved"), "PhaseRunRecord 缺少 force_approved 字段"
    assert r.force_approved is False


def test_closure_hours_computed(tmp_path):
    """_project_metrics 应计算 avg_closure_hours。"""
    from datetime import datetime, timedelta

    from qualix.reporting.observability import _project_metrics
    from qualix.reporting.telemetry import PhaseRunRecord

    now = datetime.now(UTC)
    records = [
        PhaseRunRecord(
            project_id="p1",
            phase_id="Q01",
            phase_name="x",
            action="execute",
            status="ok",
            timestamp=(now - timedelta(hours=3)).isoformat(),
        ),
        PhaseRunRecord(
            project_id="p1",
            phase_id="Q01",
            phase_name="x",
            action="approve",
            status="approved",
            timestamp=now.isoformat(),
            force_approved=False,
        ),
    ]
    metrics = _project_metrics(tmp_path, "p1", records)
    assert "avg_closure_hours" in metrics
    assert metrics["avg_closure_hours"] >= 2.9


def test_force_approve_rate_computed(tmp_path):
    """force_approve_rate 应等于 force_approved / total_approved。"""
    from qualix.reporting.observability import _project_metrics
    from qualix.reporting.telemetry import PhaseRunRecord

    records = [
        PhaseRunRecord(
            project_id="p1", phase_id="Q01", phase_name="x", action="approve", status="approved", force_approved=True
        ),
        PhaseRunRecord(
            project_id="p1", phase_id="Q01", phase_name="x", action="approve", status="approved", force_approved=False
        ),
    ]
    metrics = _project_metrics(tmp_path, "p1", records)
    assert metrics["force_approve_rate"] == 0.5


def test_generate_report_includes_guard_precision(tmp_path):
    """generate_report 的返回 payload 应含 guard_precision 字段。"""
    from datetime import date

    from qualix.reporting.observability import generate_report

    try:
        payload, _, _ = generate_report(tmp_path, period_name="daily", anchor=date.today())
        assert "guard_precision" in payload
    except Exception as e:
        raise AssertionError(f"generate_report 抛出异常: {e}") from e
