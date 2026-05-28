"""Harness Ablation Matrix：记录每个 harness 组件的收益/成本.

支持 compact/full/review-heavy 等 profile，
模型升级后逐个 stress test，删掉不再 load-bearing 的组件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from dqg.log import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Harness 组件注册表
# ---------------------------------------------------------------------------


@dataclass
class HarnessComponent:
    """单个 harness 组件."""

    name: str
    category: str  # execute_handler / finalize_handler / finalize_gate / quality
    description: str
    phases: set[str] = field(default_factory=set)  # 空 = 所有 Phase
    avg_cost_tokens: int = 0
    avg_duration_ms: int = 0
    load_bearing: bool = True  # 是否仍然 load-bearing
    ablation_notes: str = ""


# 所有已注册的 harness 组件
HARNESS_COMPONENTS: Final = MappingProxyType(
    {
        # Execute handlers
        "phase_contract": HarnessComponent(
            "phase_contract", "execute_handler", "生成执行合同", avg_cost_tokens=0, avg_duration_ms=50
        ),
        "diff_context": HarnessComponent(
            "diff_context",
            "execute_handler",
            "增量 diff 上下文",
            phases={"Q06", "Q07"},
            avg_cost_tokens=500,
            avg_duration_ms=200,
        ),
        "weak_assert": HarnessComponent(
            "weak_assert",
            "execute_handler",
            "弱断言 tree-sitter 检测",
            phases={"Q06"},
            avg_cost_tokens=300,
            avg_duration_ms=500,
        ),
        "coverage_matrix": HarnessComponent(
            "coverage_matrix",
            "execute_handler",
            "覆盖度矩阵自动生成",
            phases={"Q04"},
            avg_cost_tokens=200,
            avg_duration_ms=100,
        ),
        "business_mutations": HarnessComponent(
            "business_mutations",
            "execute_handler",
            "业务域变异规则",
            phases={"Q06"},
            avg_cost_tokens=400,
            avg_duration_ms=100,
        ),
        "blast_radius": HarnessComponent(
            "blast_radius",
            "execute_handler",
            "代码改动影响范围",
            phases={"Q05", "Q05a", "Q05b", "Q06"},
            avg_cost_tokens=500,
            avg_duration_ms=1000,
        ),
        "data_patterns": HarnessComponent(
            "data_patterns",
            "execute_handler",
            "故障数据模式注入",
            phases={"Q05", "Q05a", "Q05b", "Q06"},
            avg_cost_tokens=300,
            avg_duration_ms=100,
        ),
        "se_code_mapping": HarnessComponent(
            "se_code_mapping",
            "execute_handler",
            "SE→Code 自动映射",
            phases={"Q05", "Q05a", "Q05b", "Q06", "Q07"},
            avg_cost_tokens=500,
            avg_duration_ms=2000,
        ),
        "code_skeleton": HarnessComponent(
            "code_skeleton",
            "execute_handler",
            "TREEFRAG 代码骨架压缩",
            phases={"Q07"},
            avg_cost_tokens=0,
            avg_duration_ms=500,
        ),
        "demand_trace": HarnessComponent(
            "demand_trace",
            "execute_handler",
            "需求驱动代码路径追踪",
            phases={"Q07"},
            avg_cost_tokens=0,
            avg_duration_ms=1000,
        ),
        "requirement_smell": HarnessComponent(
            "requirement_smell",
            "execute_handler",
            "需求异味检测",
            phases={"Q01"},
            avg_cost_tokens=0,
            avg_duration_ms=50,
        ),
        "requirement_graph": HarnessComponent(
            "requirement_graph",
            "finalize_handler",
            "需求层级图 GAP 检测",
            phases={"Q01"},
            avg_cost_tokens=0,
            avg_duration_ms=100,
        ),
        "overcorrection_guard": HarnessComponent(
            "overcorrection_guard", "quality", "Judge 过严误报检测", avg_cost_tokens=0, avg_duration_ms=50
        ),
        # Finalize handlers
        "review_chain": HarnessComponent(
            "review_chain", "finalize_handler", "Judge/Critique prompt 生成", avg_cost_tokens=2000, avg_duration_ms=500
        ),
        "verification_bundle": HarnessComponent(
            "verification_bundle", "finalize_handler", "统一验证包收集", avg_cost_tokens=0, avg_duration_ms=100
        ),
        "skill_factory": HarnessComponent(
            "skill_factory", "finalize_handler", "Skill 规则建议生成", avg_cost_tokens=500, avg_duration_ms=200
        ),
        "skill_evolution": HarnessComponent(
            "skill_evolution", "finalize_handler", "Skill 进化 diff", avg_cost_tokens=300, avg_duration_ms=200
        ),
        "score_calibration": HarnessComponent(
            "score_calibration", "finalize_handler", "DeepEval 评分校准", avg_cost_tokens=1000, avg_duration_ms=5000
        ),
        "eval_baseline": HarnessComponent(
            "eval_baseline", "finalize_handler", "量化质量基线", avg_cost_tokens=0, avg_duration_ms=100
        ),
        "golden_sample": HarnessComponent(
            "golden_sample", "finalize_handler", "Golden Sample 对比", avg_cost_tokens=0, avg_duration_ms=200
        ),
        "rule_compliance": HarnessComponent(
            "rule_compliance", "finalize_handler", "规则执行率检查", avg_cost_tokens=0, avg_duration_ms=100
        ),
        # Finalize gates
        "reasoning_log": HarnessComponent(
            "reasoning_log", "finalize_gate", "推理日志存在性检查", avg_cost_tokens=0, avg_duration_ms=10
        ),
        "no_regression": HarnessComponent(
            "no_regression", "finalize_gate", "产物数量防回退", avg_cost_tokens=0, avg_duration_ms=10
        ),
        "compile_check": HarnessComponent(
            "compile_check",
            "finalize_gate",
            "编译验证",
            phases={"Q05", "Q05b"},
            avg_cost_tokens=0,
            avg_duration_ms=30000,
        ),
        "coverage_gate": HarnessComponent(
            "coverage_gate", "finalize_gate", "覆盖率门禁", phases={"Q06"}, avg_cost_tokens=0, avg_duration_ms=1000
        ),
        "auto_checks": HarnessComponent(
            "auto_checks", "finalize_gate", "AutoHarness 自动校验", avg_cost_tokens=0, avg_duration_ms=200
        ),
    }
)


# ---------------------------------------------------------------------------
# Harness Profile
# ---------------------------------------------------------------------------

HARNESS_PROFILES: Final = MappingProxyType(
    {
        "full": {name: True for name in HARNESS_COMPONENTS},
        "compact": {
            "phase_contract": True,
            "diff_context": True,
            "weak_assert": True,
            "review_chain": True,
            "verification_bundle": True,
            "reasoning_log": True,
            "no_regression": True,
            "compile_check": True,
            "coverage_gate": True,
            "auto_checks": True,
            # 关闭的
            "coverage_matrix": False,
            "business_mutations": False,
            "blast_radius": False,
            "data_patterns": False,
            "se_code_mapping": False,
            "code_skeleton": False,
            "demand_trace": False,
            "requirement_smell": False,
            "requirement_graph": False,
            "overcorrection_guard": False,
            "skill_factory": False,
            "skill_evolution": False,
            "score_calibration": False,
            "eval_baseline": False,
            "golden_sample": False,
            "rule_compliance": False,
        },
        "review-heavy": {
            **{name: True for name in HARNESS_COMPONENTS},
            # 额外强化评审
            "score_calibration": True,
            "eval_baseline": True,
            "golden_sample": True,
            "rule_compliance": True,
        },
    }
)


def get_active_components(profile: str = "full", phase_id: str = "") -> list[str]:
    """获取指定 profile 下的活跃组件列表."""
    profile_config = HARNESS_PROFILES.get(profile, HARNESS_PROFILES["full"])
    active = []
    for name, enabled in profile_config.items():
        if not enabled:
            continue
        comp = HARNESS_COMPONENTS.get(name)
        if comp and (not comp.phases or phase_id in comp.phases):
            active.append(name)
    return active


def estimate_cost(profile: str = "full", phase_id: str = "") -> dict[str, Any]:
    """估算指定 profile 的成本."""
    active = get_active_components(profile, phase_id)
    total_tokens = sum(HARNESS_COMPONENTS[n].avg_cost_tokens for n in active)
    total_ms = sum(HARNESS_COMPONENTS[n].avg_duration_ms for n in active)

    return {
        "profile": profile,
        "phase_id": phase_id,
        "active_components": len(active),
        "total_components": len(HARNESS_COMPONENTS),
        "estimated_tokens": total_tokens,
        "estimated_duration_ms": total_ms,
        "components": active,
    }


def format_ablation_report() -> str:
    """生成 ablation 报告."""
    lines = [
        "# Harness Ablation Matrix",
        "",
        "| Component | Category | Phases | Tokens | Duration | Load-bearing |",
        "|-----------|----------|--------|--------|----------|-------------|",
    ]

    for name, comp in sorted(HARNESS_COMPONENTS.items(), key=lambda x: x[1].category):
        phases = ", ".join(sorted(comp.phases)) if comp.phases else "all"
        lb = "YES" if comp.load_bearing else "NO"
        lines.append(
            f"| {name} | {comp.category} | {phases} | {comp.avg_cost_tokens} | {comp.avg_duration_ms}ms | {lb} |"
        )

    lines.append("")
    lines.append("## Profiles")
    for profile_name in HARNESS_PROFILES:
        cost = estimate_cost(profile_name)
        lines.append(
            f"- **{profile_name}**: {cost['active_components']} components, ~{cost['estimated_tokens']} tokens, ~{cost['estimated_duration_ms']}ms"
        )

    return "\n".join(lines)
