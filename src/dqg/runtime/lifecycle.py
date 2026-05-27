"""Lifecycle handler 注册机制：execute/finalize 的 sidecar 逻辑下沉为独立 handler.

每个 handler 是一个函数，签名为 (ctx: ExecutionContext, result: PhaseResult) -> None。
handler 按依赖关系分组并行执行，无依赖的 handler 同时运行。
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


class LifecycleHandler(Protocol):
    """Handler 协议：接收执行上下文和结果对象."""

    def __call__(self, ctx: ExecutionContext, result: PhaseResult) -> None: ...


# Pre-execute 检查函数：返回 True 表示终止整个 execute（跳过所有 handler）
PreCheckFn = Callable[["ExecutionContext", "PhaseResult"], bool]


@dataclass
class HandlerRegistration:
    """Handler 注册条目."""

    name: str
    handler: LifecycleHandler
    phases: set[str] | None = None  # None = 所有 Phase 都执行
    stage: str = "execute"  # "execute" | "finalize"
    order: int = 100  # 越小越先执行
    depends_on: list[str] = field(default_factory=list)  # 依赖的 handler 名称
    required: bool = False  # True = 失败时 BLOCKED，False = 失败时 WARNING
    gate: bool = False  # True = 失败时跳过所有直接/间接下游（硬门禁语义）


class LifecycleRegistry:
    """Handler 注册表：管理 execute/finalize 阶段的 sidecar handler."""

    def __init__(self) -> None:
        self._handlers: list[HandlerRegistration] = []

    def register(
        self,
        name: str,
        handler: LifecycleHandler,
        stage: str = "execute",
        phases: set[str] | None = None,
        order: int = 100,
        depends_on: list[str] | None = None,
        required: bool = False,
        gate: bool = False,
    ) -> None:
        self._handlers.append(
            HandlerRegistration(
                name=name,
                handler=handler,
                phases=phases,
                stage=stage,
                order=order,
                depends_on=depends_on or [],
                required=required,
                gate=gate,
            )
        )

    def get_handlers(self, stage: str, phase_id: str) -> list[HandlerRegistration]:
        """获取指定阶段和 Phase 的 handler 列表（按 order 排序）."""
        matched = []
        for reg in self._handlers:
            if reg.stage != stage:
                continue
            if reg.phases is not None and phase_id not in reg.phases:
                continue
            matched.append(reg)
        matched.sort(key=lambda r: r.order)
        return matched

    def run_handlers(
        self,
        stage: str,
        ctx: ExecutionContext,
        result: PhaseResult,
    ) -> None:
        """执行所有匹配的 handler（依赖图驱动并行）.

        无依赖声明时按 order 串行执行（向后兼容）。
        有依赖声明时，同一层内的独立 handler 并行执行。
        """
        from dqg.runtime.events import EventType

        handlers = self.get_handlers(stage, ctx.phase_id)
        if not handlers:
            return

        # 如果没有任何 handler 声明了 depends_on，走快速串行路径
        has_deps = any(h.depends_on for h in handlers)
        if not has_deps:
            for reg in handlers:
                try:
                    reg.handler(ctx, result)
                    result.add_event(
                        EventType.SIDECAR_COMPLETED,
                        f"{reg.name} completed",
                        handler=reg.name,
                    )
                except Exception as exc:
                    if reg.required:
                        result.add_error(f"BLOCKED: required handler {reg.name} failed: {exc}")
                    else:
                        result.add_warning(f"Handler {reg.name} failed: {exc}")
            return

        # 有依赖声明：构建依赖图，分层并行执行
        by_name: dict[str, HandlerRegistration] = {h.name: h for h in handlers}
        active_names = set(by_name.keys())

        deps: dict[str, set[str]] = {}
        for h in handlers:
            deps[h.name] = {d for d in h.depends_on if d in active_names}

        completed_names: set[str] = set()
        gate_failed_names: set[str] = set()  # gate=True 的 handler 失败后加入，传播跳过下游
        result_lock = threading.Lock()

        def _run_one(reg: HandlerRegistration) -> tuple[str, Exception | None]:
            try:
                reg.handler(ctx, result)
                with result_lock:
                    result.add_event(
                        EventType.SIDECAR_COMPLETED,
                        f"{reg.name} completed",
                        handler=reg.name,
                    )
                return reg.name, None
            except Exception as exc:
                with result_lock:
                    if reg.gate:
                        gate_failed_names.add(reg.name)
                    if reg.required:
                        result.add_error(f"BLOCKED: required handler {reg.name} failed: {exc}")
                    else:
                        result.add_warning(f"Handler {reg.name} failed: {exc}")
                return reg.name, exc

        remaining = set(active_names)
        while remaining:
            ready = sorted(
                [n for n in remaining if deps[n].issubset(completed_names)],
                key=lambda n: by_name[n].order,
            )

            # 优先处理：deps 中含 gate 失败的 handler → 跳过并传播
            gate_blocked = [n for n in ready if deps[n] & gate_failed_names]
            if gate_blocked:
                for n in gate_blocked:
                    failed_gate_deps = sorted(deps[n] & gate_failed_names)
                    with result_lock:
                        result.add_warning(f"Handler {n} skipped: hard gate failed in {', '.join(failed_gate_deps)}")
                    gate_failed_names.add(n)  # 传播：本 handler 也视为 gate 失败
                    completed_names.add(n)  # 标记完成，避免其下游进入死锁路径
                    remaining.discard(n)
                continue  # 重新评估 remaining

            if not ready:
                # 依赖死锁：剩余 handler 的依赖无法满足（非 gate 原因）
                unresolved = {n: deps[n] - completed_names for n in remaining}
                for name, missing in unresolved.items():
                    reg = by_name[name]
                    with result_lock:
                        if reg.required:
                            result.add_error(
                                f"BLOCKED: required handler {name} 依赖未满足: {', '.join(sorted(missing))}",
                            )
                        else:
                            result.add_warning(
                                f"Handler {name} 依赖未满足: {', '.join(sorted(missing))}，已跳过",
                            )
                break

            if len(ready) == 1:
                name, _exc = _run_one(by_name[ready[0]])
                completed_names.add(name)
                remaining.discard(name)
                continue

            with ThreadPoolExecutor(max_workers=min(len(ready), 6)) as pool:
                futures = {pool.submit(_run_one, by_name[name]): name for name in ready}
                for future in as_completed(futures):
                    name, _exc = future.result()
                    completed_names.add(name)
                    remaining.discard(name)


# 全局注册表实例
_registry = LifecycleRegistry()

# Pre-execute 检查注册表：phase_id → list[PreCheckFn]
_pre_checks: dict[str, list[PreCheckFn]] = {}


def get_registry() -> LifecycleRegistry:
    return _registry


def register_pre_check(phase_id: str, fn: PreCheckFn) -> None:
    """注册 pre-execute 检查函数.

    fn 返回 True 时终止整个 execute 阶段（跳过所有 lifecycle handler）。
    用于 Q06 编译预检等"失败则无需运行 LLM"的快速门禁。
    """
    _pre_checks.setdefault(phase_id, []).append(fn)


def run_pre_checks(ctx: ExecutionContext, result: PhaseResult) -> bool:
    """运行当前 Phase 的所有 pre-execute 检查. 返回 True 表示应终止 execute."""
    return any(fn(ctx, result) for fn in _pre_checks.get(ctx.phase_id, []))


def register_handler(
    name: str,
    handler: LifecycleHandler,
    stage: str = "execute",
    phases: set[str] | None = None,
    order: int = 100,
    depends_on: list[str] | None = None,
    required: bool = False,
    gate: bool = False,
) -> None:
    """便捷注册函数."""
    _registry.register(name, handler, stage, phases, order, depends_on, required, gate)
