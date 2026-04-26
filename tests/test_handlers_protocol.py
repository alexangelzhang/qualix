# tests/test_handlers_protocol.py
"""Tests for protocol compliance finalize handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock


def _make_ctx(tmp_path, phase_id="Q07"):
    """Create minimal ExecutionContext mock."""
    ctx = MagicMock()
    ctx.output_dir = tmp_path
    ctx.project_id = "test"
    ctx.phase_id = phase_id
    ctx.internal_dir = tmp_path / "test" / phase_id / "_internal"
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    ctx.shared = {}
    return ctx


def _make_result():
    result = MagicMock()
    result.errors = []
    result.warnings = []
    return result


def test_protocol_compliance_passes_when_all_covered(tmp_path):
    """All checklist items mentioned in judge result → no BLOCKED errors."""
    from dqg.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()

    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [
            {"description": "finding 有具体文件:行号证据"},
            {"description": "REQ/BR/SE 在代码中的实现完整"},
            {"description": "调用链追踪 Controller→Service→Domain→Gateway"},
            {"description": "blast radius 内的 callers 已评估"},
            {"description": "严重级别分级合理"},
        ],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    assert not any("BLOCKED" in str(e) for e in result.errors)
    assert not any("WARNING" in str(w) for w in result.warnings if "protocol_compliance" in str(w))


def test_protocol_compliance_warns_when_checklist_uncovered(tmp_path):
    """Missing checklist items → WARNING (not BLOCKED, keyword fuzzy match too imprecise)."""
    from dqg.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()

    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [{"description": "finding 有证据"}],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    assert len(result.errors) == 0  # no BLOCKED
    warnings = [w for w in result.warnings if "protocol_compliance" in str(w)]
    assert len(warnings) > 0


def test_protocol_compliance_skips_unknown_phase(tmp_path):
    """Unknown phase → no errors, no warnings."""
    from dqg.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q99")
    result = _make_result()
    handle_protocol_compliance(ctx, result)
    assert len(result.errors) == 0


def test_protocol_compliance_warns_on_zero_dynamic_genes(tmp_path):
    """No dynamic genes → WARNING (SOFT, not BLOCKED)."""
    from dqg.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()

    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [
            {"description": "finding 有具体文件:行号证据"},
            {"description": "REQ/BR/SE 在代码中的实现完整"},
            {"description": "调用链追踪 Controller→Service→Domain→Gateway"},
            {"description": "blast radius 内的 callers 已评估"},
            {"description": "严重级别分级合理"},
        ],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    warnings = [w for w in result.warnings if "dynamic" in str(w).lower() or "gene" in str(w).lower()]
    assert len(warnings) >= 1
