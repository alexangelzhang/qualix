"""GateVerdict: 统一卡控层 — 汇总所有检查结果为单一决策.

所有检查（flow_integrity、schema、phase_constraints、handler errors、
guardrail、language compile_check）结果汇入一个 verdict。
approve 命令只读 _gate_verdict.json 做决策。
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from qualix.runtime.result import PhaseResult

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
    why: str = ""  # 这条规则存在的原因（降低误报投诉和 --force 冲动）
    evidence: str = ""  # 正确做法示例


# 静态 why 注册表：(source, name) → why / evidence
# 优先查精确 (source, name)，找不到退回 (source, "*")
_WHY_REGISTRY: dict[tuple[str, str], dict[str, str]] = {
    ("schema", "schema_validation"): {
        "why": "结构化 JSON 字段违反 Pydantic 约束；下游 Phase 读取时会解析失败，导致审计结果无法追溯",
        "evidence": "缺少必填字段 / 字段类型错误 / enum 值不在允许范围内",
    },
    ("guardrail", "semantic_guardrail"): {
        "why": "报告含泛化描述或幻觉内容，无法作为可验证证据；下游门禁依赖此报告做决策",
        "evidence": "坏: '系统整体设计合理'  好: '类 X.method() 缺少空指针断言，见 L42'",
    },
    ("guardrail", "rationalization_guard"): {
        "why": "Judge 评分被合理化稀释，导致低质量产物通过门禁",
        "evidence": "检测到: '虽然...但', '总体来说', '可以接受' 等规避表达",
    },
    ("guardrail", "fabrication_detector"): {
        "why": "报告中引用了不存在的类/方法/行号（幻觉输出），会直接误导开发者",
        "evidence": "坏: 'MockService.verify() L88'（实际无此方法）  好: '[来源: OrderService.java:88]'",
    },
    ("handler", "critique_closure"): {
        "why": "Judge+Critique 双轨制是质量闭环核心；仅有 Judge 会漏掉其盲区",
        "evidence": "_critique.json 不存在，说明 Critique agent 未完成或未触发",
    },
    ("handler", "flow_integrity"): {
        "why": "产物 core_arrays 为空时下游 Phase 审计结论无数据支撑",
        "evidence": "audit_items / semantic_expectations 等数组为空，检查 worker 是否输出了结构化 JSON",
    },
    ("phase_constraints", "*"): {
        "why": "Phase 业务指标不达标；达标线来自 phase_registry 配置，代表最低可接受质量",
        "evidence": "运行 qualix-run spec --phase <phase_id> --json 查看 contract.hard_checks 确认阈值",
    },
    ("language", "*"): {
        "why": "代码在 LLM 审计前必须可编译；编译失败的代码无法产生有意义的覆盖率分析",
        "evidence": "运行 mvn test-compile（Java）修复编译错误后重新 execute",
    },
    ("schema", "*"): {
        "why": "产物 JSON 不符合 Phase schema 约束，下游消费方无法正确解析",
        "evidence": "运行 qualix-run spec --phase <phase_id> --json 查看 json_schema 字段要求",
    },
}


def _enrich_why(item: CheckItem) -> CheckItem:
    """用 _WHY_REGISTRY 填充 CheckItem 的 why/evidence（已有值则不覆盖）."""
    if item.why:
        return item
    entry = _WHY_REGISTRY.get((item.source, item.name)) or _WHY_REGISTRY.get((item.source, "*"))
    if entry:
        item.why = entry.get("why", "")
        item.evidence = entry.get("evidence", "")
    return item


@dataclass
class GateVerdict:
    """Phase 卡控汇总结果."""

    phase_id: str
    timestamp: str = ""
    checks: list[CheckItem] = field(default_factory=list)
    upstream_hashes: dict[str, str] = field(default_factory=dict)

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
            "upstream_hashes": self.upstream_hashes,
            "summary": {
                "total": len(self.checks),
                "passed": sum(1 for c in self.checks if c.passed),
                "hard_failures": len(hf),
                "soft_failures": len(sf),
            },
        }

    def is_stale(self, output_dir: Path, project_id: str) -> bool:
        """上游产物是否已变更（哈希不匹配则 stale）."""
        if not self.upstream_hashes:
            return False
        base = output_dir / project_id
        for rel_path, saved_hash in self.upstream_hashes.items():
            current = compute_file_hash(base / rel_path)
            if current != saved_hash:
                return True
        return False


def load_rule_overrides(base_dir: Path) -> dict[str, set[str]]:
    """读取 <base_dir>/.dqg/rule_overrides.yaml 的项目级规则豁免配置.

    格式::

        disable:
          - schema_validation      # 完全豁免（passed=True）
        warn_only:
          - semantic_guardrail     # HARD → SOFT 降级

    返回 {key: set(lower-cased names)} 供 O(1) 查找。
    匹配策略：按 CheckItem.name 精确匹配（大小写不敏感）。
    """
    import yaml

    override_path = base_dir / ".dqg" / "rule_overrides.yaml"
    if not override_path.exists():
        return {}
    try:
        text = override_path.read_text(encoding="utf-8")
    except OSError as e:
        log.warning("load_rule_overrides: cannot read %s: %s", override_path, e)
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        # 格式错误不能静默：豁免规则全部失效会导致 HARD check 意外阻断
        raise RuntimeError(
            f"rule_overrides.yaml 解析失败，豁免规则已全部失效。\n请检查 {override_path} 的 YAML 语法。\n原因: {e}"
        ) from e
    if not isinstance(data, dict):
        return {}
    return {
        "disable": {s.lower() for s in data.get("disable", []) if isinstance(s, str)},
        "warn_only": {s.lower() for s in data.get("warn_only", []) if isinstance(s, str)},
    }


def _apply_overrides(checks: list[CheckItem], overrides: dict[str, set[str]]) -> list[CheckItem]:
    """把 rule_overrides 应用到 CheckItem 列表（失败项降级/豁免）.

    返回新列表；被豁免的项用 dataclasses.replace 生成副本，不修改原对象。
    """
    if not overrides:
        return checks
    disable_set = overrides.get("disable", set())
    warn_only_set = overrides.get("warn_only", set())
    result = []
    for item in checks:
        if not item.passed:
            name_lower = item.name.lower()
            if name_lower in disable_set:
                item = dc_replace(item, passed=True, message=f"[project-override: disabled] {item.message}")
                log.info("GateVerdict override: disabled check %s", item.name)
            elif name_lower in warn_only_set and item.level == "HARD":
                item = dc_replace(item, level="SOFT", message=f"[project-override: warn_only] {item.message}")
                log.info("GateVerdict override: downgraded %s to SOFT", item.name)
        result.append(item)
    return result


def build_verdict(
    phase_id: str,
    result: PhaseResult,
    guardrail_results: list[dict[str, Any]] | None = None,
    constraint_violations: list[dict[str, Any]] | None = None,
    schema_errors: list[str] | None = None,
    upstream_hashes: dict[str, str] | None = None,
    rule_overrides: dict[str, set[str]] | None = None,
) -> GateVerdict:
    """从各检查源构建 GateVerdict.

    Args:
        phase_id: Phase ID
        result: PhaseResult（含 errors/warnings from handlers + flow_integrity）
        guardrail_results: _guardrail_results.json 内容
        constraint_violations: enforce_phase_constraints() 返回值
        schema_errors: Schema validation errors（HARD 级别，不可 --force 绕过）
        upstream_hashes: 上游产物文件路径 → MD5 哈希（由 check_cross_phase_refs 提供）
        rule_overrides: load_rule_overrides() 的结果，项目级豁免配置
    """
    verdict = GateVerdict(phase_id=phase_id)
    if upstream_hashes:
        verdict.upstream_hashes = upstream_hashes

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

    for c in verdict.checks:
        _enrich_why(c)

    # 应用项目级 rule_overrides（disable/warn_only）
    if rule_overrides:
        verdict.checks = _apply_overrides(verdict.checks, rule_overrides)

    return verdict


def save_verdict(output_dir: Path, project_id: str, phase_id: str, verdict: GateVerdict) -> Path | None:
    """写入 _gate_verdict.json."""
    from qualix.core.state_machine import PHASE_DEFS
    from qualix.core.state_machine import phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        log.warning("Unknown phase %s, cannot save verdict", phase_id)
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_gate_verdict.json"
    from qualix.json_utils import save_json

    save_json(path, verdict.to_dict())
    log.info("GateVerdict saved: %s (passed=%s)", path, verdict.passed)
    return path


def load_verdict(output_dir: Path, project_id: str, phase_id: str) -> GateVerdict | None:
    """读取 _gate_verdict.json."""
    from qualix.core.state_machine import PHASE_DEFS
    from qualix.core.state_machine import phase_dir as _phase_dir

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    path = _phase_dir(output_dir, project_id, phase_def) / "_gate_verdict.json"
    if not path.exists():
        return None

    try:
        from qualix.json_utils import load_json

        data = load_json(path)
    except Exception:
        log.warning("Failed to load verdict: %s", path, exc_info=True)
        return None

    if not data:
        return None

    verdict = GateVerdict(phase_id=data.get("phase_id", phase_id), timestamp=data.get("timestamp", ""))
    verdict.upstream_hashes = data.get("upstream_hashes", {})
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


def compute_file_hash(path: Path) -> str:
    """计算文件 MD5，文件不存在返回空串."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return ""
