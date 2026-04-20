"""Hyperedge 管理：多实体关联（3+ 节点的业务域链接）.

从 knowledge_network.py 拆分而来，负责：
1. 创建/查询 hyperedge（多节点关联）
2. 从 Phase A 产物自动构建业务域 hyperedge
3. 格式化 hyperedge 上下文供 prompt 注入
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dqg.store import get_connection

if TYPE_CHECKING:
    from pathlib import Path

# 从 knowledge_network 复用 pattern 关键词
from dqg.memory.knowledge_network import _PATTERN_KEYWORDS


def create_hyperedge(
    output_dir: Path,
    hyperedge_id: str,
    edge_type: str,
    node_ids: list[str],
    roles: list[str] | None = None,
    label: str = "",
    description: str = "",
    project_id: str = "",
    strength: float = 1.0,
) -> None:
    """创建一条 hyperedge，关联 3+ 个节点.

    Args:
        hyperedge_id: 唯一标识
        edge_type: 关联类型（如 AMOUNT_CHAIN, STATE_MACHINE_CHAIN, CONCURRENCY_CHAIN）
        node_ids: 参与节点 ID 列表
        roles: 每个节点在 hyperedge 中的角色（如 "se", "br", "weak_assert"）
        label: 简短标签
        description: 描述
        project_id: 所属项目
        strength: 关联强度
    """
    if roles and len(roles) != len(node_ids):
        roles = None

    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO knowledge_hyperedges (hyperedge_id, edge_type, label, description, project_id, strength)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(hyperedge_id) DO UPDATE SET
                label=excluded.label, description=excluded.description, strength=excluded.strength""",
            (hyperedge_id, edge_type, label, description, project_id, strength),
        )
        conn.execute("DELETE FROM knowledge_hyperedge_members WHERE hyperedge_id=?", (hyperedge_id,))
        for i, node_id in enumerate(node_ids):
            role = roles[i] if roles else ""
            conn.execute(
                """INSERT OR IGNORE INTO knowledge_hyperedge_members (hyperedge_id, node_id, role)
                VALUES (?, ?, ?)""",
                (hyperedge_id, node_id, role),
            )


def get_hyperedges_for_node(
    output_dir: Path,
    node_id: str,
) -> list[dict[str, Any]]:
    """获取某个节点参与的所有 hyperedge."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT h.hyperedge_id, h.edge_type, h.label, h.description, h.project_id, h.strength,
                      m.role
               FROM knowledge_hyperedges h
               JOIN knowledge_hyperedge_members m ON h.hyperedge_id = m.hyperedge_id
               WHERE m.node_id = ?""",
            (node_id,),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for r in rows:
        results.append({
            "hyperedge_id": r[0],
            "edge_type": r[1],
            "label": r[2],
            "description": r[3],
            "project_id": r[4],
            "strength": r[5],
            "my_role": r[6],
        })
    return results


def get_hyperedge_members(
    output_dir: Path,
    hyperedge_id: str,
) -> list[dict[str, Any]]:
    """获取 hyperedge 的所有成员节点."""
    with get_connection(output_dir) as conn:
        rows = conn.execute(
            """SELECT m.node_id, m.role, n.node_type, n.title, n.content, n.project_id
               FROM knowledge_hyperedge_members m
               LEFT JOIN knowledge_nodes n ON m.node_id = n.node_id
               WHERE m.hyperedge_id = ?""",
            (hyperedge_id,),
        ).fetchall()

    return [
        {
            "node_id": r[0],
            "role": r[1],
            "node_type": r[2] or "",
            "title": r[3] or "",
            "content": (r[4] or "")[:100],
            "project_id": r[5] or "",
        }
        for r in rows
    ]


def build_business_hyperedges(output_dir: Path, project_id: str, phase_id: str) -> int:
    """从 Phase A 产物自动构建业务域 hyperedge.

    扫描 SE，按业务域（金额/并发/状态机等）聚合关联的 BR + SE + GAP，
    形成多实体关联的 hyperedge。

    Returns:
        创建的 hyperedge 数量
    """
    with get_connection(output_dir) as conn:
        nodes = conn.execute(
            "SELECT node_id, node_type, title, content FROM knowledge_nodes WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        ).fetchall()

    if not nodes:
        return 0

    pattern_groups: dict[str, list[dict[str, str]]] = {}
    for n in nodes:
        text = f"{n[2]} {n[3]}".lower()
        for pattern, keywords in _PATTERN_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                if pattern not in pattern_groups:
                    pattern_groups[pattern] = []
                pattern_groups[pattern].append({
                    "node_id": n[0],
                    "node_type": n[1],
                    "title": n[2],
                })

    count = 0
    for pattern, members in pattern_groups.items():
        if len(members) < 2:
            continue

        hyperedge_id = f"hyper:{project_id}:{phase_id}:{pattern}"
        node_ids = [m["node_id"] for m in members]
        roles = [m["node_type"] for m in members]
        titles = [m["title"][:30] for m in members[:3]]

        create_hyperedge(
            output_dir,
            hyperedge_id=hyperedge_id,
            edge_type=f"{pattern.upper()}_CHAIN",
            node_ids=node_ids,
            roles=roles,
            label=f"{pattern} 关联链 ({len(members)} 节点)",
            description=f"业务域 [{pattern}] 的多实体关联: {', '.join(titles)}",
            project_id=project_id,
        )
        count += 1

    return count


def format_hyperedge_context(
    output_dir: Path,
    node_id: str,
) -> str:
    """格式化节点的 hyperedge 上下文，供 prompt 注入."""
    edges = get_hyperedges_for_node(output_dir, node_id)
    if not edges:
        return ""

    lines = []
    for edge in edges[:5]:
        members = get_hyperedge_members(output_dir, edge["hyperedge_id"])
        other_members = [m for m in members if m["node_id"] != node_id]
        if not other_members:
            continue
        member_strs = [f"{m['node_type']}:{m['title'][:40]}" for m in other_members[:4]]
        lines.append(f"  [{edge['edge_type']}] {edge['label']}: {', '.join(member_strs)}")

    if not lines:
        return ""
    return "  Hyperedge 关联:\n" + "\n".join(lines)
