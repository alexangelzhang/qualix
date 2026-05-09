"""Q05: 分支清单 vs Exception 类 EUT 覆盖（T6 配套 Guardrail）."""

from __future__ import annotations

from typing import Any

from dqg.json_utils import load_json
from dqg.quality.guardrail.guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)


class Q05BranchCoverageGuardrail(PhaseGuardrail):
    """若存在 `_internal/_q05_branch_inventory.json` 且含异常类分支，则要求至少一条 Exception EUT."""

    name = "q05_branch_coverage"
    level = GuardrailLevel.BLOCKED

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        inv_path = ctx.phase_dir / "_internal" / "_q05_branch_inventory.json"
        if not inv_path.exists():
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="未找到分支清单 _internal/_q05_branch_inventory.json，跳过分支覆盖门禁（建议执行 Q05 三步范式 Step A）",
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
        if exc_branches == 0:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="分支清单中无异常类分支，跳过高阶校验",
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
                    message="存在异常分支清单但缺少 phase_b_structured.json",
                )
            ]

        exception_euts = _count_exception_euts(data)
        if exception_euts < 1:
            return [
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
            ]

        return [
            GuardrailResult(
                guardrail_name=self.name,
                passed=True,
                level=GuardrailLevel.INFO,
                message=f"异常分支 {exc_branches} 条，Exception EUT {exception_euts} 条",
            )
        ]


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
