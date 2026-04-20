"""Lifecycle handler 注册机制：execute/finalize 的 sidecar 逻辑下沉为独立 handler.

每个 handler 是一个函数，签名为 (ctx: ExecutionContext, result: PhaseResult) -> None。
handler 按依赖关系分组并行执行，无依赖的 handler 同时运行。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


class LifecycleHandler(Protocol):
    """Handler 协议：接收执行上下文和结果对象."""

    def __call__(self, ctx: ExecutionContext, result: PhaseResult) -> None: ...


@dataclass
class HandlerRegistration:
    """Handler 注册条目."""

    name: str
    handler: LifecycleHandler
    phases: set[str] | None = None  # None = 所有 Phase 都执行
    stage: str = "execute"  # "execute" | "finalize"
    order: int = 100  # 越小越先执行
    depends_on: list[str] = field(default_factory=list)  # 依赖的 handler 名称


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
    ) -> None:
        self._handlers.append(HandlerRegistration(
            name=name,
            handler=handler,
            phases=phases,
            stage=stage,
            order=order,
            depends_on=depends_on or [],
        ))

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
                    result.add_warning(f"Handler {reg.name} failed: {exc}")
            return

        # 有依赖声明：构建依赖图，分层并行执行
        by_name: dict[str, HandlerRegistration] = {h.name: h for h in handlers}
        active_names = set(by_name.keys())

        deps: dict[str, set[str]] = {}
        for h in handlers:
            deps[h.name] = {d for d in h.depends_on if d in active_names}

        completed_names: set[str] = set()
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
                    result.add_warning(f"Handler {reg.name} failed: {exc}")
                return reg.name, exc

        remaining = set(active_names)
        while remaining:
            ready = sorted(
                [n for n in remaining if deps[n].issubset(completed_names)],
                key=lambda n: by_name[n].order,
            )
            if not ready:
                ready = sorted(remaining, key=lambda n: by_name[n].order)

            if len(ready) == 1:
                name, _exc = _run_one(by_name[ready[0]])
                completed_names.add(name)
                remaining.discard(name)
                continue

            with ThreadPoolExecutor(max_workers=min(len(ready), 6)) as pool:
                futures = {
                    pool.submit(_run_one, by_name[name]): name
                    for name in ready
                }
                for future in as_completed(futures):
                    name, _exc = future.result()
                    completed_names.add(name)
                    remaining.discard(name)


# 全局注册表实例
_registry = LifecycleRegistry()


def get_registry() -> LifecycleRegistry:
    return _registry


def register_handler(
    name: str,
    handler: LifecycleHandler,
    stage: str = "execute",
    phases: set[str] | None = None,
    order: int = 100,
    depends_on: list[str] | None = None,
) -> None:
    """便捷注册函数."""
    _registry.register(name, handler, stage, phases, order, depends_on)
