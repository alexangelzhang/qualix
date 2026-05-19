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
    """Q05 Mock 巧合正确检测: Q05 跳过（测试代码用 Mock 是正常的）."""

    def test_q05_coincidence_skipped(self, tmp_path: Path):
        from dqg.runtime.handlers_detection import handle_mock_coincidence_check

        ctx = _make_ctx(tmp_path, "Q05")
        result = PhaseResult(phase_id="Q05")
        handle_mock_coincidence_check(ctx, result)

        assert result.success
        assert not result.errors
        assert not result.warnings

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


# ---------------------------------------------------------------------------
# C9: EUT 矩阵实现完整性——方法级检查
# ---------------------------------------------------------------------------


class TestEutImplementationCompleteness:
    """C9: 升级后的方法级实现完整性检查."""

    def _call(self, data: dict, test_files: list) -> list[str]:
        from dqg.quality.checks.q05_structure_checks import _check_eut_implementation_completeness

        return _check_eut_implementation_completeness(data, test_files)

    def _eut(self, eut_id: str, when: str) -> dict:
        return {"eut_id": eut_id, "when": when}

    # ── 层 1：文件不存在 ────────────────────────────────────────────────────

    def test_no_test_file_blocked(self, tmp_path: Path):
        """被测类无对应测试文件 → BLOCKED eut_not_implemented."""
        data = {"eut_items": [self._eut("EUT-001", "OrderService.createOrder 被调用时")]}
        errors = self._call(data, [])
        assert any("eut_not_implemented" in e for e in errors)
        assert any("BLOCKED" in e for e in errors)

    # ── 层 2a：精确模式——有 EUT-xxx 追溯注释，全覆盖 ────────────────────────

    def test_precise_mode_all_covered(self, tmp_path: Path):
        """@Test 方法有 EUT-xxx 注释且全部覆盖 → 无错误."""
        tf = tmp_path / "OrderServiceTest.java"
        tf.write_text(
            "@Test\nvoid test1() { // EUT-001\n  assertEquals(1,1);\n}\n"
            "@Test\nvoid test2() { // EUT-002\n  assertEquals(1,1);\n}\n",
            encoding="utf-8",
        )
        data = {
            "eut_items": [
                self._eut("EUT-001", "OrderService.createOrder 正常路径"),
                self._eut("EUT-002", "OrderService.createOrder 异常路径"),
            ]
        }
        errors = self._call(data, [tf])
        assert errors == []

    # ── 层 2b：精确模式——部分 EUT 无对应 @Test ─────────────────────────────

    def test_precise_mode_missing_eut_blocked(self, tmp_path: Path):
        """有追溯注释但 EUT-002 没有对应 @Test → BLOCKED eut_method_missing."""
        tf = tmp_path / "OrderServiceTest.java"
        tf.write_text(
            "@Test\nvoid test1() { // EUT-001\n  assertEquals(1,1);\n}\n",
            encoding="utf-8",
        )
        data = {
            "eut_items": [
                self._eut("EUT-001", "OrderService.createOrder 正常路径"),
                self._eut("EUT-002", "OrderService.createOrder 异常路径"),
            ]
        }
        errors = self._call(data, [tf])
        assert any("eut_method_missing" in e for e in errors)
        assert any("EUT-002" in e for e in errors)

    # ── 层 2c：代理模式——无追溯注释，方法数充足 ───────────────────────────

    def test_proxy_mode_enough_methods(self, tmp_path: Path):
        """无 EUT-xxx 注释，@Test 数 ≥ EUT 数 → 无错误."""
        tf = tmp_path / "OrderServiceTest.java"
        tf.write_text(
            "@Test\nvoid test1() { assertEquals(1,1); }\n@Test\nvoid test2() { assertEquals(2,2); }\n",
            encoding="utf-8",
        )
        data = {
            "eut_items": [
                self._eut("EUT-001", "OrderService.createOrder 路径一"),
                self._eut("EUT-002", "OrderService.createOrder 路径二"),
            ]
        }
        errors = self._call(data, [tf])
        assert errors == []

    # ── 层 2d：代理模式——方法数不足 ────────────────────────────────────────

    def test_proxy_mode_insufficient_methods_blocked(self, tmp_path: Path):
        """无追溯注释，@Test 数 < EUT 数 → BLOCKED eut_method_count."""
        tf = tmp_path / "OrderServiceTest.java"
        tf.write_text(
            "@Test\nvoid test1() { assertEquals(1,1); }\n",
            encoding="utf-8",
        )
        data = {
            "eut_items": [
                self._eut("EUT-001", "OrderService.createOrder 路径一"),
                self._eut("EUT-002", "OrderService.createOrder 路径二"),
                self._eut("EUT-003", "OrderService.createOrder 路径三"),
            ]
        }
        errors = self._call(data, [tf])
        assert any("eut_method_count" in e for e in errors)
        assert any("BLOCKED" in e for e in errors)

    # ── 边界：空 eut_items → 无错误 ─────────────────────────────────────────

    def test_empty_euts_noop(self, tmp_path: Path):
        """eut_items 为空时直接返回空列表."""
        errors = self._call({"eut_items": []}, [])
        assert errors == []


# ---------------------------------------------------------------------------
# C10: git diff 变更实现类必须有 EUT 覆盖
# ---------------------------------------------------------------------------


class TestGitDiffCoverage:
    """C10: _check_q05_git_diff_coverage."""

    def _call(self, eut_items: list, diff_files: list) -> list[str]:
        from dqg.quality.checks.q05_structure_checks import _check_q05_git_diff_coverage

        data = {"eut_items": eut_items}
        target_modules_data = {"git_diff_files": diff_files}
        return _check_q05_git_diff_coverage(data, target_modules_data)

    def _eut(self, when: str) -> dict:
        return {"eut_id": "EUT-001", "when": when, "given": ""}

    def test_covered_class_no_warning(self):
        """EUT when 字段提到了变更类 → 无 WARNING."""
        errors = self._call(
            [self._eut("OrderService.create 被调用")],
            ["maf-srv-service/src/main/java/com/mi/maf/srv/service/OrderService.java"],
        )
        assert errors == []

    def test_uncovered_impl_class_blocked(self):
        """变更的 Service 类未出现在任何 EUT → BLOCKED git_diff_not_covered."""
        errors = self._call(
            [self._eut("OtherService.doSomething 被调用")],
            ["maf-srv-service/src/main/java/com/mi/maf/srv/service/process/DetectionProcessSrvService.java"],
        )
        assert any("git_diff_not_covered" in e for e in errors)
        assert any("DetectionProcessSrvService" in e for e in errors)
        assert all("BLOCKED" in e for e in errors)

    def test_skip_interface_module(self):
        """maf-interface/ 模块的接口定义 → 跳过不检查."""
        errors = self._call(
            [self._eut("OtherService.doSomething")],
            ["maf-interface/src/main/java/com/mi/maf/inter/service/FooService.java"],
        )
        assert errors == []

    def test_skip_constant_class(self):
        """常量/枚举类（OpCode.java、SrvTagEnum.java）→ 跳过不检查."""
        errors = self._call(
            [self._eut("SomeService.method 调用")],
            [
                "maf-core/src/main/java/com/mi/maf/core/constant/OpCode.java",
                "maf-core/src/main/java/com/mi/maf/core/constant/SrvTagEnum.java",
            ],
        )
        assert errors == []

    def test_skip_non_impl_suffix(self):
        """VO/DTO/Builder 等无业务逻辑类 → 跳过不检查."""
        errors = self._call(
            [self._eut("SomeService.method 调用")],
            ["maf-srv-service/src/main/java/com/mi/maf/srv/vo/ExchangeSrvVo.java"],
        )
        assert errors == []

    def test_no_target_modules_data_noop(self):
        """target_modules_data 为 None → 直接返回空."""
        from dqg.quality.checks.q05_structure_checks import _check_q05_git_diff_coverage

        assert _check_q05_git_diff_coverage({"eut_items": []}, None) == []


# ---------------------------------------------------------------------------
# check_eut_method_alignment：方法级 C1+C2
# ---------------------------------------------------------------------------


class TestEutMethodAlignment:
    """check_eut_method_alignment: @Test 方法体必须含 EUT then 业务关键词."""

    def _call(self, eut_items: list, java_src: str, tmp_path) -> list[str]:
        from dqg.quality.checks.q05_structure_checks import check_eut_method_alignment

        tf = tmp_path / "FooServiceTest.java"
        tf.write_text(java_src, encoding="utf-8")
        return check_eut_method_alignment({"eut_items": eut_items}, [tf])

    def _eut(self, eid: str, then: str) -> dict:
        return {"eut_id": eid, "when": "FooService.doSomething 被调用", "then": then}

    def test_method_body_matches_then_no_warning(self, tmp_path):
        """@Test 方法体含 then 的业务方法名 → 无 WARNING."""
        errors = self._call(
            [self._eut("EUT-001", "assertEquals(2, result.size()); verify(orderService, times(1)).createOrder(any())")],
            "@Test\nvoid test1() {\n  // EUT-001\n  List<X> result = service.doSomething();\n  assertEquals(2, result.size());\n  verify(orderService, times(1)).createOrder(any());\n}\n",
            tmp_path,
        )
        assert errors == []

    def test_method_body_misses_then_business_method_warns(self, tmp_path):
        """@Test 方法体只有 assertNull，then 要求 createOrder → WARNING."""
        errors = self._call(
            [self._eut("EUT-001", "assertEquals(2, result.size()); verify(orderService, times(1)).createOrder(any())")],
            "@Test\nvoid test1() {\n  // EUT-001\n  Map<String,String> result = service.doSomething(null, 10000L);\n  assertNull(result);\n}\n",
            tmp_path,
        )
        assert any("eut_method_then_mismatch" in e for e in errors)
        assert any("EUT-001" in e for e in errors)
        assert all("WARNING" in e for e in errors)

    def test_no_eut_annotation_skipped(self, tmp_path):
        """@Test 方法体无 EUT-xxx 注释 → 跳过，无 WARNING."""
        errors = self._call(
            [self._eut("EUT-001", "verify(orderService).createOrder(any())")],
            "@Test\nvoid test1() {\n  assertNull(service.doSomething(null));\n}\n",
            tmp_path,
        )
        assert errors == []

    def test_empty_euts_noop(self, tmp_path):
        """空 eut_items → 直接返回空."""
        from dqg.quality.checks.q05_structure_checks import check_eut_method_alignment

        assert check_eut_method_alignment({"eut_items": []}, []) == []
