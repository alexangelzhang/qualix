"""Mermaid 图验证：解析 Mermaid 文本提取节点/边，与 VLM 元数据对比.

用于图片→Mermaid 转换后的验证闭环：
1. 从 Mermaid 代码中提取节点和边的数量
2. 与 VLM 返回的 node_count/edge_count 对比
3. 差异超阈值标记 NEEDS_REVIEW
"""

from __future__ import annotations

import re
from typing import Any


def extract_mermaid_graph_stats(mermaid_code: str) -> dict[str, int]:
    """从 Mermaid 代码中提取节点和边的数量.

    支持 flowchart/graph 和 stateDiagram 两种常见格式。

    Returns:
        {"node_count": N, "edge_count": M}
    """
    if not mermaid_code or not mermaid_code.strip():
        return {"node_count": 0, "edge_count": 0}

    lines = mermaid_code.strip().splitlines()
    nodes: set[str] = set()
    edge_count = 0

    # 检测图类型
    first_line = lines[0].strip().lower() if lines else ""
    is_state = first_line.startswith("statediagram")

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("%%") or stripped.startswith("---"):
            continue

        if is_state:
            # stateDiagram: state transitions "A --> B" or "A --> B : label"
            m = re.match(r"(\w+)\s*-->\s*(\w+)", stripped)
            if m:
                nodes.add(m.group(1))
                nodes.add(m.group(2))
                edge_count += 1
                continue
            # state declaration: "state Name"
            m = re.match(r"state\s+(\w+)", stripped)
            if m:
                nodes.add(m.group(1))
        else:
            # flowchart/graph: edges like "A --> B", "A -->|label| B", "A --- B"
            edge_pattern = re.findall(
                r"(\w+)\s*(?:-->|==>|-.->|---|\|[^|]*\|)\s*(\w+)",
                stripped,
            )
            for src, tgt in edge_pattern:
                nodes.add(src)
                nodes.add(tgt)
                edge_count += 1

            # node declarations: "A[label]" or "A(label)" or "A{label}"
            node_decl = re.findall(r"(\w+)\s*[\[\(\{]", stripped)
            nodes.update(node_decl)

    # 排除 Mermaid 关键词
    keywords = {
        "graph", "flowchart", "subgraph", "end", "direction",
        "statediagram", "classDef", "class", "click", "style",
        "LR", "RL", "TB", "BT", "TD", "v2",
    }
    nodes -= keywords

    return {"node_count": len(nodes), "edge_count": edge_count}


def validate_mermaid_against_metadata(
    mermaid_code: str,
    expected_nodes: int | None = None,
    expected_edges: int | None = None,
    node_tolerance: float = 0.3,
    edge_tolerance: float = 0.3,
) -> dict[str, Any]:
    """验证 Mermaid 代码与预期的节点/边数量是否匹配.

    Args:
        mermaid_code: Mermaid 图代码
        expected_nodes: VLM 返回的预期节点数
        expected_edges: VLM 返回的预期边数
        node_tolerance: 节点数量容差比例（默认 30%）
        edge_tolerance: 边数量容差比例（默认 30%）

    Returns:
        {
            "status": "PASS" | "NEEDS_REVIEW" | "SKIP",
            "actual": {"node_count": N, "edge_count": M},
            "expected": {"node_count": X, "edge_count": Y},
            "issues": ["..."]
        }
    """
    if not mermaid_code or not mermaid_code.strip():
        return {
            "status": "SKIP",
            "actual": {"node_count": 0, "edge_count": 0},
            "expected": {"node_count": expected_nodes, "edge_count": expected_edges},
            "issues": ["无 Mermaid 代码"],
        }

    actual = extract_mermaid_graph_stats(mermaid_code)
    issues: list[str] = []

    if expected_nodes is not None and expected_nodes > 0:
        diff = abs(actual["node_count"] - expected_nodes)
        if diff > expected_nodes * node_tolerance:
            issues.append(
                f"节点数偏差过大: 实际 {actual['node_count']} vs 预期 {expected_nodes}"
            )

    if expected_edges is not None and expected_edges > 0:
        diff = abs(actual["edge_count"] - expected_edges)
        if diff > expected_edges * edge_tolerance:
            issues.append(
                f"边数偏差过大: 实际 {actual['edge_count']} vs 预期 {expected_edges}"
            )

    # 基本完整性检查
    if actual["node_count"] == 0:
        issues.append("Mermaid 代码未解析出任何节点")
    if actual["node_count"] > 0 and actual["edge_count"] == 0:
        issues.append("Mermaid 代码有节点但无边，可能不完整")

    status = "NEEDS_REVIEW" if issues else "PASS"
    # 如果没有预期值可对比，且基本结构完整，标记为 PASS
    if expected_nodes is None and expected_edges is None and not issues:
        status = "PASS"

    return {
        "status": status,
        "actual": actual,
        "expected": {"node_count": expected_nodes, "edge_count": expected_edges},
        "issues": issues,
    }


def validate_image_mermaid_batch(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量验证图片语义解析结果中的 Mermaid 代码.

    Args:
        items: image_semantics.json 中的 items 列表，
               每个 item 可能包含 mermaid_code / node_count / edge_count

    Returns:
        验证结果列表，每个包含 token + validation 结果
    """
    results: list[dict[str, Any]] = []
    for item in items:
        mermaid_code = item.get("mermaid_code", "")
        if not mermaid_code:
            continue

        validation = validate_mermaid_against_metadata(
            mermaid_code,
            expected_nodes=item.get("node_count"),
            expected_edges=item.get("edge_count"),
        )
        results.append({
            "token": item.get("token", ""),
            "name": item.get("name", ""),
            "validation": validation,
        })

    return results
