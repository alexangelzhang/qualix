"""跨项目知识网络（A-MEM Zettelkasten 模式）.

自动建立 SE/GAP/bug case/skill rule 之间的链接。
新项目执行时关联历史经验。

知识节点类型：
- FACT: REQ/BR/SE/GAP/OPEN（来自项目产物）
- BUG: bug case（来自案例库）
- RULE: skill 规则（来自 skill prompt）
- LESSON: 经验教训（来自 critique/preference）

链接类型：
- SIMILAR: 语义相似（如两个项目的并发 GAP）
- CAUSED_BY: 因果关系（bug case → skill rule 修改）
- RESOLVED_BY: 解决关系（GAP → 技术方案设计）
- RELATED: 一般关联
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from dqg.store import get_connection

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# 节点管理
# ---------------------------------------------------------------------------


def upsert_node(
    output_dir: Path,
    node_id: str,
    node_type: str,
    title: str,
    content: str = "",
    project_id: str = "",
    phase_id: str = "",
    tags: list[str] | None = None,
) -> None:
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO knowledge_nodes (node_id, node_type, project_id, phase_id, title, content, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                title=excluded.title, content=excluded.content, tags=excluded.tags""",
            (node_id, node_type, project_id, phase_id, title, content, json.dumps(tags or [], ensure_ascii=False)),
        )


def add_link(
    output_dir: Path,
    source_id: str,
    target_id: str,
    link_type: str,
    strength: float = 1.0,
    reason: str = "",
) -> None:
    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO knowledge_links (source_id, target_id, link_type, strength, reason)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, link_type) DO UPDATE SET
                strength=excluded.strength, reason=excluded.reason""",
            (source_id, target_id, link_type, strength, reason),
        )


# ---------------------------------------------------------------------------
# 自动链接构建
# ---------------------------------------------------------------------------

# 常见模式关键词 → 用于跨项目相似性匹配
_PATTERN_KEYWORDS = {
    "并发": ["并发", "幂等", "锁", "竞争", "冲突"],
    "权限": ["权限", "隔离", "越权", "鉴权", "角色"],
    "状态机": ["状态机", "状态流转", "状态迁移", "驳回", "循环"],
    "金额": ["金额", "计算", "精度", "BigDecimal", "分"],
    "超时": ["超时", "重试", "降级", "熔断", "补偿"],
    "通知": ["通知", "消息", "推送", "飞书", "提醒"],
    "导出": ["导出", "异步", "大数据量"],
    "缓存": ["缓存", "失效", "一致性"],
}


def build_cross_project_links(output_dir: Path) -> int:
    """扫描所有项目的事实，自动建立跨项目相似链接（批量写入）."""

    with get_connection(output_dir) as conn:
        nodes = conn.execute("SELECT node_id, node_type, project_id, title, content FROM knowledge_nodes").fetchall()

    if len(nodes) < 2:
        return 0

    # 预计算 lowered text（避免每个 pattern 重复计算）
    nodes_list = []
    for n in nodes:
        d = dict(n)
        d["_text"] = f"{d['title']} {d['content']}".lower()
        nodes_list.append(d)

    # 收集所有待插入的链接
    links_to_insert = []
    for pattern, keywords in _PATTERN_KEYWORDS.items():
        matching = [n for n in nodes_list if any(kw in n["_text"] for kw in keywords)]
        for i, a in enumerate(matching):
            for b in matching[i + 1 :]:
                if a["project_id"] != b["project_id"]:
                    links_to_insert.append((a["node_id"], b["node_id"], "SIMILAR", 0.8, f"共同模式: {pattern}"))

    # 批量写入
    if links_to_insert:
        with get_connection(output_dir) as conn:
            conn.executemany(
                """INSERT INTO knowledge_links (source_id, target_id, link_type, strength, reason)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, link_type) DO UPDATE SET
                    strength=excluded.strength, reason=excluded.reason""",
                links_to_insert,
            )

    return len(links_to_insert)


def index_project_facts(output_dir: Path, project_id: str, phase_id: str) -> int:
    """将项目产物中的事实注册为知识节点."""

    with get_connection(output_dir) as conn:
        try:
            prefix = f"{project_id}:{phase_id}:%"
            conn.execute(
                "DELETE FROM knowledge_links WHERE source_id LIKE ? OR target_id LIKE ?",
                (prefix, prefix),
            )
            conn.execute(
                "DELETE FROM knowledge_nodes WHERE project_id=? AND phase_id=? AND node_type='FACT'",
                (project_id, phase_id),
            )
            rows = conn.execute(
                "SELECT fact_id, fact_type, description FROM structured_facts WHERE project_id=? AND phase_id=?",
                (project_id, phase_id),
            ).fetchall()
        except Exception:
            return 0

    count = 0
    for r in rows:
        node_id = f"{project_id}:{phase_id}:{r['fact_id']}"
        # 提取标签
        tags = _extract_tags(r["description"])
        upsert_node(
            output_dir,
            node_id,
            "FACT",
            title=f"[{r['fact_type']}] {r['fact_id']}",
            content=r["description"],
            project_id=project_id,
            phase_id=phase_id,
            tags=tags,
        )
        count += 1

    return count


def index_bug_cases(output_dir: Path) -> int:
    """将 bug 案例库注册为知识节点."""

    try:
        from dqg.tracking.bug_cases import load_cases

        cases = load_cases()
    except Exception:
        return 0

    count = 0
    for case in cases:
        case_id = case.get("case_id", "")
        node_id = f"bug:{case_id}"
        upsert_node(
            output_dir,
            node_id,
            "BUG",
            title=case.get("title", ""),
            content=case.get("lesson", ""),
            tags=case.get("tags", []),
        )

        # 链接到 fix_target（skill rule）
        fix_target = case.get("fix_target", "")
        if fix_target:
            rule_id = f"rule:{fix_target}"
            upsert_node(output_dir, rule_id, "RULE", title=fix_target)
            add_link(output_dir, node_id, rule_id, "CAUSED_BY", reason="bug 导致规则修改")

        count += 1

    return count


def _extract_tags(text: str) -> list[str]:
    """从文本中提取标签."""
    tags = set()
    for pattern, keywords in _PATTERN_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            tags.add(pattern)
    return sorted(tags)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def get_related_knowledge(
    output_dir: Path,
    node_id: str,
    max_depth: int = 2,
) -> list[dict[str, Any]]:
    """获取某个节点的关联知识（BFS 遍历链接）."""
    visited = set()
    result = []
    queue = [(node_id, 0)]

    with get_connection(output_dir) as conn:
        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            # 获取节点信息
            node = conn.execute("SELECT * FROM knowledge_nodes WHERE node_id=?", (current,)).fetchone()
            if node and depth > 0:
                result.append({**dict(node), "depth": depth})

            # 获取链接
            links = conn.execute(
                "SELECT target_id, link_type, strength, reason FROM knowledge_links WHERE source_id=? UNION SELECT source_id, link_type, strength, reason FROM knowledge_links WHERE target_id=?",
                (current, current),
            ).fetchall()

            for link in links:
                neighbor = link[0]
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

    return result


def get_cross_project_insights(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, Any]]:
    """获取当前项目可借鉴的跨项目经验."""

    with get_connection(output_dir) as conn:
        # 找到当前项目的所有节点
        my_nodes = conn.execute(
            "SELECT node_id FROM knowledge_nodes WHERE project_id=? AND phase_id=?",
            (project_id, phase_id),
        ).fetchall()
        my_ids = {r[0] for r in my_nodes}

        insights = []
        for my_id in my_ids:
            # 找跨项目的 SIMILAR 链接
            links = conn.execute(
                """SELECT l.target_id, l.reason, l.strength, n.title, n.content, n.project_id
                FROM knowledge_links l
                JOIN knowledge_nodes n ON l.target_id = n.node_id
                WHERE l.source_id = ? AND l.link_type = 'SIMILAR' AND n.project_id != ?
                UNION
                SELECT l.source_id, l.reason, l.strength, n.title, n.content, n.project_id
                FROM knowledge_links l
                JOIN knowledge_nodes n ON l.source_id = n.node_id
                WHERE l.target_id = ? AND l.link_type = 'SIMILAR' AND n.project_id != ?""",
                (my_id, project_id, my_id, project_id),
            ).fetchall()

            for link in links:
                insights.append(
                    {
                        "my_node": my_id,
                        "related_node": link[0],
                        "reason": link[1],
                        "strength": link[2],
                        "related_title": link[3],
                        "related_content": link[4][:100],
                        "related_project": link[5],
                    }
                )

        return insights


def format_insights(insights: list[dict[str, Any]]) -> str:
    """格式化跨项目经验."""
    if not insights:
        return "  跨项目知识: 无关联经验"

    # 去重并按 strength 排序
    seen = set()
    unique = []
    for i in insights:
        key = (i["my_node"], i["related_node"])
        if key not in seen:
            seen.add(key)
            unique.append(i)
    unique.sort(key=lambda x: -x["strength"])

    lines = [f"  跨项目知识关联 ({len(unique)} 条):"]
    for i in unique[:10]:
        lines.append(f"    [{i['reason']}] {i['related_title']}: {i['related_content']}")
    return "\n".join(lines)
