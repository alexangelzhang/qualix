"""内置 PhaseGuardrail 实现 — 包装现有三层检查.

- FinalizeChecksGuardrail: 硬性校验（BLOCKED）
- PhaseConstraintsGuardrail: DSL 约束断言（BLOCKED/WARNING）
- RuleComplianceGuardrail: 规则合规检查（WARNING/INFO）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.quality.guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)
from dqg.quality.semantic_guardrail import ReportSemanticGuardrail


class FinalizeChecksGuardrail(PhaseGuardrail):
    """包装 finalize_checks.run_finalize_checks — 硬性校验."""

    name = "finalize_checks"
    level = GuardrailLevel.BLOCKED

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        from dqg.quality.finalize_checks import run_finalize_checks

        errors = run_finalize_checks(ctx.output_dir, ctx.project_id, ctx.phase_id)
        if not errors:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=True,
                level=GuardrailLevel.INFO,
                message="硬性校验全部通过",
            )]

        results: list[GuardrailResult] = []
        for err in errors:
            is_blocked = err.startswith("BLOCKED")
            results.append(GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.BLOCKED if is_blocked else GuardrailLevel.WARNING,
                message=err,
            ))
        return results


class PhaseConstraintsGuardrail(PhaseGuardrail):
    """包装 phase_constraints.enforce_phase_constraints — DSL 约束."""

    name = "phase_constraints"
    level = GuardrailLevel.BLOCKED

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        from dqg.runtime.phase_constraints import enforce_phase_constraints

        violations = enforce_phase_constraints(
            ctx.output_dir, ctx.project_id, ctx.phase_id,
        )
        if not violations:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=True,
                level=GuardrailLevel.INFO,
                message="DSL 约束全部满足",
            )]

        results: list[GuardrailResult] = []
        for v in violations:
            level = (
                GuardrailLevel.BLOCKED
                if v.get("block_if_fail")
                else GuardrailLevel.WARNING
            )
            results.append(GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=level,
                message=f"{v['label']}: 实际值 {v['actual']} {v['op']} {v['threshold']}",
                details=[f"metric={v['metric']}"],
            ))
        return results


class RuleComplianceGuardrail(PhaseGuardrail):
    """包装 rule_compliance.compute_rule_compliance — 规则合规."""

    name = "rule_compliance"
    level = GuardrailLevel.WARNING

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        from dqg.quality.rule_compliance import compute_rule_compliance

        compliance = compute_rule_compliance(
            ctx.output_dir, ctx.project_id, ctx.phase_id,
        )
        if not compliance:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=True,
                level=GuardrailLevel.INFO,
                message="无适用规则",
            )]

        results: list[GuardrailResult] = []
        for rule in compliance.get("rules", []):
            if rule is None:
                continue
            passed = rule.get("ok", True)
            results.append(GuardrailResult(
                guardrail_name=self.name,
                passed=passed,
                level=GuardrailLevel.INFO if passed else GuardrailLevel.WARNING,
                message=f"[{rule.get('category', '?')}] {rule.get('name', '?')}: {rule.get('detail', '')}",
                details=[f"id={rule.get('id', '?')}"],
            ))
        return results


# ---------------------------------------------------------------------------
# 默认 guardrail 集合
# ---------------------------------------------------------------------------

#: 所有 Phase 共用的 output guardrail 列表
DEFAULT_OUTPUT_GUARDRAILS: list[PhaseGuardrail] = [
    FinalizeChecksGuardrail(),
    PhaseConstraintsGuardrail(),
    RuleComplianceGuardrail(),
    ReportSemanticGuardrail(),
]


def get_guardrails(phase_id: str) -> list[PhaseGuardrail]:
    """获取指定 Phase 的 guardrail 列表.

    优先从 PHASE_DEFS 读取自定义 guardrails，
    未配置则返回默认集合。
    """
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    custom = phase_def.get("output_guardrails")
    if custom is not None:
        return custom
    return DEFAULT_OUTPUT_GUARDRAILS
