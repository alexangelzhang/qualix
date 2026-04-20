"""Build dependency graph and aggregate output files for crawl results."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def build_dependency_graph(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root_url_norm: str,
    recursive_mentions: bool,
    canonicalize_mentions: bool,
    max_depth: int,
    max_docs: int,
    ingest_subdir: Path,
) -> Path:
    """Build and write dependency_graph.json. Returns the file path."""
    edge_status_stats = dict(Counter(str(e.get("status", "") or "") for e in edges))
    dependency_graph = {
        "generated_at": datetime.now().isoformat(),
        "root_url": root_url_norm,
        "recursive_mentions": recursive_mentions,
        "canonicalize_mentions": canonicalize_mentions,
        "max_depth": max_depth,
        "max_docs": max_docs,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "edge_status_stats": edge_status_stats,
    }
    path = ingest_subdir / "dependency_graph.json"
    path.write_text(json.dumps(dependency_graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_aggregate_output(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root_url_norm: str,
    recursive_mentions: bool,
    canonicalize_mentions: bool,
    max_depth: int,
    max_docs: int,
    ingest_subdir: Path,
    dependency_graph_path: Path,
) -> tuple[Path, Path]:
    """Build aggregate plain text and aggregate ingest JSON.

    Returns (aggregate_plain_text_path, aggregate_ingest_path).
    """
    aggregate_text_lines: list[str] = []
    aggregate_docs: list[dict[str, Any]] = []
    for node in nodes:
        plain_text_path = str(node.get("plain_text_path", "") or "")
        plain_text = ""
        if plain_text_path and Path(plain_text_path).exists():
            plain_text = Path(plain_text_path).read_text(encoding="utf-8")
        aggregate_text_lines.append(f"# [{node.get('node_id', '')}] {node.get('title', '')}")
        aggregate_text_lines.append(f"- URL: {node.get('url', '')}")
        aggregate_text_lines.append("")
        if plain_text:
            aggregate_text_lines.append(plain_text.rstrip())
            aggregate_text_lines.append("")

        aggregate_docs.append({
            "node_id": node.get("node_id", ""),
            "doc_key": node.get("doc_key", ""),
            "title": node.get("title", ""),
            "url": node.get("url", ""),
            "status": node.get("status", ""),
            "depth": node.get("depth", 0),
            "summary": node.get("summary", {}),
            "ingest_path": node.get("ingest_path", ""),
            "plain_text_path": node.get("plain_text_path", ""),
            "asset_manifest_path": node.get("asset_manifest_path", ""),
        })

    aggregate_plain_text_path = ingest_subdir / "aggregate_plain_text.txt"
    aggregate_plain_text_path.write_text(
        "\n".join(aggregate_text_lines).strip() + "\n", encoding="utf-8",
    )

    total_assets = 0
    total_asset_downloaded = 0
    total_asset_failed = 0
    for node in nodes:
        summary = node.get("summary", {}) if isinstance(node.get("summary"), dict) else {}
        total_assets += int(summary.get("asset_count", 0) or 0)
        total_asset_downloaded += int(summary.get("asset_downloaded_count", 0) or 0)
        total_asset_failed += int(summary.get("asset_failed_count", 0) or 0)

    aggregate_ingest = {
        "generated_at": datetime.now().isoformat(),
        "root_url": root_url_norm,
        "recursive_mentions": recursive_mentions,
        "canonicalize_mentions": canonicalize_mentions,
        "max_depth": max_depth,
        "max_docs": max_docs,
        "summary": {
            "doc_count": len(nodes),
            "doc_failed_count": len([n for n in nodes if n.get("status") != "ok"]),
            "edge_count": len(edges),
            "edge_crawled_ok_count": len([e for e in edges if e.get("status") == "crawled_ok"]),
            "edge_crawled_failed_count": len([e for e in edges if e.get("status") == "crawled_failed"]),
            "asset_count": total_assets,
            "asset_downloaded_count": total_asset_downloaded,
            "asset_failed_count": total_asset_failed,
        },
        "documents": aggregate_docs,
        "dependency_graph_path": str(dependency_graph_path),
        "aggregate_plain_text_path": str(aggregate_plain_text_path),
    }

    aggregate_ingest_path = ingest_subdir / "aggregate_ingest.json"
    aggregate_ingest_path.write_text(
        json.dumps(aggregate_ingest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return aggregate_plain_text_path, aggregate_ingest_path
