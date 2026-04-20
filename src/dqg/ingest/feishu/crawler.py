"""Crawl Feishu documents with recursive mention traversal.

This module is the main orchestrator. Sub-modules:
- block_parser: block type parsing and element extraction
- segment_builder: document segment and asset assembly
- document_ingestor: single-document ingestion pipeline
- mention_resolver: mention edge resolution and batch result processing
- output_builder: dependency graph and aggregate output construction

All public symbols are re-exported here for backward compatibility.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from dqg.ingest.feishu.asset_downloader import sanitize_filename
from dqg.ingest.feishu.auth import normalize_url, parse_feishu_url
from dqg.ingest.common import warn
from dqg.ingest.feishu.document_ingestor import (
    fetch_raw_content_with_fallback,
    ingest_single_document,
)
from dqg.ingest.feishu.mention_resolver import (
    finalize_edges as _finalize_edges,
    process_batch_results as _process_batch_results,
    resolve_mention_edge,
)
from dqg.ingest.feishu.output_builder import (
    build_aggregate_output as _build_aggregate_output,
    build_dependency_graph as _build_dependency_graph,
)

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


def _setup_directories(
    root_url: str,
    output_dir: Path,
) -> tuple[str, str, str, Path, Path]:
    """Normalize root URL and create output directories.

    Returns (root_url_norm, root_scheme, root_host, ingest_subdir, docs_dir).
    """
    root_url_norm = normalize_url(root_url)
    root_parsed = urlparse(root_url_norm)
    root_scheme = root_parsed.scheme or "https"
    root_host = root_parsed.netloc

    ingest_subdir = output_dir / "ingest"
    ingest_subdir.mkdir(parents=True, exist_ok=True)
    docs_dir = ingest_subdir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    return root_url_norm, root_scheme, root_host, ingest_subdir, docs_dir


def _prepare_batch_contexts(
    batch_jobs: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    doc_key_to_node_id: dict[str, str],
    ingest_subdir: Path,
    docs_dir: Path,
) -> list[dict[str, Any]]:
    """Assign node IDs and output dirs for a batch of jobs."""
    job_contexts: list[dict[str, Any]] = []
    for job in batch_jobs:
        doc_type, token = parse_feishu_url(str(job["url"]))
        doc_key = f"{doc_type}:{token}"
        node_id = f"DOC-{len(nodes) + len(job_contexts) + 1:03d}"
        doc_key_to_node_id[doc_key] = node_id
        current_depth = int(job["depth"])
        node_output_dir = (
            ingest_subdir if current_depth == 0
            else docs_dir / sanitize_filename(f"{node_id}_{token}")
        )
        job_contexts.append({
            "job": job,
            "node_id": node_id,
            "doc_key": doc_key,
            "node_output_dir": node_output_dir,
            "depth": current_depth,
        })
    return job_contexts


def _ingest_one_document(
    ctx: dict[str, Any],
    client: Any,
    get_code_language: "Callable[[int], str]",
    prefer_user_token: bool,
    download_images: bool,
    save_raw_blocks: bool,
    asset_retries: int,
    include_raw_image_keys: bool,
) -> dict[str, Any]:
    """Ingest a single document and return its node dict."""
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


def _run_batch_ingestion(
    job_contexts: list[dict[str, Any]],
    max_doc_workers: int,
    client: Any,
    get_code_language: "Callable[[int], str]",
    prefer_user_token: bool,
    download_images: bool,
    save_raw_blocks: bool,
    asset_retries: int,
    include_raw_image_keys: bool,
) -> list[dict[str, Any]]:
    """Run parallel document ingestion for a batch."""
    workers = min(max_doc_workers, len(job_contexts))
    # Root doc (depth=0) always runs alone to establish baseline
    if job_contexts[0]["depth"] == 0:
        workers = 1

    batch_results: list[dict[str, Any]] = [{}] * len(job_contexts)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(
                _ingest_one_document, ctx, client, get_code_language,
                prefer_user_token, download_images, save_raw_blocks,
                asset_retries, include_raw_image_keys,
            ): i
            for i, ctx in enumerate(job_contexts)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            batch_results[idx] = future.result()

    return batch_results


def crawl_documents(
    client: Any,
    get_code_language: "Callable[[int], str]",
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
    """Crawl Feishu documents with recursive mention traversal."""
    root_url_norm, root_scheme, root_host, ingest_subdir, docs_dir = _setup_directories(
        root_url, output_dir,
    )

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

        job_contexts = _prepare_batch_contexts(
            batch_jobs, nodes, doc_key_to_node_id, ingest_subdir, docs_dir,
        )
        batch_results = _run_batch_ingestion(
            job_contexts, max_doc_workers, client, get_code_language,
            prefer_user_token, download_images, save_raw_blocks,
            asset_retries, include_raw_image_keys,
        )
        current_batch = _process_batch_results(
            job_contexts, batch_results, nodes, edges,
            processed_doc_keys, scheduled_doc_keys, doc_key_to_node_id,
            mention_target_cache, root_scheme, root_host,
            recursive_mentions, canonicalize_mentions, max_depth, max_docs,
            client, prefer_user_token,
        )

    _finalize_edges(edges, nodes, doc_key_to_node_id)

    dependency_graph_path = _build_dependency_graph(
        nodes, edges, root_url_norm, recursive_mentions,
        canonicalize_mentions, max_depth, max_docs, ingest_subdir,
    )
    aggregate_plain_text_path, aggregate_ingest_path = _build_aggregate_output(
        nodes, edges, root_url_norm, recursive_mentions,
        canonicalize_mentions, max_depth, max_docs,
        ingest_subdir, dependency_graph_path,
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "dependency_graph_path": str(dependency_graph_path),
        "aggregate_ingest_path": str(aggregate_ingest_path),
        "aggregate_plain_text_path": str(aggregate_plain_text_path),
    }
