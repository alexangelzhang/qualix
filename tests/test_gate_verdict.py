"""Tests for GateVerdict unified gate layer."""

from __future__ import annotations

from dqg.runtime.gate_verdict import CheckItem, GateVerdict, _extract_handler_name, build_verdict
from dqg.runtime.result import PhaseResult


class TestCheckItem:
    def test_basic(self):
        c = CheckItem(source="handler", name="review_chain", passed=False, level="HARD", message="failed")
        assert c.source == "handler"
        assert not c.passed
        assert c.level == "HARD"


class TestGateVerdict:
    def test_empty_verdict_passes(self):
        v = GateVerdict(phase_id="Q01")
        assert v.passed
        assert not v.hard_blocked
        assert not v.soft_blocked

    def test_hard_blocked(self):
        v = GateVerdict(
            phase_id="Q01",
            checks=[
                CheckItem(source="handler", name="x", passed=False, level="HARD"),
            ],
        )
        assert v.hard_blocked
        assert not v.passed

    def test_soft_blocked(self):
        v = GateVerdict(
            phase_id="Q01",
            checks=[
                CheckItem(source="handler", name="x", passed=False, level="SOFT"),
            ],
        )
        assert v.soft_blocked
        assert not v.hard_blocked
        assert not v.passed

    def test_all_passed(self):
        v = GateVerdict(
            phase_id="Q01",
            checks=[
                CheckItem(source="handler", name="a", passed=True, level="HARD"),
                CheckItem(source="guardrail", name="b", passed=True, level="SOFT"),
            ],
        )
        assert v.passed
        assert not v.hard_blocked
        assert not v.soft_blocked

    def test_to_dict(self):
        v = GateVerdict(
            phase_id="Q03",
            checks=[
                CheckItem(source="handler", name="a", passed=True, level="HARD"),
                CheckItem(source="phase_constraints", name="b", passed=False, level="HARD", message="fail"),
            ],
        )
        d = v.to_dict()
        assert d["phase_id"] == "Q03"
        assert d["hard_blocked"] is True
        assert d["summary"]["total"] == 2
        assert d["summary"]["hard_failures"] == 1

    def test_hard_and_soft_failures(self):
        v = GateVerdict(
            phase_id="Q01",
            checks=[
                CheckItem(source="handler", name="a", passed=False, level="HARD"),
                CheckItem(source="guardrail", name="b", passed=False, level="SOFT"),
                CheckItem(source="schema", name="c", passed=True, level="HARD"),
            ],
        )
        assert len(v.hard_failures) == 1
        assert len(v.soft_failures) == 1


class TestBuildVerdict:
    def test_from_result_errors(self):
        result = PhaseResult(phase_id="Q01", action="finalize")
        result.add_error("BLOCKED: required handler review_chain failed: boom")
        result.add_warning("Handler facts_export failed: no column")

        verdict = build_verdict("Q01", result)
        assert len(verdict.checks) == 2
        assert verdict.hard_blocked
        assert verdict.checks[0].level == "HARD"
        assert verdict.checks[0].name == "review_chain"
        assert verdict.checks[1].level == "SOFT"
        assert verdict.checks[1].name == "facts_export"

    def test_from_guardrail_results(self):
        result = PhaseResult(phase_id="Q01", action="finalize")
        g_results = [
            {"guardrail": "semantic", "passed": True, "level": "blocked", "message": "ok", "details": {}},
            {"guardrail": "compliance", "passed": False, "level": "warning", "message": "low", "details": {}},
        ]
        verdict = build_verdict("Q01", result, guardrail_results=g_results)
        assert len(verdict.checks) == 2
        assert not verdict.hard_blocked
        assert verdict.soft_blocked

    def test_from_constraint_violations(self):
        result = PhaseResult(phase_id="Q03", action="finalize")
        violations = [
            {
                "label": "CRITICAL=0",
                "metric": "critical_count",
                "op": "==",
                "threshold": 0,
                "actual": 3,
                "block_if_fail": True,
            },
        ]
        verdict = build_verdict("Q03", result, constraint_violations=violations)
        assert len(verdict.checks) == 1
        assert verdict.hard_blocked
        assert verdict.checks[0].source == "phase_constraints"

    def test_combined(self):
        result = PhaseResult(phase_id="Q01", action="finalize")
        result.add_warning("Handler x failed: y")
        g = [{"guardrail": "g1", "passed": False, "level": "blocked", "message": "bad", "details": {}}]
        c = [
            {
                "label": "REQ>=1",
                "metric": "req_count",
                "op": ">=",
                "threshold": 1,
                "actual": None,
                "block_if_fail": True,
                "reason": "metric_resolve_failed",
            }
        ]
        verdict = build_verdict("Q01", result, guardrail_results=g, constraint_violations=c)
        assert len(verdict.checks) == 3
        assert verdict.hard_blocked


class TestSaveLoadVerdict:
    def test_roundtrip(self, tmp_path):
        from dqg.runtime.gate_verdict import load_verdict, save_verdict

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "PROJ" / "Q01").mkdir(parents=True)

        verdict = GateVerdict(
            phase_id="Q01",
            checks=[
                CheckItem(source="handler", name="a", passed=True, level="HARD"),
                CheckItem(source="phase_constraints", name="b", passed=False, level="SOFT", message="fail"),
            ],
        )
        save_verdict(output_dir, "PROJ", "Q01", verdict)
        loaded = load_verdict(output_dir, "PROJ", "Q01")

        assert loaded is not None
        assert loaded.phase_id == "Q01"
        assert len(loaded.checks) == 2
        assert loaded.soft_blocked
        assert not loaded.hard_blocked

    def test_load_missing(self, tmp_path):
        from dqg.runtime.gate_verdict import load_verdict

        output_dir = tmp_path / "output"
        output_dir.mkdir()
        assert load_verdict(output_dir, "PROJ", "Q01") is None


class TestExtractHandlerName:
    def test_blocked_prefix(self):
        assert _extract_handler_name("BLOCKED: required handler review_chain failed: boom") == "review_chain"

    def test_handler_prefix(self):
        assert _extract_handler_name("Handler facts_export failed: no column") == "facts_export"

    def test_unknown(self):
        assert _extract_handler_name("some random error") == "unknown"
