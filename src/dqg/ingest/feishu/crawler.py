"""Crawl Feishu documents with recursive mention traversal.

This module is the main orchestrator. Sub-modules:
- block_parser: block type parsing and element extraction
- segment_builder: document segment and asset assembly
- document_ingestor: single-document ingestion pipeline

All public symbols are re-exported here for backward compatibility.
"""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from dqg.ingest.feishu.asset_downloader import sanitize_filename
from dqg.ingest.feishu.auth import (
    normalize_url,
    parse_feishu_url,
)
from dqg.ingest.common import warn
from dqg.ingest.feishu.document_ingestor import (
    fetch_raw_content_with_fallback,
    ingest_single_document,
)
from dqg.ingest.feishu.mention_graph import canonicalize_mention_target, resolve_mention_target

# --- Backward-compatible re-exports ---
from dqg.ingest.feishu.block_parser import (  # noqa: F401
    collect_mention_docs,
    extract_block_text,
    extract_media_asset,
    extract_text_from_elements,
    find_root_block_id,
    get_block_elements,
)
from dqg.ingest.feishu.segment_builder import build_segments_and_assets  # noqa: F401

# Re-export from document_ingestor (already imported above, just add to namespace)
fetch_raw_content_with_fallback = fetch_raw_content_with_fallback  # noqa: PLW0127
ingest_single_document = ingest_single_document  # noqa: PLW0127

if TYPE_CHECKING:
    from collections.abc import Callable

_DEFAULT_DOC_WORKERS = 4


def crawl_documents(
    client: Any,
    get_code_language: Callable[[int], str],
    root_url: str,
    output_dir: Path,
    prefer_user_token: bool,
    download_images: bool,
    save_raw_blocks: bool,
    asset_retries: int,
    include_raw_image_keys: bool,
    recursive_mentions: bool,
    canonicalize_mentions: bool,
    max_depth: int,
    max_docs: int,
    max_doc_workers: int = _DEFAULT_DOC_WORKERS,
) -> dict[str, Any]:
    root_url_norm = normalize_url(root_url)
    root_parsed = urlparse(root_url_norm)
    root_scheme = root_parsed.scheme or "https"
    root_host = root_parsed.netloc

    ingest_subdir = output_dir / "ingest"
    ingest_subdir.mkdir(parents=True, exist_ok=True)
    docs_dir = ingest_subdir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    processed_doc_keys: set[str] = set()
    scheduled_doc_keys: set[str] = set()
    doc_key_to_node_id: dict[str, str] = {}
    mention_target_cache: dict[str, tuple[str, str, str]] = {}

    root_doc_type, root_token = parse_feishu_url(root_url_norm)
    root_doc_key = f"{root_doc_type}:{root_token}"
    current_batch = [{"url": root_url_norm, "depth": 0, "from_node_id": "", "via": {}, "doc_key": root_doc_key}]
    scheduled_doc_keys.add(root_doc_key)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    while current_batch:
        if len(nodes) >= max_docs:
            warn(f"达到 max_docs={max_docs}，停止继续抓取")
            break

        # Deduplicate and cap batch
        batch_jobs: list[dict[str, Any]] = []
        for job in current_batch:
            doc_key = str(job["doc_key"])
            if doc_key in processed_doc_keys:
                continue
            if len(nodes) + len(batch_jobs) >= max_docs:
                break
            batch_jobs.append(job)

        if not batch_jobs:
            break

        # Assign node IDs before parallel execution (must be sequential)
        job_contexts: list[dict[str, Any]] = []
        for job in batch_jobs:
            doc_type, token = parse_feishu_url(str(job["url"]))
            doc_key = f"{doc_type}:{token}"
            node_id = f"DOC-{len(nodes) + len(job_contexts) + 1:03d}"
            doc_key_to_node_id[doc_key] = node_id
            current_depth = int(job["depth"])
            node_output_dir = ingest_subdir if current_depth == 0 else docs_dir / sanitize_filename(f"{node_id}_{token}")
            job_contexts.append({
                "job": job,
                "node_id": node_id,
                "doc_key": doc_key,
                "node_output_dir": node_output_dir,
                "depth": current_depth,
            })

        # Parallel document ingestion
        workers = min(max_doc_workers, len(job_contexts))
        # Root doc (depth=0) always runs alone to establish baseline
        if job_contexts[0]["depth"] == 0:
            workers = 1

        def _ingest_job(ctx: dict[str, Any]) -> dict[str, Any]:
            node: dict[str, Any] = {
                "node_id": ctx["node_id"],
                "doc_key": ctx["doc_key"],
                "url": str(ctx["job"]["url"]),
                "depth": ctx["depth"],
                "status": "pending",
                "title": "",
                "document_id": "",
                "output_dir": str(ctx["node_output_dir"]),
                "error": "",
                "summary": {},
            }
            try:
                result = ingest_single_document(
                    client=client,
                    get_code_language=get_code_language,
                    input_url=str(ctx["job"]["url"]),
                    output_dir=ctx["node_output_dir"],
                    prefer_user_token=prefer_user_token,
                    download_images=download_images,
                    save_raw_blocks=save_raw_blocks,
                    asset_retries=asset_retries,
                    include_raw_image_keys=include_raw_image_keys,
                )
                node.update({
                    "status": "ok",
                    "title": result.get("title", ""),
                    "document_id": result.get("document_id", ""),
                    "summary": result.get("summary", {}),
                    "ingest_path": result.get("ingest_path", ""),
                    "plain_text_path": result.get("plain_text_path", ""),
                    "asset_manifest_path": result.get("asset_manifest_path", ""),
                    "raw_blocks_path": result.get("raw_blocks_path", ""),
                    "mention_count": len(result.get("mention_docs", [])),
                    "_mention_docs": result.get("mention_docs", []),
                })
            except Exception as exc:
                node["status"] = "failed"
                node["error"] = str(exc)
                node["_mention_docs"] = []
                warn(f"抓取文档失败: {ctx['job']['url']}: {exc}")
            return node

        batch_results: list[dict[str, Any]] = [{}] * len(job_contexts)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {
                pool.submit(_ingest_job, ctx): i
                for i, ctx in enumerate(job_contexts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                batch_results[idx] = future.result()

        # Process results and collect next batch
        next_batch: list[dict[str, Any]] = []
        for ctx, node in zip(job_contexts, batch_results):
            doc_key = ctx["doc_key"]
            node_id = ctx["node_id"]
            current_depth = ctx["depth"]
            mention_docs = node.pop("_mention_docs", [])

            for mention in mention_docs:
                edge = {
                    "from_node_id": node_id,
                    "from_doc_key": doc_key,
                    "mention_title": mention.get("title", ""),
                    "mention_token": mention.get("token", ""),
                    "mention_url": mention.get("url", ""),
                    "mention_obj_type": mention.get("obj_type", ""),
                    "source_block_ids": mention.get("source_block_ids", []),
                    "to_doc_key": "",
                    "to_node_id": "",
                    "to_url": "",
                    "status": "pending",
                    "reason": "",
                }

                if not recursive_mentions:
                    edge["status"] = "skipped"
                    edge["reason"] = "recursive_mentions_disabled"
                    edges.append(edge)
                    continue
                if current_depth >= max_depth:
                    edge["status"] = "skipped"
                    edge["reason"] = "max_depth_reached"
                    edges.append(edge)
                    continue

                target_url, target_type, target_token, reason = resolve_mention_target(
                    mention=mention,
                    default_scheme=root_scheme,
                    default_host=root_host,
                )
                if not target_url:
                    edge["status"] = "skipped"
                    edge["reason"] = reason
                    edges.append(edge)
                    continue

                target_doc_key = f"{target_type}:{target_token}"
                canonical_reason = ""
                if canonicalize_mentions and target_type in {"docx", "wiki"}:
                    cache_key = f"{target_type}:{target_token}|{target_url}"
                    cached = mention_target_cache.get(cache_key)
                    if cached is None:
                        cached = canonicalize_mention_target(
                            client=client,
                            target_url=target_url,
                            target_type=target_type,
                            target_token=target_token,
                            prefer_user_token=prefer_user_token,
                        )
                        mention_target_cache[cache_key] = cached
                    target_url, target_doc_key, canonical_reason = cached
                    if canonical_reason not in {"", "already_canonical", "not_doc_like"}:
                        edge["canonicalization_reason"] = canonical_reason

                edge["to_doc_key"] = target_doc_key
                edge["to_url"] = target_url

                if target_type not in {"docx", "wiki"}:
                    edge["status"] = "skipped"
                    edge["reason"] = f"unsupported_recursive_type:{target_type}"
                    edges.append(edge)
                    continue

                final_reason = reason
                if canonical_reason and canonical_reason not in {"", "already_canonical", "not_doc_like"}:
                    final_reason = f"{reason}|{canonical_reason}" if reason else canonical_reason

                if target_doc_key in doc_key_to_node_id:
                    edge["to_node_id"] = doc_key_to_node_id[target_doc_key]
                    edge["status"] = "linked_existing"
                    edge["reason"] = final_reason
                    edges.append(edge)
                    continue
                if target_doc_key in scheduled_doc_keys:
                    edge["status"] = "already_scheduled"
                    edge["reason"] = final_reason
                    edges.append(edge)
                    continue
                if len(scheduled_doc_keys) >= max_docs:
                    edge["status"] = "skipped"
                    edge["reason"] = "max_docs_reached"
                    edges.append(edge)
                    continue

                next_batch.append({
                    "url": target_url,
                    "depth": current_depth + 1,
                    "from_node_id": node_id,
                    "via": mention,
                    "doc_key": target_doc_key,
                })
                scheduled_doc_keys.add(target_doc_key)
                edge["status"] = "scheduled"
                edge["reason"] = final_reason
                edges.append(edge)

            nodes.append(node)
            processed_doc_keys.add(doc_key)

        current_batch = next_batch

    node_by_id: dict[str, dict[str, Any]] = {str(n.get("node_id", "")): n for n in nodes}
    for edge in edges:
        to_doc_key = str(edge.get("to_doc_key", "") or "")
        if not to_doc_key:
            continue
        if not edge.get("to_node_id") and to_doc_key in doc_key_to_node_id:
            edge["to_node_id"] = doc_key_to_node_id[to_doc_key]
        to_node_id = str(edge.get("to_node_id", "") or "")
        target_node = node_by_id.get(to_node_id)
        if target_node:
            edge["target_node_status"] = target_node.get("status", "")
            edge["target_node_error"] = target_node.get("error", "")
        if edge.get("status") in {"scheduled", "already_scheduled", "linked_existing", "crawled"}:
            if not target_node:
                edge["status"] = "skipped"
                edge["reason"] = "scheduled_but_not_crawled"
                continue
            if target_node.get("status") == "ok":
                edge["status"] = "crawled_ok"
            else:
                edge["status"] = "crawled_failed"
                if not edge.get("reason"):
                    edge["reason"] = f"target_node_status:{target_node.get('status', 'unknown')}"

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

    dependency_graph_path = ingest_subdir / "dependency_graph.json"
    dependency_graph_path.write_text(json.dumps(dependency_graph, ensure_ascii=False, indent=2), encoding="utf-8")

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

        aggregate_docs.append(
            {
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
            }
        )

    aggregate_plain_text_path = ingest_subdir / "aggregate_plain_text.txt"
    aggregate_plain_text_path.write_text("\n".join(aggregate_text_lines).strip() + "\n", encoding="utf-8")
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
    aggregate_ingest_path.write_text(json.dumps(aggregate_ingest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "nodes": nodes,
        "edges": edges,
        "dependency_graph_path": str(dependency_graph_path),
        "aggregate_ingest_path": str(aggregate_ingest_path),
        "aggregate_plain_text_path": str(aggregate_plain_text_path),
    }
