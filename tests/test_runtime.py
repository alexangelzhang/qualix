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

    def test_gate_handler_failure_skips_downstream(self):
        """gate=True handler 失败时，依赖它的 handler 被 skip（warning），不执行."""
        reg = LifecycleRegistry()
        ran: list[str] = []

        def gate_handler(ctx, r):
            raise ValueError("schema invalid")

        def downstream(ctx, r):
            ran.append("downstream")

        reg.register("hard_gate", gate_handler, stage="finalize", gate=True, required=True)
        reg.register("judge", downstream, stage="finalize", order=70, depends_on=["hard_gate"])

        ctx = ExecutionContext(output_dir=Path("/tmp"), project_id="p", phase_id="Q01")
        result = PhaseResult()
        reg.run_handlers("finalize", ctx, result)

        assert "downstream" not in ran
        assert any("judge" in w and "hard gate" in w for w in result.warnings)

    def test_gate_false_failure_does_not_skip_downstream(self):
        """gate=False（默认）的 handler 失败不影响下游执行."""
        reg = LifecycleRegistry()
        ran: list[str] = []

        def flaky(ctx, r):
            raise ValueError("transient error")

        def downstream(ctx, r):
            ran.append("downstream")

        reg.register("flaky", flaky, stage="finalize")
        reg.register("judge", downstream, stage="finalize", order=70, depends_on=["flaky"])

        ctx = ExecutionContext(output_dir=Path("/tmp"), project_id="p", phase_id="Q01")
        result = PhaseResult()
        reg.run_handlers("finalize", ctx, result)

        assert "downstream" in ran

    def test_gate_skip_propagates_transitively(self):
        """gate skip 传播：A(gate) 失败 → B 依赖 A 被跳过 → C 依赖 B 也被跳过."""
        reg = LifecycleRegistry()
        ran: list[str] = []

        def fail(ctx, r):
            raise ValueError("fail")

        reg.register("A", fail, stage="finalize", gate=True, required=True)
        reg.register("B", lambda ctx, r: ran.append("B"), stage="finalize", order=60, depends_on=["A"])
        reg.register("C", lambda ctx, r: ran.append("C"), stage="finalize", order=70, depends_on=["B"])

        ctx = ExecutionContext(output_dir=Path("/tmp"), project_id="p", phase_id="Q01")
        result = PhaseResult()
        reg.run_handlers("finalize", ctx, result)

        assert ran == []
        assert sum(1 for w in result.warnings if "hard gate" in w) == 2  # B and C skipped


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


def test_guardrail_coverage_evidence_trusts_structured_data():
    """ReportSemanticGuardrail 在 structured_data 存在时优先用 JSON，避免 markdown 表格截断误报."""
    from dqg.quality.guardrail import GuardrailContext
    from dqg.quality.guardrail.semantic_guardrail import ReportSemanticGuardrail

    # structured_data 里 evidence 含 [文件:行号] → 合格；report 表格里被截断只剩 "COVERED EUT-001 applyXxx" → 没行号
    structured_data = {
        "audit_items": [
            {
                "id": "AUDIT-001",
                "eut_id": "EUT-001",
                "status": "COVERED",
                "evidence": "applyXxx_shouldSucceed() [MrOrderMainServiceTest.java:100]",
            }
        ]
    }
    truncated_report = (
        "| AUDIT-001 | EUT-001 | SE-001 | Happy | COVERED | MrOrderMainService.applyXxx | applyXxx_shouldSucc"
    )

    ctx = GuardrailContext(
        output_dir=Path("/tmp"),
        project_id="demo",
        phase_id="Q06",
        phase_dir=Path("/tmp"),
        report_content=truncated_report,
        structured_data=structured_data,
    )
    guardrail = ReportSemanticGuardrail()
    results = guardrail._check_coverage_evidence(ctx)
    # structured_data 路径生效 → 找到合格 evidence → 无虚高告警
    assert not results, f"expected no coverage-inflation warning, got {[r.message for r in results]}"


def test_guardrail_coverage_evidence_catches_real_inflation():
    """structured_data 中 COVERED 但 evidence 真的缺行号 → 正确告警."""
    from dqg.quality.guardrail import GuardrailContext
    from dqg.quality.guardrail.semantic_guardrail import ReportSemanticGuardrail

    structured_data = {
        "audit_items": [
            {
                "id": "AUDIT-001",
                "eut_id": "EUT-001",
                "status": "COVERED",
                "evidence": "该方法已覆盖",  # 无行号
            }
        ]
    }
    ctx = GuardrailContext(
        output_dir=Path("/tmp"),
        project_id="demo",
        phase_id="Q06",
        phase_dir=Path("/tmp"),
        report_content="",
        structured_data=structured_data,
    )
    guardrail = ReportSemanticGuardrail()
    results = guardrail._check_coverage_evidence(ctx)
    assert results, "expected warning when evidence truly lacks file:line"
    assert "COVERED" in results[0].message


def test_mock_strip_meta_sections_removes_discussion_lines():
    """_strip_meta_sections 应同时剥离 # 元章节和讨论性行（含「未扫描到/例如/风险」等）."""
    from dqg.runtime.handlers.handlers_detection import _strip_meta_sections

    report = (
        "# 审计明细\n"
        "mock.when(..).thenReturn(new UserDO())\n"  # 事实行, 应保留
        "## 自我评审\n"
        "mock.returnValue=null\n"  # 评审章节, 剥离
        "## 改进建议\n"
        "建议避免 mock 返回 null\n"  # 改进建议 + 建议关键词
        "## 明细\n"
        "未扫描到 mock return null 等 smell\n"  # 讨论性修饰词
    )
    stripped = _strip_meta_sections(report)
    assert "mock.when(..).thenReturn(new UserDO())" in stripped
    assert "returnValue=null" not in stripped
    assert "mock return null 等 smell" not in stripped
    assert "建议避免" not in stripped


def test_fabrication_fallback_across_phases(tmp_path, monkeypatch):
    """_get_code_repos 在当前 Phase 无 _inputs.json 时回退其他 Phase."""
    from dqg.core.state_machine import PHASE_DEFS, internal_dir
    from dqg.json_utils import save_json
    from dqg.quality.guardrail import GuardrailContext
    from dqg.quality.guardrail.fabrication_detector import FabricationDetectorGuardrail

    # 在 Q05 目录下种 _inputs.json，Q06 无
    q05_dir = internal_dir(tmp_path, "demo", PHASE_DEFS["Q05"])
    q05_dir.mkdir(parents=True, exist_ok=True)
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    save_json(q05_dir / "_inputs.json", {"code_repos": [str(fake_repo)]})

    ctx = GuardrailContext(
        output_dir=tmp_path,
        project_id="demo",
        phase_id="Q06",
        phase_dir=tmp_path,
    )
    fd = FabricationDetectorGuardrail()
    repos = fd._get_code_repos(ctx)
    assert len(repos) == 1
    assert repos[0] == fake_repo.resolve() or repos[0] == fake_repo
