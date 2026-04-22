#!/usr/bin/env python3
"""Playwright 浏览器方式下载飞书文档内嵌图片。

复用 Chrome profile 登录态，通过 CDP 连接 + 滚动加载 + 浏览器内 fetch 下载。

Usage:
    # 先关闭 Chrome，然后运行：
    python scripts/feishu_browser_images.py <feishu_url> -o <output_dir>
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path


CDP_PORT = 9222


def launch_chrome_with_cdp() -> subprocess.Popen:
    """启动 Chrome 带 remote debugging port，使用默认 profile。"""
    chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome_user_data = str(Path.home() / "Library/Application Support/Google/Chrome")
    proc = subprocess.Popen(
        [
            chrome_bin,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={chrome_user_data}",
            "--no-first-run",
            "--disable-blink-features=AutomationControlled",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # 等 CDP 端口就绪
    import socket
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", CDP_PORT), timeout=1):
                return proc
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Chrome CDP port {CDP_PORT} not ready after 30s")


async def download_images(url: str, output_dir: Path, timeout: int = 90) -> dict:
    from playwright.async_api import async_playwright

    assets_dir = output_dir / "ingest" / "ingest" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    print(f"[browser_images] 启动 Chrome (CDP mode)...", file=sys.stderr)
    chrome_proc = launch_chrome_with_cdp()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            print(f"[browser_images] 打开文档: {url}", file=sys.stderr)
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            await asyncio.sleep(5)

            # 等待飞书文档容器出现
            print(f"[browser_images] 等待文档容器...", file=sys.stderr)
            try:
                await page.wait_for_selector(".bear-web-x-container", timeout=30000)
            except Exception:
                print(f"[browser_images] 未找到 .bear-web-x-container，尝试继续", file=sys.stderr)

            # 边滚边收集图片 URL（飞书虚拟滚动会卸载不可见的 DOM）
            print(f"[browser_images] 滚动并收集图片...", file=sys.stderr)
            img_count = await page.evaluate("""
            async () => {
                const delay = ms => new Promise(r => setTimeout(r, ms));
                const c = document.querySelector('.bear-web-x-container') || document.documentElement;

                const seen = new Set();
                const allImgs = [];

                const collect = () => {
                    document.querySelectorAll('img').forEach(img => {
                        const src = img.src || img.getAttribute('data-src') || '';
                        if (!src || src.startsWith('data:')) return;
                        if (img.classList.contains('ud__avatar__image')) return;
                        if (img.classList.contains('larkw-emoji__img')) return;
                        if (src.includes('image_size=72x72')) return;
                        if (src.includes('sprite-min')) return;
                        if (!src.includes('feishucdn') && !src.includes('feishu.cn') && !src.includes('larkoffice')) return;
                        const key = src.split('?')[0];
                        if (seen.has(key)) return;
                        seen.add(key);
                        allImgs.push(src);
                    });
                };

                // 从顶部开始
                c.scrollTop = 0;
                await delay(500);
                collect();

                // 边滚边收集
                let lastTop = -1, stable = 0;
                for (let i = 0; i < 150; i++) {
                    c.scrollTop += 400;
                    await delay(250);
                    collect();
                    if (c.scrollTop === lastTop) { stable++; if (stable > 3) break; }
                    else { stable = 0; }
                    lastTop = c.scrollTop;
                }

                c.scrollTop = 0;
                window.__feishu_imgs = allImgs;
                return allImgs.length;
            }
            """)
            print(f"[browser_images] 收集到 {img_count} 张图片 URL", file=sys.stderr)

            # 在浏览器内 fetch 所有图片为 base64
            print(f"[browser_images] 在浏览器内 fetch 图片...", file=sys.stderr)
            fetch_results = await page.evaluate("""
            async () => {
                const imgs = window.__feishu_imgs || [];
                const results = [];

                for (let i = 0; i < imgs.length; i++) {
                    const src = imgs[i];
                    try {
                        const resp = await fetch(src, {credentials: 'include', mode: 'cors'});
                        if (!resp.ok) { results.push({i, src: src.substring(0, 200), error: 'HTTP_' + resp.status}); continue; }
                        const blob = await resp.blob();
                        const b64 = await new Promise(resolve => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                        results.push({i, src: src.substring(0, 200), size: blob.size, type: blob.type, data: b64});
                    } catch(e) {
                        // blob URL 失败时尝试用 canvas 截图
                        if (src.startsWith('blob:')) {
                            try {
                                const img = new Image();
                                img.crossOrigin = 'anonymous';
                                await new Promise((resolve, reject) => {
                                    img.onload = resolve;
                                    img.onerror = reject;
                                    img.src = src;
                                });
                                const canvas = document.createElement('canvas');
                                canvas.width = img.naturalWidth;
                                canvas.height = img.naturalHeight;
                                canvas.getContext('2d').drawImage(img, 0, 0);
                                const dataUrl = canvas.toDataURL('image/png');
                                results.push({i, src: src.substring(0, 200), size: dataUrl.length, type: 'image/png', data: dataUrl});
                                continue;
                            } catch(e2) {}
                        }
                        results.push({i, src: src.substring(0, 200), error: e.message});
                    }
                }
                return results;
            }
            """)

            print(f"[browser_images] fetch 完成，处理结果...", file=sys.stderr)

            # 保存到本地
            results = []
            for item in fetch_results:
                idx = item.get("i", 0)
                src = item.get("src", "")
                error = item.get("error")
                if error:
                    results.append({"index": idx, "status": "failed", "error": str(error), "src": src})
                    print(f"  [{idx}] FAIL: {error}", file=sys.stderr)
                    continue

                b64_data = item.get("data", "")
                img_type = item.get("type", "image/png")

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
                target = assets_dir / filename
                target.write_bytes(raw)

                results.append({
                    "index": idx, "filename": filename, "status": "downloaded",
                    "size": len(raw), "type": img_type, "src": src,
                })
                print(f"  [{idx}] OK: {filename} ({len(raw)} bytes)", file=sys.stderr)

            await page.close()
    finally:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=10)

    # 保存 manifest
    manifest_path = output_dir / "ingest" / "ingest" / "browser_asset_manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    downloaded = sum(1 for r in results if r["status"] == "downloaded")
    failed = sum(1 for r in results if r.get("status") == "failed")
    print(f"\n[browser_images] 完成: {downloaded} 下载, {failed} 失败", file=sys.stderr)

    return {
        "total": len(results),
        "downloaded": downloaded,
        "failed": failed,
        "manifest_path": str(manifest_path),
        "assets_dir": str(assets_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Playwright 下载飞书文档图片")
    parser.add_argument("url", help="飞书文档 URL")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("--timeout", type=int, default=90, help="页面加载超时(秒)")
    args = parser.parse_args()

    result = asyncio.run(download_images(args.url, Path(args.output), args.timeout))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
