#!/usr/bin/env python3
"""从浏览器内存中接收飞书文档图片数据。

启动本地 HTTP server，让浏览器 JS 把 base64 图片 POST 过来。
配合 Chrome MCP inject_script 使用。

Usage:
    python scripts/feishu_image_receiver.py -o output/kind-care/phaseA
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path


class ImageReceiver(BaseHTTPRequestHandler):
    """接收浏览器 POST 过来的图片数据。"""
    assets_dir: Path
    results: list
    total_expected: int = 0
    received_count: int = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        if "total" in data:
            # 初始化消息
            ImageReceiver.total_expected = data["total"]
            ImageReceiver.received_count = 0
            print(f"[receiver] 预期接收 {data['total']} 张图片", file=sys.stderr)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

        idx = data.get("idx", 0)
        b64_data = data.get("data", "")
        img_type = data.get("type", "image/png")
        size = data.get("size", 0)
        error = data.get("error", "")

        if error:
            ImageReceiver.results.append({
                "index": idx, "status": "failed", "error": error,
            })
            print(f"  [{idx}] FAIL: {error}", file=sys.stderr)
        elif b64_data:
            # 解码并保存
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            raw = base64.b64decode(b64_data)

            ext = ".png"
            if "jpeg" in img_type or "jpg" in img_type:
                ext = ".jpg"
            elif "gif" in img_type:
                ext = ".gif"
            elif "webp" in img_type:
                ext = ".webp"
            elif "svg" in img_type:
                ext = ".svg"

            filename = f"feishu_img_{idx:03d}{ext}"
            target = ImageReceiver.assets_dir / filename
            target.write_bytes(raw)

            ImageReceiver.results.append({
                "index": idx, "filename": filename, "status": "downloaded",
                "size": len(raw), "type": img_type,
            })
            print(f"  [{idx}] OK: {filename} ({len(raw)} bytes)", file=sys.stderr)

        ImageReceiver.received_count += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

        # 全部接收完毕
        if ImageReceiver.received_count >= ImageReceiver.total_expected > 0:
            print(f"\n[receiver] 全部接收完毕!", file=sys.stderr)
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志


def main():
    parser = argparse.ArgumentParser(description="接收浏览器图片数据")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("--port", type=int, default=18765, help="监听端口")
    args = parser.parse_args()

    assets_dir = Path(args.output) / "ingest" / "ingest" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    ImageReceiver.assets_dir = assets_dir
    ImageReceiver.results = []

    server = HTTPServer(("127.0.0.1", args.port), ImageReceiver)
    print(f"[receiver] 监听 http://127.0.0.1:{args.port}", file=sys.stderr)
    print(f"[receiver] 等待浏览器发送图片数据...", file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    # 保存 manifest
    manifest_path = Path(args.output) / "ingest" / "ingest" / "browser_asset_manifest.json"
    manifest_path.write_text(json.dumps(ImageReceiver.results, indent=2, ensure_ascii=False))

    downloaded = sum(1 for r in ImageReceiver.results if r["status"] == "downloaded")
    failed = sum(1 for r in ImageReceiver.results if r.get("status") == "failed")
    print(f"\n[receiver] 完成: {downloaded} 下载, {failed} 失败", file=sys.stderr)
    print(json.dumps({
        "total": len(ImageReceiver.results),
        "downloaded": downloaded,
        "failed": failed,
        "manifest_path": str(manifest_path),
        "assets_dir": str(assets_dir),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
