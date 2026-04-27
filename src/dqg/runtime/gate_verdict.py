"""GateVerdict: 统一卡控层 — 汇总所有检查结果为单一决策.

所有检查（flow_integrity、schema、phase_constraints、handler errors、
guardrail、language compile_check）结果汇入一个 verdict。
approve 命令只读 _gate_verdict.json 做决策。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from dqg.runtime.result import PhaseResult

log = get_logger(__name__)


@dataclass
class CheckItem:
    """单个检查项结果."""

    source: str  # flow_integrity | schema | phase_constraints | handler | guardrail | language
    name: str
    passed: bool
    level: Literal["HARD", "SOFT"]  # HARD 不可绕过，SOFT 可 --force
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateVerdict:
    """Phase 卡控汇总结果."""

    phase_id: str
    timestamp: str = ""
    checks: list[CheckItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    @property
    def hard_blocked(self) -> bool:
        return any(not c.passed and c.level == "HARD" for c in self.checks)

    @property
    def soft_blocked(self) -> bool:
        return any(not c.passed and c.level == "SOFT" for c in self.checks)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def hard_failures(self) -> list[CheckItem]:
        return [c for c in self.checks if not c.passed and c.level == "HARD"]

    @property
    def soft_failures(self) -> list[CheckItem]:
        return [c for c in self.checks if not c.passed and c.level == "SOFT"]

    def to_dict(self) -> dict[str, Any]:
        hf = self.hard_failures
        sf = self.soft_failures
        return {
            "phase_id": self.phase_id,
            "timestamp": self.timestamp,
            "passed": self.passed,
            "hard_blocked": len(hf) > 0,
            "soft_blocked": len(sf) > 0,
            "checks": [asdict(c) for c in self.checks],
            "summary": {
                "total": len(self.checks),
                "passed": sum(1 for c in self.checks if c.passed),
                "hard_failures": len(hf),
                "soft_failures": len(sf),
            },
        }


def build_verdict(
    phase_id: str,
    result: PhaseResult,
    guardrail_results: list[dict[str, Any]] | None = None,
    constraint_violations: list[dict[str, Any]] | None = None,
    schema_errors: list[str] | None = None,
) -> GateVerdict:
    """从各检查源构建 GateVerdict.

    Args:
        phase_id: Phase ID
        result: PhaseResult（含 errors/warnings from handlers + flow_integrity）
        guardrail_results: _guardrail_results.json 内容
        constraint_violations: enforce_phase_constraints() 返回值
        schema_errors: Schema validation errors（HARD 级别，不可 --force 绕过）
    """
    verdict = GateVerdict(phase_id=phase_id)

    # 0. Schema validation errors → HARD (不可 --force 绕过)
    for err in schema_errors or []:
        if "不存在" in err:
            continue
        verdict.checks.append(
            CheckItem(
                source="schema",
                name="schema_validation",
                passed=False,
                level="HARD",
                message=err,
            )
        )

    # 1. Handler errors → HARD (required handler) 或 SOFT (optional)
    for error in result.errors:
        is_required = error.startswith("BLOCKED:")
        verdict.checks.append(
            CheckItem(
                source="handler",
                name=_extract_handler_name(error),
                passed=False,
                level="HARD" if is_required else "SOFT",
                message=error,
            )
        )

    # 2. Handler warnings → SOFT
    for warning in result.warnings:
        verdict.checks.append(
            CheckItem(
                source="handler",
                name=_extract_handler_name(warning),
                passed=False,
                level="SOFT",
                message=warning,
            )
        )

    # 3. Guardrail results
    for g in guardrail_results or []:
        level_map = {"blocked": "HARD", "warning": "SOFT", "info": "SOFT"}
        verdict.checks.append(
            CheckItem(
                source="guardrail",
                name=g.get("guardrail", "unknown"),
                passed=g.get("passed", True),
                level=level_map.get(g.get("level", "info"), "SOFT"),
                message=g.get("message", ""),
                details=g.get("details", {}),
            )
        )

    # 4. Phase Constraints violations
    for v in constraint_violations or []:
        verdict.checks.append(
            CheckItem(
                source="phase_constraints",
                name=v.get("label", v.get("metric", "unknown")),
                passed=False,
                level="HARD" if v.get("block_if_fail") else "SOFT",
                message=_format_constraint_message(v),
                details=v,
            )
        )

    return verdict


def save_verdict(output_dir: Path, project_id: str, phase_id: str, verdict: GateVerdict) -> Path | None:
    """写入 _gate_verdict.json."""
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        log.warning("Unknown phase %s, cannot save verdict", phase_id)
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_gate_verdict.json"
    from dqg.json_utils import save_json

    save_json(path, verdict.to_dict())
    log.info("GateVerdict saved: %s (passed=%s)", path, verdict.passed)
    return path


def load_verdict(output_dir: Path, project_id: str, phase_id: str) -> GateVerdict | None:
    """读取 _gate_verdict.json."""
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    path = _phase_dir(output_dir, project_id, phase_def) / "_gate_verdict.json"
    if not path.exists():
        return None

    try:
        from dqg.json_utils import load_json

        data = load_json(path)
    except Exception:
        log.warning("Failed to load verdict: %s", path, exc_info=True)
        return None

    if not data:
        return None

    verdict = GateVerdict(phase_id=data.get("phase_id", phase_id), timestamp=data.get("timestamp", ""))
    for c in data.get("checks", []):
        verdict.checks.append(
            CheckItem(
                source=c.get("source", "unknown"),
                name=c.get("name", "unknown"),
                passed=c.get("passed", False),
                level=c.get("level", "SOFT"),
                message=c.get("message", ""),
                details=c.get("details", {}),
            )
        )
    return verdict


def _extract_handler_name(msg: str) -> str:
    """从 error/warning 消息中提取 handler 名称."""
    for prefix in ("BLOCKED: required handler ", "Handler "):
        if msg.startswith(prefix):
            rest = msg[len(prefix) :]
            parts = rest.split(" ", 1)
            if parts:
                return parts[0]
    return "unknown"


def _format_constraint_message(v: dict[str, Any]) -> str:
    """格式化约束违反消息."""
    actual = v.get("actual")
    actual_str = "N/A" if actual is None else str(actual)
    reason = f" ({v['reason']})" if v.get("reason") else ""
    return f"{v.get('label', '?')}: 实际值 {actual_str} {v.get('op', '?')} {v.get('threshold', '?')} 不满足{reason}"
