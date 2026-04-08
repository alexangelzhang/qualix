#!/usr/bin/env python3
"""Directly ingest Feishu doc/wiki content without Markdown conversion."""

from __future__ import annotations

import argparse
from pathlib import Path

from dqg.ingest.feishu.auth import load_larkkit, parse_feishu_url
from dqg.ingest.common import fail, info, warn
from dqg.ingest.feishu.crawler import crawl_documents


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct ingest Feishu doc/wiki without Markdown conversion")
    parser.add_argument("url", help="飞书文档/Wiki URL")
    parser.add_argument("-o", "--output-dir", required=True, help="输出目录")

    parser.add_argument(
        "--prefer-user-token",
        action="store_true",
        default=True,
        help="优先使用 user_access_token（默认）",
    )
    parser.add_argument(
        "--prefer-tenant-token",
        action="store_false",
        dest="prefer_user_token",
        help="优先使用 tenant_access_token",
    )

    parser.add_argument(
        "--download-images",
        action="store_true",
        default=True,
        help="下载图片/白板/思维导图资源（默认开启）",
    )
    parser.add_argument(
        "--no-download-images",
        action="store_false",
        dest="download_images",
        help="不下载媒体资源，仅提取 token",
    )

    parser.add_argument(
        "--asset-retries",
        type=int,
        default=2,
        help="单个媒体资源下载重试次数（默认2）",
    )

    parser.add_argument(
        "--include-raw-image-keys",
        action="store_true",
        default=True,
        help="从 raw_content 提取 img_v3 key 并作为额外下载候选（默认开启）",
    )
    parser.add_argument(
        "--no-include-raw-image-keys",
        action="store_false",
        dest="include_raw_image_keys",
        help="不使用 raw_content 的 img_v3 key 补充下载",
    )

    parser.add_argument(
        "--recursive-mentions",
        action="store_true",
        default=True,
        help="递归抓取 mention_doc 引用文档（默认开启）",
    )
    parser.add_argument(
        "--no-recursive-mentions",
        action="store_false",
        dest="recursive_mentions",
        help="不递归抓取 mention_doc",
    )
    parser.add_argument(
        "--canonicalize-mentions",
        action="store_true",
        default=True,
        help="将 mention 目标统一规范化为 docx:{document_id} 以减少 wiki/docx 重复（默认开启）",
    )
    parser.add_argument(
        "--no-canonicalize-mentions",
        action="store_false",
        dest="canonicalize_mentions",
        help="不对 mention 目标做 docx canonicalize",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="mention_doc 递归最大深度（默认3）",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=30,
        help="本次最多抓取文档数（默认30）",
    )

    parser.add_argument(
        "--save-raw-blocks",
        action="store_true",
        help="保存 blocks.raw.json 便于排查",
    )

    args = parser.parse_args()

    try:
        FeishuClient, get_code_language = load_larkkit()  # noqa: N806
    except Exception as exc:
        fail(str(exc))
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        parse_feishu_url(args.url)
    except Exception as exc:
        fail(str(exc))
        return 1

    try:
        client = FeishuClient()
    except Exception as exc:
        fail(f"初始化 FeishuClient 失败: {exc}")
        return 1

    try:
        crawl_result = crawl_documents(
            client=client,
            get_code_language=get_code_language,
            root_url=args.url,
            output_dir=output_dir,
            prefer_user_token=args.prefer_user_token,
            download_images=args.download_images,
            save_raw_blocks=args.save_raw_blocks,
            asset_retries=max(args.asset_retries, 0),
            include_raw_image_keys=args.include_raw_image_keys,
            recursive_mentions=args.recursive_mentions,
            canonicalize_mentions=args.canonicalize_mentions,
            max_depth=max(args.max_depth, 0),
            max_docs=max(args.max_docs, 1),
        )
    except Exception as exc:
        fail(f"抓取失败: {exc}")
        return 1

    nodes = crawl_result.get("nodes", [])
    ok_nodes = [n for n in nodes if n.get("status") == "ok"]
    failed_nodes = [n for n in nodes if n.get("status") != "ok"]

    total_assets = 0
    total_asset_downloaded = 0
    total_asset_failed = 0
    for node in ok_nodes:
        summary = node.get("summary", {}) if isinstance(node.get("summary"), dict) else {}
        total_assets += int(summary.get("asset_count", 0) or 0)
        total_asset_downloaded += int(summary.get("asset_downloaded_count", 0) or 0)
        total_asset_failed += int(summary.get("asset_failed_count", 0) or 0)

    info(f"输出 dependency graph: {crawl_result.get('dependency_graph_path', '')}")
    info(f"输出 aggregate ingest: {crawl_result.get('aggregate_ingest_path', '')}")
    info(f"输出 aggregate plain text: {crawl_result.get('aggregate_plain_text_path', '')}")
    info(
        "统计: "
        f"docs={len(nodes)}, ok={len(ok_nodes)}, failed={len(failed_nodes)}, "
        f"assets={total_assets}, downloaded={total_asset_downloaded}, failed_assets={total_asset_failed}"
    )

    if failed_nodes:
        for node in failed_nodes:
            warn(f"文档抓取失败: node={node.get('node_id')} url={node.get('url')} err={node.get('error')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
