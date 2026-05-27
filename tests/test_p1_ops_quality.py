"""Tests for P1 ops quality improvements."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Task 1: --strict-profile-context
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, phase_id: str = "Q01", strict: bool = False):
    from dqg.runtime.execution_context import ExecutionContext

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
    r.add_warning = lambda msg: r.warnings.append(msg)
    return r


def test_strict_profile_context_blocks_when_section_missing(tmp_path):
    """--strict-profile-context 且报告缺 PROFILE_CONTEXT → BLOCKED."""
    from dqg.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=True)
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert any("BLOCKED" in e for e in result.errors), "严格模式应产生 BLOCKED error"
    assert not any("BLOCKED" in w for w in result.warnings), "不应在 warning 里出现 BLOCKED"


def test_non_strict_profile_context_warns_only(tmp_path):
    """非严格模式下缺 PROFILE_CONTEXT → 仅 WARNING，不 BLOCKED。"""
    from dqg.runtime.handlers.handlers_finalize import handle_profile_context_check

    ctx = _make_ctx(tmp_path, phase_id="Q01", strict=False)
    (ctx.phase_root / "phase_a_report.md").write_text("# 报告\n\n无 profile context")

    result = _make_result()
    handle_profile_context_check(ctx, result)

    assert result.errors == [], "非严格模式不应有 BLOCKED error"
    assert len(result.warnings) > 0, "非严格模式应有 WARNING"
