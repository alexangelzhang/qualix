#!/usr/bin/env python3
"""Feishu 文档 ingest 入口 — 调用 qualix.ingest.feishu.crawler.crawl_documents."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from qualix.ingest.feishu.auth import load_larkkit
from qualix.ingest.feishu.crawler import crawl_documents
from qualix.json_utils import dump_json_str


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书文档 ingest")
    parser.add_argument("url", help="飞书文档 URL")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("--save-raw-blocks", action="store_true", help="保存原始 block JSON")
    parser.add_argument("--no-images", action="store_true", help="不下载图片")
    parser.add_argument("--prefer-user-token", action="store_true", default=True)
    parser.add_argument("--prefer-tenant-token", action="store_true")
    parser.add_argument("--max-depth", type=int, default=1)
    parser.add_argument("--max-docs", type=int, default=50)
    parser.add_argument("--no-larkkit", action="store_true", help="禁用 larkkit，走自建 API")
    args = parser.parse_args()

    prefer_user_token = not args.prefer_tenant_token

    try:
        feishu_client_cls, get_code_language = load_larkkit()
        client = feishu_client_cls()
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    result = crawl_documents(
        client=client,
        get_code_language=get_code_language,
        root_url=args.url,
        output_dir=Path(args.output),
        prefer_user_token=prefer_user_token,
        download_images=not args.no_images,
        save_raw_blocks=args.save_raw_blocks,
        asset_retries=3,
        include_raw_image_keys=False,
        recursive_mentions=args.max_depth > 0,
        canonicalize_mentions=True,
        max_depth=args.max_depth,
        max_docs=args.max_docs,
        use_larkkit=not args.no_larkkit,
    )

    print(dump_json_str(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
