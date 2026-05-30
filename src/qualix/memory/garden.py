"""Memory Garden（Layer 2）：批量消费 sidecar 队列，构建跨项目链接与语义边."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qualix.constants import MEMORY_GAP_CONTRADICTION_MAX_PAIRS, MEMORY_GARDEN_REPORT, MEMORY_SIDECAR_QUEUE
from qualix.json_utils import save_json
from qualix.log import get_logger
from qualix.memory.knowledge_network import (
    LINK_CONTRADICTS,
    LINK_DERIVED_FROM,
    LINK_SUPERSEDES,
    add_link,
    build_cross_project_links,
    upsert_node,
)
from qualix.store import get_connection

if TYPE_CHECKING:
    from qualix.runtime.execution_context import ExecutionContext
    from qualix.runtime.result import PhaseResult

log = get_logger(__name__)

_TYPE_RANK = {"REQ": 0, "BR": 1, "SE": 2, "GAP": 3, "OPEN": 4}


def _kind_from_fact_title(title: str) -> str:
    m = re.match(r"\[(\w+)\]", title or "")
    return m.group(1) if m else "FACT"


def _memver_prefix(project_id: str, phase_id: str) -> str:
    return f"memver:{project_id}:{phase_id}:"


def _clear_memver_snapshot_nodes(output_dir: Path, project_id: str, phase_id: str) -> None:
    prefix = _memver_prefix(project_id, phase_id) + "%"
    with get_connection(output_dir) as conn:
        conn.execute(
            "DELETE FROM knowledge_links WHERE source_id LIKE ? OR target_id LIKE ?",
            (prefix, prefix),
        )
        conn.execute("DELETE FROM knowledge_nodes WHERE node_id LIKE ?", (prefix,))


def build_supersedes_links(output_dir: Path, project_id: str, phase_id: str) -> int:
    """从 requirement_versions 的 superseded 行生成 SUPERSEDES 边与快照节点."""
    _clear_memver_snapshot_nodes(output_dir, project_id, phase_id)

    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT fact_id, version, description, fact_type, status
               FROM requirement_versions
               WHERE project_id=? AND phase_id=? AND status='superseded'
               ORDER BY fact_id, version""",
            (project_id, phase_id),
        ).fetchall()
        active_rows = conn.execute(
            """SELECT fact_id, description FROM requirement_versions
               WHERE project_id=? AND phase_id=? AND status='active'""",
            (project_id, phase_id),
        ).fetchall()
    active_by_fact = {r["fact_id"]: (r["description"] or "") for r in active_rows}

    count = 0
    for r in rows:
        fact_id = r["fact_id"]
        ver = int(r["version"])
        src = f"{project_id}:{phase_id}:{fact_id}"
        memver_id = f"memver:{project_id}:{phase_id}:{fact_id}:v{ver}"
        desc = (r["description"] or "")[:4000]
        upsert_node(
            output_dir,
            memver_id,
            "MEMVER",
            title=f"[v{ver}] {fact_id}",
            content=desc,
            project_id=project_id,
            phase_id=phase_id,
            tags=["version_snapshot"],
        )
        add_link(
            output_dir,
            src,
            memver_id,
            LINK_SUPERSEDES,
            strength=0.92,
            reason=f"superseded version {ver}",
        )
        count += 1
        cur_desc = active_by_fact.get(fact_id, "")
        if cur_desc and _polarity_clash(cur_desc, desc):
            add_link(output_dir, src, memver_id, LINK_CONTRADICTS, strength=0.75, reason="polarity clash vs snapshot")
            add_link(output_dir, memver_id, src, LINK_CONTRADICTS, strength=0.75, reason="polarity clash vs current")
    return count


def _polarity_clash(a: str, b: str) -> bool:
    ax, bx = a.lower(), b.lower()
    strong_neg = ("禁止", "不支持", "勿", "不得", "不能", "排除", "no ", "not ", "must not")
    strong_pos = ("必须", "应当", "需要", "务必", "须", "must ", "shall ", "required")
    a_neg = any(k in ax for k in strong_neg)
    b_neg = any(k in bx for k in strong_neg)
    a_pos = any(k in ax for k in strong_pos)
    b_pos = any(k in bx for k in strong_pos)
    return (a_neg and b_pos) or (b_neg and a_pos)


def build_derived_from_hyperedges(output_dir: Path, project_id: str, phase_id: str) -> int:
    """同一业务域 hyperedge 内按 REQ→BR→SE→GAP 顺序链式 DERIVED_FROM."""
    hedge_like = f"hyper:{project_id}:{phase_id}:%"
    with get_connection(output_dir) as conn:
        hedges = conn.execute(
            "SELECT hyperedge_id FROM knowledge_hyperedges WHERE project_id=? AND hyperedge_id LIKE ?",
            (project_id, hedge_like),
        ).fetchall()

    count = 0
    for (hid,) in hedges:
        rows = conn.execute(
            """SELECT m.node_id, n.title, n.node_type
               FROM knowledge_hyperedge_members m
               JOIN knowledge_nodes n ON m.node_id = n.node_id
               WHERE m.hyperedge_id=? AND n.project_id=? AND n.phase_id=?""",
            (hid, project_id, phase_id),
        ).fetchall()
        if len(rows) < 2:
            continue
        members = [dict(r) for r in rows]
        members.sort(key=lambda m: (_TYPE_RANK.get(_kind_from_fact_title(m["title"] or ""), 99), m["node_id"]))
        for i in range(1, len(members)):
            a, b = members[i]["node_id"], members[i - 1]["node_id"]
            add_link(
                output_dir,
                a,
                b,
                LINK_DERIVED_FROM,
                strength=0.6,
                reason=f"hyperedge {hid}",
            )
            count += 1
    return count


def build_gap_contradiction_links(
    output_dir: Path, project_id: str, phase_id: str, *, max_pairs: int = MEMORY_GAP_CONTRADICTION_MAX_PAIRS
) -> int:
    """同 Phase 的 GAP 事实之间，基于极保守的极性冲突启发式添加 CONTRADICTS（双向）."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT node_id, title, content FROM knowledge_nodes
               WHERE project_id=? AND phase_id=? AND node_type='FACT' AND title LIKE '[GAP]%'""",
            (project_id, phase_id),
        ).fetchall()
    nodes = [dict(r) for r in rows]
    added = 0
    pair_budget = max_pairs
    for i, a in enumerate(nodes):
        for b in nodes[i + 1 :]:
            if pair_budget <= 0:
                log.info(
                    "gap_contradiction: max_pairs=%d reached for %s/%s (nodes=%d), truncated",
                    max_pairs,
                    project_id,
                    phase_id,
                    len(nodes),
                )
                return added
            if _polarity_clash(a.get("content", ""), b.get("content", "")):
                add_link(
                    output_dir,
                    a["node_id"],
                    b["node_id"],
                    LINK_CONTRADICTS,
                    strength=0.55,
                    reason="GAP polarity clash",
                )
                add_link(
                    output_dir,
                    b["node_id"],
                    a["node_id"],
                    LINK_CONTRADICTS,
                    strength=0.55,
                    reason="GAP polarity clash",
                )
                added += 2
                pair_budget -= 1
    return added


def _read_and_pop_queue(queue_path: Path, max_consume: int) -> tuple[list[dict[str, Any]], int]:
    if not queue_path.exists():
        return [], 0
    raw = queue_path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return [], 0
    take = min(len(lines), max_consume)
    batch: list[dict[str, Any]] = []
    for line in lines[:take]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.warning("garden: skip malformed queue line")
            continue
        if isinstance(obj, dict):
            batch.append(obj)
    rest = lines[take:]
    queue_path.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")
    return batch, take


def run_memory_garden(output_dir: Path, *, max_queue_lines: int = 120) -> dict[str, Any]:
    """消费 sidecar 队列一批；全局跑一次跨项目链接；对涉及 phase 写语义边与报告."""
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_path = output_dir / MEMORY_SIDECAR_QUEUE
    batch, consumed = _read_and_pop_queue(queue_path, max_queue_lines)

    report: dict[str, Any] = {
        "queue_lines_consumed": consumed,
        "batch_records": len(batch),
        "cross_project_links": 0,
        "supersedes_links": 0,
        "derived_from_links": 0,
        "contradicts_links": 0,
        "pairs": [],
    }

    if not batch:
        report["note"] = "empty_or_unparseable_queue"
        save_json(output_dir / MEMORY_GARDEN_REPORT, report)
        return report

    seen: set[tuple[str, str]] = set()
    pairs: list[dict[str, str]] = []
    for row in batch:
        pid = row.get("project_id") or ""
        ph = row.get("phase_id") or ""
        if not pid or not ph:
            continue
        key = (pid, ph)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"project_id": pid, "phase_id": ph})

    report["pairs"] = pairs
    report["cross_project_links"] = build_cross_project_links(output_dir)

    sup = der = con = 0
    for p in pairs:
        try:
            sup += build_supersedes_links(output_dir, p["project_id"], p["phase_id"])
            der += build_derived_from_hyperedges(output_dir, p["project_id"], p["phase_id"])
            con += build_gap_contradiction_links(output_dir, p["project_id"], p["phase_id"])
        except Exception:
            log.warning("garden: pair failed %s/%s", p["project_id"], p["phase_id"], exc_info=True)

    report["supersedes_links"] = sup
    report["derived_from_links"] = der
    report["contradicts_links"] = con
    save_json(output_dir / MEMORY_GARDEN_REPORT, report)
    return report


def handle_memory_garden_finalize(ctx: ExecutionContext, result: PhaseResult) -> None:
    """finalize handler：消费队列并写本 phase 的 garden 摘要."""
    report = run_memory_garden(ctx.output_dir)
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    save_json(ctx.internal_dir / "_memory_garden_local.json", report)
