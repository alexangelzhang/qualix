"""PhaseGuardrail — 统一质量门控接口.

借鉴 Agent SDK Guardrail 模式，将 Qualix 现有三层检查
（finalize_checks / phase_constraints / rule_checks）
统一为 PhaseGuardrail 接口。

用法::

    guardrails = get_guardrails(phase_id)
    results = run_guardrails(guardrails, ctx)
    blocked = [r for r in results if r.level == GuardrailLevel.BLOCKED]
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class GuardrailLevel(Enum):
    """门控严重级别."""

    BLOCKED = "BLOCKED"  # 阻断 finalize/approve
    WARNING = "WARNING"  # 警告但不阻断
    INFO = "INFO"  # 仅信息展示


@dataclass
class GuardrailResult:
    """单条门控检查结果."""

    guardrail_name: str
    passed: bool
    level: GuardrailLevel
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class GuardrailContext:
    """门控执行上下文."""

    output_dir: Path
    project_id: str
    phase_id: str
    phase_dir: Path
    report_content: str = ""
    structured_data: dict[str, Any] = field(default_factory=dict)


class PhaseGuardrail:
    """质量门控基类. 子类 override check() 方法."""

    name: str = "base"
    level: GuardrailLevel = GuardrailLevel.WARNING
    run_in_parallel: bool = True

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """执行检查，返回结果列表. 子类必须实现."""
        raise NotImplementedError


def run_guardrails(
    guardrails: list[PhaseGuardrail],
    ctx: GuardrailContext,
    *,
    parallel: bool = True,
) -> list[GuardrailResult]:
    """执行一组 guardrail，支持并发.

    parallel=True 时，所有 run_in_parallel=True 的 guardrail 并发执行，
    run_in_parallel=False 的顺序执行。
    """
    results: list[GuardrailResult] = []

    if not parallel:
        for g in guardrails:
            results.extend(g.check(ctx))
        return results

    parallel_guards = [g for g in guardrails if g.run_in_parallel]
    sequential_guards = [g for g in guardrails if not g.run_in_parallel]

    if parallel_guards:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(parallel_guards), 4),
        ) as pool:
            futures = {pool.submit(g.check, ctx): g for g in parallel_guards}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception as exc:
                    g = futures[future]
                    results.append(
                        GuardrailResult(
                            guardrail_name=g.name,
                            passed=False,
                            level=GuardrailLevel.WARNING,
                            message=f"Guardrail {g.name} 执行异常: {exc}",
                        )
                    )

    for g in sequential_guards:
        results.extend(g.check(ctx))

    return results
