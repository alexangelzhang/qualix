"""Single-document ingestion: fetch metadata, blocks, raw content, and persist."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dqg.ingest.feishu.asset_downloader import append_raw_image_key_assets, download_assets
from dqg.ingest.feishu.auth import (
    call_with_token_fallback,
    normalize_url,
    resolve_input_doc,
)
from dqg.ingest.feishu.bitable_ingest import ingest_bitable
from dqg.ingest.feishu.block_parser import collect_mention_docs
from dqg.ingest.common import RAW_IMAGE_KEY_PATTERN, REQUEST_TIMEOUT_SECONDS, info, warn
from dqg.ingest.error_strategy import classify_error
from dqg.ingest.feishu.segment_builder import build_segments_and_assets

if TYPE_CHECKING:
    from collections.abc import Callable


def fetch_raw_content_with_fallback(
    client: Any,
    document_id: str,
    prefer_user_token: bool,
) -> tuple[str, bool | None, list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    for use_user_token in [prefer_user_token, not prefer_user_token]:
        url = f"{client.BASE_URL}/docx/v1/documents/{document_id}/raw_content"
        try:
            response = client._session.get(  # type: ignore[attr-defined]
                url,
                headers=client._get_headers(use_user_token),  # type: ignore[attr-defined]
                params={"lang": 0},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 401:
                raise RuntimeError("[401] access_token expired or invalid")
            if response.status_code == 403:
                raise RuntimeError("[403] permission denied for raw_content")
            response.raise_for_status()
            data = response.json()
            code = int(data.get("code", 0) or 0)
            if code != 0:
                msg = str(data.get("msg", ""))
                raise RuntimeError(f"[{code}] {msg}")
            content = str((data.get("data") or {}).get("content", "") or "")
            return content, use_user_token, attempts
        except Exception as exc:  # pragma: no cover
            attempts.append(
                {
                    "use_user_token": use_user_token,
                    "error": str(exc),
                    "error_type": classify_error(str(exc)),
                }
            )
    return "", None, attempts


def ingest_single_document(
    client: Any,
    get_code_language: Callable[[int], str],
    input_url: str,
    output_dir: Path,
    prefer_user_token: bool,
    download_images: bool,
    save_raw_blocks: bool,
    asset_retries: int,
    include_raw_image_keys: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_input_url = normalize_url(input_url)

    resolved = resolve_input_doc(client, normalized_input_url, prefer_user_token)
    document_id = str(resolved["resolved_doc_id"])

    # Bitable 走独立路径
    if resolved.get("resolved_doc_type") == "bitable":
        bitable_result = ingest_bitable(
            app_token=document_id,
            output_dir=output_dir,
        )
        return {
            "status": bitable_result.get("status", "ok"),
            "url": normalized_input_url,
            "title": f"Bitable {document_id}",
            "document_id": document_id,
            "resolved": resolved,
            "ingest_path": bitable_result.get("ingest_path", ""),
            "plain_text_path": bitable_result.get("plain_text_path", ""),
            "asset_manifest_path": "",
            "raw_blocks_path": "",
            "mention_docs": [],
            "raw_image_keys": [],
            "summary": bitable_result.get("summary", {}),
        }

    # docx 走原有路径
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_meta = pool.submit(
            call_with_token_fallback,
            lambda use_user_token: client.get_document_meta(document_id, use_user_token=use_user_token),
            prefer_user_token,
        )
        fut_content = pool.submit(
            call_with_token_fallback,
            lambda use_user_token: client.get_document_content(document_id, use_user_token=use_user_token),
            prefer_user_token,
        )
        fut_raw = pool.submit(
            fetch_raw_content_with_fallback,
            client=client,
            document_id=document_id,
            prefer_user_token=prefer_user_token,
        )

        doc_meta, meta_use_user_token = fut_meta.result()
        content, content_use_user_token = fut_content.result()
        raw_content, raw_content_use_user_token, raw_content_attempts = fut_raw.result()

    blocks = content.get("items", []) if isinstance(content, dict) else []
    if not blocks:
        warn(f"文档 blocks 为空: {normalized_input_url}")

    segments, assets, plain_text = build_segments_and_assets(blocks, get_code_language)
    mention_docs = collect_mention_docs(blocks)

    raw_image_keys = sorted(set(RAW_IMAGE_KEY_PATTERN.findall(raw_content))) if raw_content else []
    if include_raw_image_keys and raw_image_keys:
        assets = append_raw_image_key_assets(assets, raw_image_keys)

    asset_results: list[dict[str, Any]] = []
    if download_images and assets:
        ingest_subdir = output_dir / "ingest"
        ingest_subdir.mkdir(parents=True, exist_ok=True)
        assets_dir = ingest_subdir / "assets"
        info(f"开始下载媒体资源: doc={document_id}, total={len(assets)}")
        asset_results = download_assets(
            client=client,
            assets=assets,
            output_dir=assets_dir,
            prefer_user_token=content_use_user_token,
            retries=asset_retries,
        )
    else:
        for idx, asset in enumerate(assets, start=1):
            asset_results.append(
                {
                    "asset_index": idx,
                    "kind": asset.get("kind", ""),
                    "token": asset.get("token", ""),
                    "name": asset.get("name", ""),
                    "section_path": asset.get("section_path", ""),
                    "source": asset.get("source", "block"),
                    "source_block_ids": asset.get("source_block_ids", []),
                    "path": "",
                    "status": "not_downloaded",
                    "error": "download_images_disabled",
                    "error_type": "download_images_disabled",
                    "failure_category": "skipped",
                    "use_user_token": None,
                    "attempts": [],
                    "guidance": [],
                }
            )

    text_segments = [seg for seg in segments if seg.get("text")]
    ingest = _build_ingest_payload(
        url=normalized_input_url, resolved=resolved, doc_meta=doc_meta, document_id=document_id,
        meta_use_user_token=meta_use_user_token, content_use_user_token=content_use_user_token,
        blocks=blocks, segments=segments, text_segments=text_segments,
        asset_results=asset_results, mention_docs=mention_docs,
        raw_content=raw_content, raw_content_use_user_token=raw_content_use_user_token,
        raw_content_attempts=raw_content_attempts, raw_image_keys=raw_image_keys,
    )

    paths = _write_ingest_files(output_dir, ingest, plain_text, asset_results, content, save_raw_blocks)

    return {
        "status": "ok",
        "url": normalized_input_url,
        "title": doc_meta.get("title", ""),
        "document_id": doc_meta.get("document_id", document_id),
        "resolved": resolved,
        "ingest_path": paths["ingest"],
        "plain_text_path": paths["plain_text"],
        "asset_manifest_path": paths["asset_manifest"],
        "raw_blocks_path": paths.get("raw_blocks", ""),
        "mention_docs": mention_docs,
        "raw_image_keys": raw_image_keys,
        "summary": ingest["summary"],
    }


def _build_ingest_payload(
    *,
    url: str, resolved: dict, doc_meta: dict, document_id: str,
    meta_use_user_token: Any, content_use_user_token: Any,
    blocks: list, segments: list, text_segments: list,
    asset_results: list, mention_docs: list,
    raw_content: str, raw_content_use_user_token: Any,
    raw_content_attempts: list, raw_image_keys: list,
) -> dict[str, Any]:
    return {
        "source": {
            "url": url,
            "resolved": resolved,
            "title": doc_meta.get("title", ""),
            "document_id": doc_meta.get("document_id", document_id),
            "meta_use_user_token": meta_use_user_token,
            "content_use_user_token": content_use_user_token,
            "generated_at": datetime.now().isoformat(),
        },
        "summary": {
            "block_count": len(blocks),
            "segment_count": len(segments),
            "text_segment_count": len(text_segments),
            "text_char_count": sum(len(seg.get("text", "")) for seg in text_segments),
            "asset_count": len(asset_results),
            "asset_downloaded_count": len([a for a in asset_results if a.get("status") in {"downloaded", "cached"}]),
            "asset_failed_count": len([a for a in asset_results if a.get("status") == "failed"]),
            "mention_doc_count": len(mention_docs),
            "raw_image_key_count": len(raw_image_keys),
        },
        "raw_content": {
            "fetched": bool(raw_content),
            "use_user_token": raw_content_use_user_token,
            "attempts": raw_content_attempts,
            "raw_image_key_count": len(raw_image_keys),
        },
        "mentions": mention_docs,
        "segments": segments,
        "assets": asset_results,
    }


def _write_ingest_files(
    output_dir: Path, ingest: dict, plain_text: str,
    asset_results: list, content: dict, save_raw_blocks: bool,
) -> dict[str, str]:
    ingest_subdir = output_dir / "ingest"
    ingest_subdir.mkdir(parents=True, exist_ok=True)
    ingest_path = ingest_subdir / "ingest.json"
    plain_text_path = ingest_subdir / "plain_text.txt"
    asset_manifest_path = ingest_subdir / "asset_manifest.json"
    ingest_path.write_text(json.dumps(ingest, ensure_ascii=False, indent=2), encoding="utf-8")
    plain_text_path.write_text(plain_text, encoding="utf-8")
    asset_manifest_path.write_text(json.dumps(asset_results, ensure_ascii=False, indent=2), encoding="utf-8")

    paths = {
        "ingest": str(ingest_path),
        "plain_text": str(plain_text_path),
        "asset_manifest": str(asset_manifest_path),
    }

    if save_raw_blocks:
        raw_blocks_path = ingest_subdir / "blocks.raw.json"
        raw_blocks_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["raw_blocks"] = str(raw_blocks_path)

    return paths
