"""Phase-map 生成器：为上游 Phase 产物生成 ≤2KB 轻量索引.

aider repo-map 思路的 DQG 移植：在 _upstream_context.md 之前注入一份
结构性摘要（SE-id 列表、EUT 统计、覆盖率摘要），让 worker LLM 在读全文
之前先建立全局感知，减少注意力稀释。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# target_phase → 需要为哪些上游 Phase 生成 map
_UPSTREAM_MAP: dict[str, list[str]] = {
    "Q04": ["Q01"],
    "Q05": ["Q01"],
    "Q05a": ["Q01"],
    "Q05b": ["Q05a"],
    "Q06": ["Q05a", "Q01"],
    "Q07": ["Q01"],
}


def _map_q01(data: dict[str, Any]) -> str:
    """Q01 structured JSON → 紧凑 SE/REQ 索引."""
    ses = data.get("semantic_expectations", [])
    reqs = data.get("requirements", [])
    opens = data.get("open_items", [])

    total_se = len(ses)
    se_ids = [s.get("se_id", "") for s in ses]

    # 分类：category 含"异常"/"恢复"/"容错"的 SE 优先展示
    exception_ses = [
        s["se_id"]
        for s in ses
        if any(
            k in s.get("category", "") + s.get("description", "")
            for k in ("异常", "恢复", "容错", "rollback", "retry", "idempoten")
        )
    ]

    req_count = sum(1 for r in reqs if r.get("req_id", "").startswith("REQ-"))
    br_count = sum(1 for r in reqs if r.get("req_id", "").startswith("BR-"))

    lines = [
        "## SE Map (Q01)",
        f"SEs: {total_se} 条 | REQ: {req_count} / BR: {br_count}",
    ]
    if se_ids:
        lines.append(f"All SE-ids: {', '.join(se_ids[:30])}" + (" ..." if len(se_ids) > 30 else ""))
    if exception_ses:
        lines.append(f"异常/幂等 SE（Q06 重点审计）: {', '.join(exception_ses[:10])}")
    if opens:
        open_ids = [o.get("open_id", "") for o in opens]
        lines.append(f"OPEN items: {', '.join(open_ids)} — 相关 EUT 可能受影响")
    return "\n".join(lines)


def _map_q05a(data: dict[str, Any]) -> str:
    """Q05a structured JSON (phase_b_structured.json) → EUT 索引."""
    euts = data.get("audit_items", [])
    if not euts:
        # 兼容 PhaseBOutput.eut_items 字段名
        euts = data.get("eut_items", [])

    total = len(euts)
    if total == 0:
        return "## EUT Map (Q05a)\n(无 EUT 条目)"

    passed = sum(1 for e in euts if e.get("audit_status") == "COVERED" or e.get("status") == "pass")
    pending = [
        e.get("eut_id", e.get("id", "?"))
        for e in euts
        if e.get("audit_status") not in ("COVERED",) and e.get("status") not in ("pass",)
    ]

    # 标记 weak-assert 或 high-risk 的 EUT（Q06 审计重点）
    weak = [e.get("eut_id", e.get("id", "?")) for e in euts if e.get("weak_assert") or e.get("risk_tier") == "high"]

    lines = [
        "## EUT Map (Q05a)",
        f"EUTs: {total} 条 | PASS: {passed} / 其余: {total - passed}",
    ]
    if pending:
        display = pending[:15]
        lines.append(
            f"非 PASS EUTs: {', '.join(display)}" + (f" ...({len(pending) - 15} more)" if len(pending) > 15 else "")
        )
    if weak:
        lines.append(f"弱断言/高风险 EUTs（Q06 重点）: {', '.join(weak[:10])}")
    return "\n".join(lines)


def _map_q06(data: dict[str, Any]) -> str:
    """Q06 structured JSON → 覆盖率摘要（用于 Q07 上下文）."""
    items = data.get("audit_items", [])
    covered = sum(1 for i in items if i.get("audit_status") == "COVERED")
    uncov = [i.get("eut_id", "?") for i in items if i.get("audit_status") == "UNCOVERED"]
    partial = sum(1 for i in items if i.get("audit_status") == "PARTIAL")
    gate = data.get("coverage_gate", {})

    lines = [
        "## Q06 Coverage Map",
        f"COVERED: {covered} / UNCOVERED: {len(uncov)} / PARTIAL: {partial}",
    ]
    if uncov:
        lines.append(
            f"UNCOVERED EUTs: {', '.join(uncov[:10])}" + (f" ...({len(uncov) - 10} more)" if len(uncov) > 10 else "")
        )
    if gate:
        lines.append(f"Coverage gate: {gate}")
    return "\n".join(lines)


_PHASE_GENERATORS = {
    "Q01": _map_q01,
    "Q05a": _map_q05a,
    "Q06": _map_q06,
}


def generate_phase_map(output_dir: Path, project_id: str, target_phase: str) -> str | None:
    """生成 target_phase 需要的上游 phase-map，返回 Markdown 字符串或 None."""
    from dqg.constants import STRUCTURED_JSON_MAP
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _pd

    upstream_phases = _UPSTREAM_MAP.get(target_phase, [])
    if not upstream_phases:
        return None

    sections: list[str] = [
        f"# Phase Map — {target_phase} 上游摘要\n_此索引由 phase_map.py 自动生成，供 worker 快速感知上游结构_\n"
    ]

    for up_phase in upstream_phases:
        src_file = STRUCTURED_JSON_MAP.get(up_phase)
        if not src_file:
            continue
        phase_def = PHASE_DEFS.get(up_phase, {})
        pd = _pd(output_dir, project_id, phase_def)
        src = pd / src_file
        if not src.exists():
            # 也尝试 planning_snapshot
            src = pd / "_internal" / f"planning_snapshot_{up_phase}.json"
        if not src.exists():
            log.debug("phase_map: %s not found for upstream %s", src_file, up_phase)
            continue

        data = load_json(src)
        if not data:
            continue

        gen = _PHASE_GENERATORS.get(up_phase)
        if gen:
            try:
                section = gen(data)
                sections.append(section)
            except Exception as e:
                log.debug("phase_map generator failed for %s: %s", up_phase, e)

    if len(sections) == 1:
        return None  # 只有标题，没有实质内容

    result = "\n\n".join(sections)
    # 保守截断：避免 phase-map 本身消耗太多 token
    if len(result) > 3000:
        result = result[:3000] + "\n...(phase-map truncated)"
    return result
