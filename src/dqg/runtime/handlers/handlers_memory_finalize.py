"""Memory finalize handler 注册（独立文件以满足行数门禁）."""

from __future__ import annotations

from dqg.memory.garden import handle_memory_garden_finalize
from dqg.runtime.lifecycle import register_handler


def register_memory_garden_handler() -> None:
    register_handler(
        "memory_garden",
        handle_memory_garden_finalize,
        stage="finalize",
        order=35,
        depends_on=["memory_index"],
    )
