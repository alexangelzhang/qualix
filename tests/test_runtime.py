"""Runtime 测试：PhaseResult 结构化输出、lifecycle handler 注册和执行."""

from __future__ import annotations

from pathlib import Path

from dqg.runtime.events import EventType
from dqg.runtime.execution_context import ExecutionContext
from dqg.runtime.lifecycle import LifecycleRegistry
from dqg.runtime.result import PhaseResult, RuntimeEvent

# ---------------------------------------------------------------------------
# PhaseResult 测试
# ---------------------------------------------------------------------------


class TestPhaseResult:
    def test_default_success(self):
        r = PhaseResult(phase_id="Q01", action="execute")
        assert r.success is True
        assert r.exit_code == 0
        assert r.errors == []

    def test_add_error_sets_failure(self):
        r = PhaseResult(phase_id="Q01", action="execute")
        r.add_error("something broke")
        assert r.success is False
        assert r.exit_code == 1
        assert "something broke" in r.errors
        assert any(e.event_type == EventType.ERROR for e in r.events)

    def test_add_warning_keeps_success(self):
        r = PhaseResult(phase_id="Q01", action="finalize")
        r.add_warning("minor issue")
        assert r.success is True
        assert "minor issue" in r.warnings

    def test_add_artifact(self):
        r = PhaseResult()
        r.add_artifact("report", "/tmp/report.md")
        assert r.artifacts["report"] == "/tmp/report.md"

    def test_to_dict_structure(self):
        r = PhaseResult(phase_id="Q05", action="execute")
        r.add_event(EventType.PHASE_STARTED, "started")
        r.add_artifact("ctx", "/tmp/ctx.md")
        d = r.to_dict()
        assert d["success"] is True
        assert d["phase_id"] == "Q05"
        assert d["action"] == "execute"
        assert len(d["events"]) == 1
        assert d["events"][0]["event"] == "phase_started"
        assert d["artifacts"]["ctx"] == "/tmp/ctx.md"

    def test_add_event_with_data(self):
        r = PhaseResult()
        r.add_event(EventType.CONTEXT_LOADED, "loaded", path="/tmp/x", truncated=False)
        e = r.events[0]
        assert e.data["path"] == "/tmp/x"
        assert e.data["truncated"] is False


# ---------------------------------------------------------------------------
# RuntimeEvent 测试
# ---------------------------------------------------------------------------


class TestRuntimeEvent:
    def test_to_dict_minimal(self):
        e = RuntimeEvent(EventType.PHASE_STARTED, "hello")
        d = e.to_dict()
        assert d["event"] == "phase_started"
        assert d["message"] == "hello"
        assert "data" not in d

    def test_to_dict_with_data(self):
        e = RuntimeEvent(EventType.CONTEXT_LOADED, "ctx", {"path": "/x"})
        d = e.to_dict()
        assert d["data"]["path"] == "/x"


# ---------------------------------------------------------------------------
# LifecycleRegistry 测试
# ---------------------------------------------------------------------------


class TestLifecycleRegistry:
    def test_register_and_get(self):
        reg = LifecycleRegistry()
        reg.register("h1", lambda ctx, r: None, stage="execute")
        reg.register("h2", lambda ctx, r: None, stage="finalize")
        assert len(reg.get_handlers("execute", "Q01")) == 1
        assert len(reg.get_handlers("finalize", "Q01")) == 1

    def test_phase_filter(self):
        reg = LifecycleRegistry()
        reg.register("h1", lambda ctx, r: None, stage="execute", phases={"Q06"})
        reg.register("h2", lambda ctx, r: None, stage="execute")  # all phases
        assert len(reg.get_handlers("execute", "Q06")) == 2
        assert len(reg.get_handlers("execute", "Q01")) == 1  # only h2

    def test_order(self):
        reg = LifecycleRegistry()
        order_log: list[str] = []
        reg.register("last", lambda ctx, r: order_log.append("last"), stage="execute", order=200)
        reg.register("first", lambda ctx, r: order_log.append("first"), stage="execute", order=10)
        reg.register("mid", lambda ctx, r: order_log.append("mid"), stage="execute", order=100)

        ctx = ExecutionContext(
            output_dir=Path("/tmp"),
            project_id="test",
            phase_id="Q01",
        )
        result = PhaseResult()
        reg.run_handlers("execute", ctx, result)
        assert order_log == ["first", "mid", "last"]

    def test_handler_failure_becomes_warning(self):
        reg = LifecycleRegistry()

        def bad_handler(ctx, r):
            raise ValueError("boom")

        reg.register("bad", bad_handler, stage="execute")
        ctx = ExecutionContext(
            output_dir=Path("/tmp"),
            project_id="test",
            phase_id="Q01",
        )
        result = PhaseResult()
        reg.run_handlers("execute", ctx, result)
        assert result.success is True  # handler failure doesn't fail the result
        assert any("boom" in w for w in result.warnings)

    def test_handler_adds_sidecar_event(self):
        reg = LifecycleRegistry()
        reg.register("noop", lambda ctx, r: None, stage="execute")
        ctx = ExecutionContext(
            output_dir=Path("/tmp"),
            project_id="test",
            phase_id="Q01",
        )
        result = PhaseResult()
        reg.run_handlers("execute", ctx, result)
        assert any(e.event_type == EventType.SIDECAR_COMPLETED and "noop" in e.message for e in result.events)


# ---------------------------------------------------------------------------
# ExecutionContext 测试
# ---------------------------------------------------------------------------


class TestExecutionContext:
    def test_defaults(self):
        ctx = ExecutionContext(
            output_dir=Path("/tmp/out"),
            project_id="proj1",
            phase_id="Q01",
        )
        assert ctx.profile_id == ""
        assert ctx.code_repo is None
        assert ctx.shared == {}

    def test_shared_data(self):
        ctx = ExecutionContext(
            output_dir=Path("/tmp"),
            project_id="p",
            phase_id="Q01",
        )
        ctx.shared["key"] = "value"
        assert ctx.shared["key"] == "value"


# ---------------------------------------------------------------------------
# Global handler registration 测试
# ---------------------------------------------------------------------------


class TestGlobalRegistration:
    def test_handlers_registered_on_import(self):
        """Import runtime 包后，全局 registry 应该有 handler."""
        from dqg.runtime.lifecycle import get_registry

        reg = get_registry()
        # execute handlers
        execute_all = reg.get_handlers("execute", "Q06")
        handler_names = {h.name for h in execute_all}
        assert "diff_context" in handler_names
        assert "weak_assert" in handler_names
        assert "business_mutations" in handler_names

        # finalize handlers
        finalize_all = reg.get_handlers("finalize", "Q01")
        handler_names = {h.name for h in finalize_all}
        assert "perf_metrics" in handler_names
        assert "memory_index" in handler_names
        assert "review_chain" in handler_names

    def test_coverage_matrix_only_for_a5(self):
        from dqg.runtime.lifecycle import get_registry

        reg = get_registry()
        a5_handlers = {h.name for h in reg.get_handlers("execute", "Q04")}
        a_handlers = {h.name for h in reg.get_handlers("execute", "Q01")}
        assert "coverage_matrix" in a5_handlers
        assert "coverage_matrix" not in a_handlers


def test_persist_inputs_writes_coverage_report(tmp_path):
    """handle_persist_inputs 应把 ctx.coverage_report 写入 _inputs.json."""
    from dqg.json_utils import load_json
    from dqg.runtime.handlers.handlers_execute import handle_persist_inputs

    internal = tmp_path / "_internal"
    ctx = ExecutionContext(
        output_dir=tmp_path,
        project_id="demo",
        phase_id="Q06",
        code_repo="/tmp/repo",
        coverage_report="/tmp/jacoco.xml",
    )
    ctx.internal_dir = internal
    result = PhaseResult(phase_id="Q06", action="execute")

    handle_persist_inputs(ctx, result)

    inputs_path = internal / "_inputs.json"
    assert inputs_path.exists()
    data = load_json(inputs_path)
    assert data["coverage_report"] == "/tmp/jacoco.xml"
    assert data["code_repo"] == "/tmp/repo"


def test_persist_inputs_omits_coverage_report_when_none(tmp_path):
    """coverage_report=None 时不写字段，保持向后兼容."""
    from dqg.json_utils import load_json
    from dqg.runtime.handlers.handlers_execute import handle_persist_inputs

    internal = tmp_path / "_internal"
    ctx = ExecutionContext(
        output_dir=tmp_path,
        project_id="demo",
        phase_id="Q06",
        code_repo="/tmp/repo",
    )
    ctx.internal_dir = internal
    result = PhaseResult(phase_id="Q06", action="execute")

    handle_persist_inputs(ctx, result)

    data = load_json(internal / "_inputs.json")
    assert "coverage_report" not in data
