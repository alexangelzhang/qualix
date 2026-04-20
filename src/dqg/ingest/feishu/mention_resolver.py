"""Resolve mention edges and process batch ingestion results."""

from __future__ import annotations

from typing import Any

from dqg.ingest.feishu.mention_graph import canonicalize_mention_target, resolve_mention_target


def resolve_mention_edge(
    mention: dict[str, Any],
    node_id: str,
    doc_key: str,
    current_depth: int,
    root_scheme: str,
    root_host: str,
    recursive_mentions: bool,
    canonicalize_mentions: bool,
    max_depth: int,
    max_docs: int,
    client: Any,
    prefer_user_token: bool,
    scheduled_doc_keys: set[str],
    doc_key_to_node_id: dict[str, str],
    mention_target_cache: dict[str, tuple[str, str, str]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Resolve one mention into an edge dict and an optional next-batch job.

    Returns (edge, next_job_or_None).
    """
    edge: dict[str, Any] = {
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
        return edge, None
    if current_depth >= max_depth:
        edge["status"] = "skipped"
        edge["reason"] = "max_depth_reached"
        return edge, None

    target_url, target_type, target_token, reason = resolve_mention_target(
        mention=mention,
        default_scheme=root_scheme,
        default_host=root_host,
    )
    if not target_url:
        edge["status"] = "skipped"
        edge["reason"] = reason
        return edge, None

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
        return edge, None

    final_reason = reason
    if canonical_reason and canonical_reason not in {"", "already_canonical", "not_doc_like"}:
        final_reason = f"{reason}|{canonical_reason}" if reason else canonical_reason

    if target_doc_key in doc_key_to_node_id:
        edge["to_node_id"] = doc_key_to_node_id[target_doc_key]
        edge["status"] = "linked_existing"
        edge["reason"] = final_reason
        return edge, None
    if target_doc_key in scheduled_doc_keys:
        edge["status"] = "already_scheduled"
        edge["reason"] = final_reason
        return edge, None
    if len(scheduled_doc_keys) >= max_docs:
        edge["status"] = "skipped"
        edge["reason"] = "max_docs_reached"
        return edge, None

    next_job = {
        "url": target_url,
        "depth": current_depth + 1,
        "from_node_id": node_id,
        "via": mention,
        "doc_key": target_doc_key,
    }
    scheduled_doc_keys.add(target_doc_key)
    edge["status"] = "scheduled"
    edge["reason"] = final_reason
    return edge, next_job


def process_batch_results(
    job_contexts: list[dict[str, Any]],
    batch_results: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    processed_doc_keys: set[str],
    scheduled_doc_keys: set[str],
    doc_key_to_node_id: dict[str, str],
    mention_target_cache: dict[str, tuple[str, str, str]],
    root_scheme: str,
    root_host: str,
    recursive_mentions: bool,
    canonicalize_mentions: bool,
    max_depth: int,
    max_docs: int,
    client: Any,
    prefer_user_token: bool,
) -> list[dict[str, Any]]:
    """Process ingestion results: append nodes/edges, return next batch."""
    next_batch: list[dict[str, Any]] = []
    for ctx, node in zip(job_contexts, batch_results):
        doc_key = ctx["doc_key"]
        node_id = ctx["node_id"]
        current_depth = ctx["depth"]
        mention_docs = node.pop("_mention_docs", [])

        for mention in mention_docs:
            edge, next_job = resolve_mention_edge(
                mention=mention,
                node_id=node_id,
                doc_key=doc_key,
                current_depth=current_depth,
                root_scheme=root_scheme,
                root_host=root_host,
                recursive_mentions=recursive_mentions,
                canonicalize_mentions=canonicalize_mentions,
                max_depth=max_depth,
                max_docs=max_docs,
                client=client,
                prefer_user_token=prefer_user_token,
                scheduled_doc_keys=scheduled_doc_keys,
                doc_key_to_node_id=doc_key_to_node_id,
                mention_target_cache=mention_target_cache,
            )
            edges.append(edge)
            if next_job is not None:
                next_batch.append(next_job)

        nodes.append(node)
        processed_doc_keys.add(doc_key)

    return next_batch


def finalize_edges(
    edges: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    doc_key_to_node_id: dict[str, str],
) -> None:
    """Reconcile edge statuses against final node results (in-place)."""
    node_by_id: dict[str, dict[str, Any]] = {
        str(n.get("node_id", "")): n for n in nodes
    }
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
