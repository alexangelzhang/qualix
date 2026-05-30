"""Runtime 结构化结果：替代 print + exit code 的机器可消费输出."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from qualix.runtime.events import EventType


class RunStatus(StrEnum):
    """Phase 执行结果的 5 值枚举，区分 infra failure 和 logic failure.

    - ok: 正常完成（不代表质量通过，只代表执行成功）
    - timeout: 网络/LLM 超时等 infra 问题
    - adapter_crashed: Worker/Judge/Critique 适配器崩溃（import 失败、API 异常等）
    - parse_failed: LLM 输出无法解析为结构化格式（JSON parse error、schema 不匹配）
    - tainted: 执行完成但结果被污染（rationalization detected、hallucination flagged）
    """

    OK = "ok"
    TIMEOUT = "timeout"
    ADAPTER_CRASHED = "adapter_crashed"
    PARSE_FAILED = "parse_failed"
    TAINTED = "tainted"

    @property
    def is_infra_failure(self) -> bool:
        """是否为基础设施故障（不应计入质量评分）."""
        return self in (RunStatus.TIMEOUT, RunStatus.ADAPTER_CRASHED)

    @property
    def is_logic_failure(self) -> bool:
        """是否为逻辑层失败（应计入质量评分）."""
        return self in (RunStatus.PARSE_FAILED, RunStatus.TAINTED)


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
    run_status: RunStatus = RunStatus.OK
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

    def add_error(self, msg: str, run_status: RunStatus | None = None) -> None:
        self.errors.append(msg)
        self.success = False
        if run_status is not None:
            self.run_status = run_status
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
            "run_status": self.run_status.value,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "events": [e.to_dict() for e in self.events],
        }
