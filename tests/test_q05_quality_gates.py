"""Q05 左移质量门控测试：EUT then validator + weak_assert_gate BLOCKED + mock_coincidence BLOCKED + scan handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from dqg.runtime.execution_context import ExecutionContext
from dqg.runtime.result import PhaseResult
from dqg.schemas.phase_b import EutItem, RiskTier, RouteType

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Layer 1: EUT then 字段模糊检测
# ---------------------------------------------------------------------------


class TestEutThenValidator:
    """EUT then 字段必须包含具体断言或值，拒绝模糊描述."""

    def _make_eut(self, then: str) -> EutItem:
        return EutItem(
            eut_id="EUT-001",
            bound_se="SE-001",
            route_type=RouteType.HAPPY,
            given="正常 DTO",
            when="调用 createOrder",
            then=then,
            risk_tier=RiskTier.T1,
        )

    @pytest.mark.parametrize(
        "vague_then",
        [
            "验证成功",
            "验证结果",
            "检查结果",
            "确认正确",
            "确认成功",
            "验证通过",
            "测试通过",
            "结果正确",
            "符合预期",
            "正常返回",
            "返回成功",
            "执行成功",
            "功能正常",
            "断言通过",
        ],
    )
    def test_rejects_vague_then(self, vague_then: str):
        """模糊黑名单中的描述应被拒绝."""
        with pytest.raises(ValidationError, match="过于模糊"):
            self._make_eut(vague_then)

    @pytest.mark.parametrize(
        "concrete_then",
        [
            "assertEquals(OrderStatus.APPROVED, result.getStatus())",
            "assertThrows(IllegalArgumentException.class, ...)",
            "verify(repository, times(1)).save(any())",
            "返回状态 PROCESSING",
            "订单金额等于 10000 分",
            "抛出 BusinessException",
            "结果为 null",
            "调用 1 次 notify",
            "列表包含 itemA",
            "集合大小 == 3",
            "返回 code 200",
        ],
    )
    def test_accepts_concrete_then(self, concrete_then: str):
        """包含具体断言/值的描述应通过."""
        eut = self._make_eut(concrete_then)
        assert eut.then == concrete_then

    def test_rejects_non_concrete_without_blacklist_match(self):
        """不在黑名单但也不具体的描述应被拒绝."""
        with pytest.raises(ValidationError, match="缺少具体性"):
            self._make_eut("处理完毕后系统正常运行")


# ---------------------------------------------------------------------------
# Layer 2: weak_assert_gate Q05 BLOCKED
# ---------------------------------------------------------------------------


def _make_ctx(tmp_path: Path, phase_id: str = "Q05") -> ExecutionContext:
    """构造最小 ExecutionContext."""
    internal_dir = tmp_path / "internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    return ExecutionContext(
        output_dir=tmp_path,
        project_id="test",
        phase_id=phase_id,
        internal_dir=internal_dir,
        phase_root=tmp_path,
        phase_def={"dir_suffix": "phaseB"},
        shared={},
    )


class TestWeakAssertGateQ05:
    """Q05 弱断言 gate: high-risk >= 1 触发 BLOCKED."""

    def test_q05_high_risk_1_triggers_blocked(self, tmp_path: Path):
        from dqg.runtime.handlers_detection import handle_weak_assert_gate

        ctx = _make_ctx(tmp_path, "Q05")
        payload = {
            "summary": {
                "high_risk_count": 1,
                "test_method_count": 5,
                "weak_method_count": 1,
            }
        }
        (ctx.internal_dir / "_weak_assert_context.json").write_text(json.dumps(payload), encoding="utf-8")

        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_gate(ctx, result)

        assert not result.success
        assert any("BLOCKED" in e for e in result.errors)

    def test_q06_high_risk_1_no_block(self, tmp_path: Path):
        """Q06 同样 high_risk=1 不触发 BLOCKED（阈值为 3 才 WARNING）."""
        from dqg.runtime.handlers_detection import handle_weak_assert_gate

        ctx = _make_ctx(tmp_path, "Q06")
        payload = {
            "summary": {
                "high_risk_count": 1,
                "test_method_count": 5,
                "weak_method_count": 1,
            }
        }
        (ctx.internal_dir / "_weak_assert_context.json").write_text(json.dumps(payload), encoding="utf-8")

        result = PhaseResult(phase_id="Q06")
        handle_weak_assert_gate(ctx, result)

        assert result.success
        assert not result.errors

    def test_q06_high_risk_3_triggers_warning(self, tmp_path: Path):
        """Q06 high_risk=3 触发 WARNING 但不 BLOCKED."""
        from dqg.runtime.handlers_detection import handle_weak_assert_gate

        ctx = _make_ctx(tmp_path, "Q06")
        payload = {
            "summary": {
                "high_risk_count": 3,
                "test_method_count": 5,
                "weak_method_count": 3,
            }
        }
        (ctx.internal_dir / "_weak_assert_context.json").write_text(json.dumps(payload), encoding="utf-8")

        result = PhaseResult(phase_id="Q06")
        handle_weak_assert_gate(ctx, result)

        assert result.success  # WARNING 不影响 success
        assert result.warnings

    def test_no_json_file_noop(self, tmp_path: Path):
        """_weak_assert_context.json 不存在时静默跳过."""
        from dqg.runtime.handlers_detection import handle_weak_assert_gate

        ctx = _make_ctx(tmp_path, "Q05")
        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_gate(ctx, result)

        assert result.success
        assert not result.errors
        assert not result.warnings


# ---------------------------------------------------------------------------
# Layer 3: mock_coincidence_check Q05 BLOCKED
# ---------------------------------------------------------------------------


class TestMockCoincidenceQ05:
    """Q05 Mock 巧合正确检测: coincidence_hits 触发 BLOCKED."""

    def _write_report(self, tmp_path: Path, content: str) -> None:
        (tmp_path / "eut_matrix.md").write_text(content, encoding="utf-8")

    def test_q05_coincidence_hit_triggers_blocked(self, tmp_path: Path):
        from dqg.runtime.handlers_detection import handle_mock_coincidence_check

        ctx = _make_ctx(tmp_path, "Q05")
        self._write_report(tmp_path, "Mock 设置固定返回值，when(service).thenReturn(0)")

        result = PhaseResult(phase_id="Q05")
        handle_mock_coincidence_check(ctx, result)

        assert not result.success
        assert any("BLOCKED" in e for e in result.errors)

    def test_q06_coincidence_hit_warning_only(self, tmp_path: Path):
        """Q06 同样 coincidence hit 只触发 WARNING."""
        from dqg.runtime.handlers_detection import handle_mock_coincidence_check

        ctx = _make_ctx(tmp_path, "Q06")
        # Q06 report file is ut_audit_report.md
        (tmp_path / "ut_audit_report.md").write_text(
            "Mock 设置固定返回值，when(service).thenReturn(0)", encoding="utf-8"
        )

        result = PhaseResult(phase_id="Q06")
        handle_mock_coincidence_check(ctx, result)

        assert result.success
        assert result.warnings

    def test_no_report_noop(self, tmp_path: Path):
        """报告文件不存在时静默跳过."""
        from dqg.runtime.handlers_detection import handle_mock_coincidence_check

        ctx = _make_ctx(tmp_path, "Q05")
        result = PhaseResult(phase_id="Q05")
        handle_mock_coincidence_check(ctx, result)

        assert result.success
        assert not result.errors


# ---------------------------------------------------------------------------
# Layer 2 补充: handle_weak_assert_scan_q05
# ---------------------------------------------------------------------------


class TestWeakAssertScanQ05:
    """Q05 finalize 扫描 handler: 从 structured JSON 提取测试文件并扫描."""

    def test_scans_test_files_from_structured_json(self, tmp_path: Path):
        from dqg.runtime.handlers_detection import handle_weak_assert_scan_q05

        # 构造 code_repo 和测试文件
        repo = tmp_path / "repo"
        test_dir = repo / "src/test/java/demo"
        test_dir.mkdir(parents=True)
        (test_dir / "OrderServiceTest.java").write_text(
            """
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    @Test
    void shouldOnlyCheckNotNull() {
        Object result = service.createOrder();
        assertNotNull(result);
    }
}
""".strip(),
            encoding="utf-8",
        )

        # 构造 output 目录和 structured JSON
        phase_root = tmp_path / "output" / "test" / "phaseB"
        internal_dir = phase_root / "_internal"
        internal_dir.mkdir(parents=True)

        structured = {
            "project_id": "test",
            "eut_items": [],
            "test_cases": [
                {
                    "id": "TC-001",
                    "repo": "car-mrs",
                    "covered_by": "OrderServiceTest#shouldOnlyCheckNotNull",
                    "se_refs": ["SE-001"],
                }
            ],
        }
        (phase_root / "phase_b_structured.json").write_text(json.dumps(structured), encoding="utf-8")

        ctx = ExecutionContext(
            output_dir=tmp_path / "output",
            project_id="test",
            phase_id="Q05",
            code_repo=str(repo),
            internal_dir=internal_dir,
            phase_root=phase_root,
            phase_def={"dir_suffix": "phaseB"},
            shared={},
        )

        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_scan_q05(ctx, result)

        # 验证生成了 _weak_assert_context.json
        json_path = internal_dir / "_weak_assert_context.json"
        assert json_path.exists()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["summary"]["high_risk_count"] >= 1

    def test_no_code_repo_noop(self, tmp_path: Path):
        """code_repo 为 None 时静默跳过."""
        from dqg.runtime.handlers_detection import handle_weak_assert_scan_q05

        ctx = _make_ctx(tmp_path, "Q05")
        ctx.code_repo = None
        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_scan_q05(ctx, result)

        assert not (ctx.internal_dir / "_weak_assert_context.json").exists()

    def test_no_structured_json_noop(self, tmp_path: Path):
        """phase_b_structured.json 不存在时静默跳过."""
        from dqg.runtime.handlers_detection import handle_weak_assert_scan_q05

        repo = tmp_path / "repo"
        repo.mkdir()
        ctx = _make_ctx(tmp_path, "Q05")
        ctx.code_repo = str(repo)
        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_scan_q05(ctx, result)

        assert not (ctx.internal_dir / "_weak_assert_context.json").exists()

    def test_no_covered_by_noop(self, tmp_path: Path):
        """test_cases 中没有 covered_by 时静默跳过."""
        from dqg.runtime.handlers_detection import handle_weak_assert_scan_q05

        repo = tmp_path / "repo"
        repo.mkdir()

        phase_root = tmp_path / "output" / "test" / "phaseB"
        internal_dir = phase_root / "_internal"
        internal_dir.mkdir(parents=True)

        structured = {
            "project_id": "test",
            "eut_items": [],
            "test_cases": [{"id": "TC-001", "repo": "car-mrs", "covered_by": "", "se_refs": ["SE-001"]}],
        }
        (phase_root / "phase_b_structured.json").write_text(json.dumps(structured), encoding="utf-8")

        ctx = ExecutionContext(
            output_dir=tmp_path / "output",
            project_id="test",
            phase_id="Q05",
            code_repo=str(repo),
            internal_dir=internal_dir,
            phase_root=phase_root,
            phase_def={"dir_suffix": "phaseB"},
            shared={},
        )
        result = PhaseResult(phase_id="Q05")
        handle_weak_assert_scan_q05(ctx, result)

        assert not (internal_dir / "_weak_assert_context.json").exists()
