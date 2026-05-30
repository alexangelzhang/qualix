"""ContextPolicy：Domain 层声明 context 加载需求，消除 upstream_collector 里的 if-branches."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContextPolicy:
    """Domain 声明该 Phase 的 context 注入策略.

    upstream_collector 根据此对象决定注入哪些 sidecar，不再使用 if target_phase 分支。
    新增 Phase 只需在 _DEFAULT_POLICIES 里声明策略，core 文件无需修改。
    """

    inject_gap: bool = False
    inject_profile: bool = False
    inject_rsm: bool = True
    inject_diff_context: bool = False
    inject_bug_cases: bool = True


# Phase 默认策略 — single source of truth，替代原 upstream_collector 里散落的集合字面量
_DEFAULT_POLICIES: dict[str, ContextPolicy] = {
    "Q01": ContextPolicy(inject_gap=True, inject_profile=False, inject_rsm=False),
    "Q02": ContextPolicy(inject_gap=False, inject_profile=False, inject_rsm=True, inject_bug_cases=False),
    "Q03": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True),
    "Q04": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True),
    "Q05": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True),
    "Q05a": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True),
    "Q05b": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True),
    "Q06": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True, inject_diff_context=True),
    "Q07": ContextPolicy(inject_gap=False, inject_profile=True, inject_rsm=True, inject_diff_context=True),
}

_registry: dict[str, ContextPolicy] = {}


def register_context_policy(phase_id: str, policy: ContextPolicy) -> None:
    """允许 Domain 模块覆盖默认策略（供测试或未来扩展使用）."""
    _registry[phase_id] = policy


def get_context_policy(phase_id: str) -> ContextPolicy:
    return _registry.get(phase_id) or _DEFAULT_POLICIES.get(phase_id) or ContextPolicy()
