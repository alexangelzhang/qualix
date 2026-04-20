"""需求层级图 → GAP 检测：用 networkx 构建 REQ→BR→SE 有向图.

从 Phase Q01 的 _structured.json 构建需求依赖图，自动检测：
- 无 SE 覆盖的 BR（潜在 GAP）
- 无 BR 关联的 SE（可能是幻觉）
- 孤立 REQ（无 BR 分解）
- 无 related_ids 的 GAP/OPEN（悬空项）

输出追加到 _verification_bundle.json 作为确定性检查项。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)


@dataclass
class GraphAnomaly:
    """图异常."""
    anomaly_type: str   # UNCOVERED_BR | ORPHAN_SE | ISOLATED_REQ | DANGLING_GAP | DANGLING_OPEN
    severity: str       # HIGH | MEDIUM | LOW
    node_id: str
    description: str


@dataclass
class RequirementGraphResult:
    """图分析结果."""
    node_count: int = 0
    edge_count: int = 0
    req_count: int = 0
    br_count: int = 0
    se_count: int = 0
    gap_count: int = 0
    open_count: int = 0
    anomalies: list[GraphAnomaly] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)


def build_requirement_graph(structured_data: dict[str, Any]) -> Any:
    """从 Phase Q01 结构化数据构建 networkx DiGraph.

    节点属性: type (REQ|BR|SE|GAP|OPEN), description
    边: parent→child (REQ→BR), mapping (SE→BR/REQ), related (GAP/OPEN→REQ/BR)
    """
    try:
        import networkx as nx
    except ImportError:
        log.warning("networkx not installed, requirement graph analysis skipped")
        return None

    G = nx.DiGraph()

    # 添加 REQ/BR 节点
    for req in structured_data.get("requirements", []):
        rid = req.get("req_id", "")
        if not rid:
            continue
        node_type = "REQ" if rid.startswith("REQ") else "BR"
        G.add_node(rid, type=node_type, description=req.get("description", "")[:80])

        # 边: parent → child
        parent = req.get("parent_id", "")
        if parent and parent in G:
            G.add_edge(parent, rid, relation="parent_child")
        elif parent:
            # parent 可能还没添加，延迟处理
            G.add_node(parent, type="REQ", description="(forward ref)")
            G.add_edge(parent, rid, relation="parent_child")

    # 添加 SE 节点
    for se in structured_data.get("semantic_expectations", []):
        sid = se.get("se_id", "")
        if not sid:
            continue
        G.add_node(sid, type="SE", description=se.get("description", "")[:80])

        # 边: SE → mapping_target (REQ/BR)
        target = se.get("mapping_target", "")
        if target and target in G:
            G.add_edge(sid, target, relation="maps_to")

    # 添加 GAP 节点
    for gap in structured_data.get("gaps", []):
        gid = gap.get("gap_id", "")
        if not gid:
            continue
        G.add_node(gid, type="GAP", description=gap.get("description", "")[:80])
        for related in gap.get("related_ids", []):
            if related in G:
                G.add_edge(gid, related, relation="related_to")

    # 添加 OPEN 节点
    for op in structured_data.get("open_items", []):
        oid = op.get("open_id", "")
        if not oid:
            continue
        G.add_node(oid, type="OPEN", description=op.get("question", op.get("description", ""))[:80])
        for related in op.get("related_ids", []):
            if related in G:
                G.add_edge(oid, related, relation="related_to")

    return G


def analyze_requirement_graph(G: Any) -> RequirementGraphResult:
    """分析需求图，检测异常.

    Args:
        G: networkx DiGraph

    Returns:
        RequirementGraphResult
    """
    import networkx as nx

    result = RequirementGraphResult(
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
    )

    # 按类型分组
    reqs: list[str] = []
    brs: list[str] = []
    ses: list[str] = []
    gaps: list[str] = []
    opens: list[str] = []

    for node, data in G.nodes(data=True):
        t = data.get("type", "")
        if t == "REQ":
            reqs.append(node)
        elif t == "BR":
            brs.append(node)
        elif t == "SE":
            ses.append(node)
        elif t == "GAP":
            gaps.append(node)
        elif t == "OPEN":
            opens.append(node)

    result.req_count = len(reqs)
    result.br_count = len(brs)
    result.se_count = len(ses)
    result.gap_count = len(gaps)
    result.open_count = len(opens)

    # SE 映射目标集合
    se_targets: set[str] = set()
    for se in ses:
        for _, target, data in G.out_edges(se, data=True):
            if data.get("relation") == "maps_to":
                se_targets.add(target)

    # 检测 1: 无 SE 覆盖的 BR（潜在 GAP）
    for br in brs:
        if br not in se_targets:
            desc = G.nodes[br].get("description", "")
            result.anomalies.append(GraphAnomaly(
                anomaly_type="UNCOVERED_BR",
                severity="HIGH",
                node_id=br,
                description=f"BR 无 SE 覆盖（潜在 GAP）: {desc}",
            ))

    # 检测 2: 无 BR/REQ 关联的 SE（可能是幻觉）
    for se in ses:
        out_edges = list(G.out_edges(se, data=True))
        has_mapping = any(d.get("relation") == "maps_to" for _, _, d in out_edges)
        if not has_mapping:
            desc = G.nodes[se].get("description", "")
            result.anomalies.append(GraphAnomaly(
                anomaly_type="ORPHAN_SE",
                severity="MEDIUM",
                node_id=se,
                description=f"SE 无 REQ/BR 关联（可能是幻觉）: {desc}",
            ))

    # 检测 3: 孤立 REQ（无 BR 分解且无 SE 覆盖）
    for req in reqs:
        children = [t for _, t, d in G.out_edges(req, data=True) if d.get("relation") == "parent_child"]
        # 也检查入边（BR 的 parent 指向此 REQ）
        child_edges = [s for s, _, d in G.in_edges(req, data=True) if d.get("relation") == "parent_child"]
        has_children = bool(children) or bool(child_edges)
        has_se = req in se_targets
        if not has_children and not has_se:
            desc = G.nodes[req].get("description", "")
            result.anomalies.append(GraphAnomaly(
                anomaly_type="ISOLATED_REQ",
                severity="MEDIUM",
                node_id=req,
                description=f"REQ 无 BR 分解且无 SE 覆盖: {desc}",
            ))

    # 检测 4: 悬空 GAP（无 related_ids）
    for gap in gaps:
        out_edges = list(G.out_edges(gap))
        if not out_edges:
            desc = G.nodes[gap].get("description", "")
            result.anomalies.append(GraphAnomaly(
                anomaly_type="DANGLING_GAP",
                severity="LOW",
                node_id=gap,
                description=f"GAP 无关联需求: {desc}",
            ))

    # 检测 5: 悬空 OPEN（无 related_ids）
    for op in opens:
        out_edges = list(G.out_edges(op))
        if not out_edges:
            desc = G.nodes[op].get("description", "")
            result.anomalies.append(GraphAnomaly(
                anomaly_type="DANGLING_OPEN",
                severity="LOW",
                node_id=op,
                description=f"OPEN 无关联需求: {desc}",
            ))

    # 覆盖率汇总
    covered_brs = len([br for br in brs if br in se_targets])
    covered_reqs = len([req for req in reqs if req in se_targets or
                        any(t for _, t, d in G.out_edges(req, data=True)
                            if d.get("relation") == "parent_child")])

    result.coverage_summary = {
        "br_se_coverage": round(covered_brs / max(len(brs), 1), 2),
        "req_decomposition": round(covered_reqs / max(len(reqs), 1), 2),
        "orphan_se_rate": round(
            len([a for a in result.anomalies if a.anomaly_type == "ORPHAN_SE"]) / max(len(ses), 1), 2
        ),
    }

    return result


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def write_requirement_graph_analysis(
    output_dir: Path,
    project_id: str,
) -> Path | None:
    """从 Phase Q01 产物构建需求图并分析.

    Returns:
        写入的 JSON 文件路径
    """
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    phase_a_dir = PHASE_DIR_MAP.get("Q01", "phaseA")
    phase_a_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    structured_path = output_dir / project_id / phase_a_dir / phase_a_json

    data = load_json(structured_path)
    if not data:
        log.info("Requirement graph: no Phase Q01 structured data found")
        return None

    G = build_requirement_graph(data)
    if G is None:
        return None

    result = analyze_requirement_graph(G)

    int_dir = output_dir / project_id / phase_a_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "req_count": result.req_count,
        "br_count": result.br_count,
        "se_count": result.se_count,
        "gap_count": result.gap_count,
        "open_count": result.open_count,
        "coverage_summary": result.coverage_summary,
        "anomaly_count": len(result.anomalies),
        "anomalies": [
            {
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "node_id": a.node_id,
                "description": a.description,
            }
            for a in result.anomalies
        ],
    }

    json_path = int_dir / "_requirement_graph.json"
    save_json(json_path, output)

    log.info(
        "Requirement graph: %d nodes, %d edges, %d anomalies (BR coverage=%.0f%%)",
        result.node_count, result.edge_count, len(result.anomalies),
        result.coverage_summary.get("br_se_coverage", 0) * 100,
    )
    return json_path
