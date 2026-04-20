"""Runtime 结构化结果：替代 print + exit code 的机器可消费输出."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dqg.runtime.events import EventType


@dataclass
class RuntimeEvent:
    """单个生命周期事件."""

    event_type: EventType
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"event": self.event_type.value, "message": self.message}
        if self.data:
            d["data"] = self.data
        return d


@dataclass
class PhaseResult:
    """Phase execute/finalize/approve 的结构化返回值.

    替代原来的 int exit code + print side effect。
    CLI 层根据 success 决定 exit code，根据 events 决定输出内容。
    CI/API 层直接消费 to_dict()。
    """

    success: bool = True
    phase_id: str = ""
    action: str = ""  # "execute" | "finalize" | "approve" | "skip"
    events: list[RuntimeEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)  # name → path

    def add_event(
        self,
        event_type: EventType,
        message: str = "",
        **data: Any,
    ) -> None:
        self.events.append(RuntimeEvent(event_type, message, data))

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.success = False
        self.events.append(RuntimeEvent(EventType.ERROR, msg))

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        self.events.append(RuntimeEvent(EventType.WARNING, msg))

    def add_artifact(self, name: str, path: str) -> None:
        self.artifacts[name] = path

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "phase_id": self.phase_id,
            "action": self.action,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "events": [e.to_dict() for e in self.events],
        }
