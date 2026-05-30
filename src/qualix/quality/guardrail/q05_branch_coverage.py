"""Q05: 分支清单 vs Exception/Boundary 类 EUT 覆盖（T6 配套 Guardrail）."""

from __future__ import annotations

from typing import Any

from qualix.json_utils import load_json
from qualix.quality.guardrail.guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)


class Q05BranchCoverageGuardrail(PhaseGuardrail):
    """若存在 `_internal/_q05_branch_inventory.json` 且含异常/边界类分支，则要求有对应 EUT."""

    name = "q05_branch_coverage"
    level = GuardrailLevel.BLOCKED

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        inv_path = ctx.phase_dir / "_internal" / "_q05_branch_inventory.json"
        if not inv_path.exists():
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.WARNING,
                    message="未执行 Q05 三步范式 Step A，分支清单缺失，异常/边界路径覆盖无法验证（_internal/_q05_branch_inventory.json）",
                )
            ]

        inv = load_json(inv_path)
        if inv is None:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.WARNING,
                    message="分支清单 JSON 无法解析",
                )
            ]

        exc_branches = _count_exception_branches(inv)
        boundary_branches = _count_boundary_branches(inv)

        if exc_branches == 0 and boundary_branches == 0:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="分支清单中无异常/边界类分支，跳过高阶校验",
                )
            ]

        structured_path = ctx.phase_dir / "phase_b_structured.json"
        data = load_json(structured_path)
        if not data:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.BLOCKED,
                    message="存在异常/边界分支清单但缺少 phase_b_structured.json",
                )
            ]

        results = []

        # 检查 Exception 分支覆盖
        if exc_branches > 0:
            exception_euts = _count_exception_euts(data)
            if exception_euts < 1:
                results.append(
                    GuardrailResult(
                        guardrail_name=self.name,
                        passed=False,
                        level=GuardrailLevel.BLOCKED,
                        message=(
                            f"分支清单登记 {exc_branches} 条异常类分支，但 EUT 中无 route_type=Exception 条目。"
                            "请按三步范式 Step C 补充异常路径 EUT。"
                        ),
                        details=[f"exception_branches={exc_branches}", f"exception_euts={exception_euts}"],
                    )
                )
            else:
                results.append(
                    GuardrailResult(
                        guardrail_name=self.name,
                        passed=True,
                        level=GuardrailLevel.INFO,
                        message=f"异常分支 {exc_branches} 条，Exception EUT {exception_euts} 条",
                    )
                )

        # 检查 Boundary 分支覆盖
        if boundary_branches > 0:
            boundary_euts = _count_boundary_euts(data)
            if boundary_euts < 1:
                results.append(
                    GuardrailResult(
                        guardrail_name=self.name,
                        passed=False,
                        level=GuardrailLevel.BLOCKED,
                        message=(
                            f"分支清单登记 {boundary_branches} 条边界类分支，但 EUT 中无 route_type=Boundary 条目。"
                            "请按三步范式 Step C 补充边界路径 EUT（null/空集合/0值/负数/超大值/off-by-one）。"
                        ),
                        details=[f"boundary_branches={boundary_branches}", f"boundary_euts={boundary_euts}"],
                    )
                )
            else:
                results.append(
                    GuardrailResult(
                        guardrail_name=self.name,
                        passed=True,
                        level=GuardrailLevel.INFO,
                        message=f"边界分支 {boundary_branches} 条，Boundary EUT {boundary_euts} 条",
                    )
                )

        return (
            results
            if results
            else [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message=f"异常分支 {exc_branches} 条，边界分支 {boundary_branches} 条，均有对应 EUT",
                )
            ]
        )


def _count_exception_branches(inv: dict[str, Any]) -> int:
    n = 0
    targets = inv.get("targets")
    if not isinstance(targets, list):
        return 0
    for t in targets:
        if not isinstance(t, dict):
            continue
        branches = t.get("branches")
        if not isinstance(branches, list):
            continue
        for b in branches:
            if not isinstance(b, dict):
                continue
            kind = str(b.get("kind", "")).lower()
            if kind in ("exception", "error", "throws", "catch"):
                n += 1
    return n


def _count_boundary_branches(inv: dict[str, Any]) -> int:
    n = 0
    targets = inv.get("targets")
    if not isinstance(targets, list):
        return 0
    for t in targets:
        if not isinstance(t, dict):
            continue
        branches = t.get("branches")
        if not isinstance(branches, list):
            continue
        for b in branches:
            if not isinstance(b, dict):
                continue
            kind = str(b.get("kind", "")).lower()
            if kind in ("boundary", "edge", "null", "empty", "zero", "negative", "overflow"):
                n += 1
    return n


def _count_exception_euts(data: dict[str, Any]) -> int:
    items = data.get("eut_items") or []
    if not isinstance(items, list):
        return 0
    c = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        rt = str(it.get("route_type", "")).strip()
        if rt == "Exception":
            c += 1
    return c


def _count_boundary_euts(data: dict[str, Any]) -> int:
    items = data.get("eut_items") or []
    if not isinstance(items, list):
        return 0
    c = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        rt = str(it.get("route_type", "")).strip()
        if rt == "Boundary":
            c += 1
    return c
