"""agent-browser fallback for failed board/mindnote downloads.

When API download returns 403 for boards/mindnotes, fall back to
agent-browser --auto-connect which reuses the user's authenticated
Chrome session to screenshot whiteboard elements directly from the
Feishu document page.

Best-effort: if agent-browser is unavailable or Chrome is not logged in,
the fallback silently skips without blocking the main ingest flow.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from dqg.ingest.common import info, warn

_FALLBACK_KINDS = {"board", "mindnote"}
_WHITEBOARD_SELECTOR = ".whiteboard-block_container"
_SCROLL_CONTAINER = ".bear-web-x-container"


def _run(args: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return -1, str(exc)


def _agent_browser_available() -> bool:
    return shutil.which("agent-browser") is not None


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _playwright_fallback_boards(
    asset_results: list[dict[str, Any]],
    feishu_url: str,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """用 playwright CDP 模式截图失败的 board/mindnote 资源。"""
    failed = [
        (i, r) for i, r in enumerate(asset_results) if r.get("status") == "failed" and r.get("kind") in _FALLBACK_KINDS
    ]
    if not failed:
        return asset_results

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        warn("[browser_fallback] playwright 未安装，跳过 playwright fallback")
        return asset_results

    info(f"[browser_fallback] 尝试 playwright CDP fallback: {len(failed)} 个画板/思维导图")
    output_dir.mkdir(parents=True, exist_ok=True)
    recovered = 0

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            except Exception as exc:
                warn(f"[browser_fallback] playwright CDP 连接失败（Chrome 未启动？）: {exc}")
                return asset_results

            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()

            try:
                page.goto(feishu_url, wait_until="networkidle", timeout=60000)
            except Exception as exc:
                warn(f"[browser_fallback] playwright 打开文档失败: {exc}")
                page.close()
                browser.close()
                return asset_results

            title = page.title()
            if "登录" in title or "login" in title.lower():
                warn(f"[browser_fallback] 飞书未登录，跳过 playwright fallback (title={title})")
                page.close()
                browser.close()
                return asset_results

            info(f"[browser_fallback] playwright 文档已打开: {title[:60]}")
            time.sleep(2)

            for idx, result in failed:
                token = result.get("token", "")
                kind = result.get("kind", "board")
                section = result.get("section_path", "")
                target = Path(result.get("path", ""))
                if not target.name:
                    target = output_dir / f"{kind}_{token}.png"

                if section:
                    js_scroll = (
                        f"(function(){{"
                        f"const links = document.querySelectorAll('a[href*=\"#\"]');"
                        f"for (const a of links) {{"
                        f"  if (a.textContent.includes({section!r})) {{"
                        f"    a.click(); return 'ok';"
                        f"  }}"
                        f"}}"
                        f"return 'not_found';"
                        f"}})()"
                    )
                    page.evaluate(js_scroll)
                    time.sleep(1.5)

                cap_id = f"dqg-pw-{idx}"
                js_find = (
                    f"(function(){{"
                    f"const wbs = document.querySelectorAll('{_WHITEBOARD_SELECTOR}');"
                    f"for (const w of wbs) {{"
                    f"  const r = w.getBoundingClientRect();"
                    f"  if (r.top > -200 && r.top < 1200 && r.height > 20) {{"
                    f"    w.scrollIntoView({{block:'center'}}); w.click();"
                    f"    w.id = '{cap_id}';"
                    f"    return JSON.stringify({{ok:true}});"
                    f"  }}"
                    f"}}"
                    f"return JSON.stringify({{ok:false}});"
                    f"}})()"
                )
                out = page.evaluate(js_find)
                if not out or '"ok":false' in str(out) or '"ok": false' in str(out):
                    warn(f"[browser_fallback] playwright ✗ {kind} {token[:12]}... 未找到元素")
                    result["attempts"].append(
                        {
                            "attempt": len(result.get("attempts", [])) + 1,
                            "local_retry": 1,
                            "use_user_token": None,
                            "error": "playwright_element_not_found",
                            "error_type": "browser_fallback_failed",
                        }
                    )
                    continue

                time.sleep(0.5)
                try:
                    page.locator(f"#{cap_id}").screenshot(path=str(target))
                    if target.exists() and target.stat().st_size > 500:
                        result["status"] = "downloaded"
                        result["error"] = ""
                        result["error_type"] = ""
                        result["failure_category"] = ""
                        result["path"] = str(target)
                        result["attempts"].append(
                            {
                                "attempt": len(result.get("attempts", [])) + 1,
                                "local_retry": 1,
                                "use_user_token": None,
                                "error": "",
                                "error_type": "playwright_fallback_success",
                            }
                        )
                        recovered += 1
                        info(f"[browser_fallback] playwright ✓ {kind} {token[:12]}... → {target.name}")
                    else:
                        raise RuntimeError("screenshot too small or missing")
                except Exception as exc:
                    warn(f"[browser_fallback] playwright ✗ {kind} {token[:12]}... 截图失败: {exc}")
                    result["attempts"].append(
                        {
                            "attempt": len(result.get("attempts", [])) + 1,
                            "local_retry": 1,
                            "use_user_token": None,
                            "error": str(exc),
                            "error_type": "browser_fallback_failed",
                        }
                    )

            page.close()
            browser.close()

    except Exception as exc:
        warn(f"[browser_fallback] playwright fallback 异常: {exc}")

    info(f"[browser_fallback] playwright 完成: {recovered}/{len(failed)} 恢复")
    return asset_results


def _open_document(url: str) -> bool:
    rc, out = _run(["agent-browser", "--auto-connect", "open", url], timeout=60)
    if rc != 0:
        warn(f"[browser_fallback] agent-browser open failed: {out}")
        return False
    rc, title = _run(["agent-browser", "get", "title"])
    if rc != 0 or "登录" in title or "login" in title.lower():
        warn(f"[browser_fallback] 飞书未登录，跳过 browser fallback (title={title})")
        _run(["agent-browser", "close"])
        return False
    info(f"[browser_fallback] 文档已打开: {title[:60]}")
    return True


def _scroll_to_section(anchor: str) -> bool:
    js = (
        f"(function(){{ "
        f"const a = document.querySelector('a[href*=\"{anchor}\"]'); "
        f"if(a) {{ a.click(); return 'ok'; }} return 'not_found'; "
        f"}})()"
    )
    rc, out = _run(["agent-browser", "eval", js])
    if rc != 0 or "not_found" in out:
        return False
    time.sleep(1.5)
    return True


def _find_and_capture_board(board_index: int, target: Path) -> bool:
    cap_id = f"dqg-cap-{board_index}"
    js = (
        f"(function(){{ "
        f"const wbs = document.querySelectorAll('{_WHITEBOARD_SELECTOR}'); "
        f"for (const w of wbs) {{ "
        f"  const r = w.getBoundingClientRect(); "
        f"  if (r.top > -200 && r.top < 1200 && r.height > 20) {{ "
        f"    w.scrollIntoView({{block:'center'}}); w.click(); "
        f"    w.id = '{cap_id}'; "
        f"    return JSON.stringify({{ok:true, top:Math.round(r.top), h:Math.round(r.height)}}); "
        f"  }} "
        f"}} "
        f"return JSON.stringify({{ok:false, count:wbs.length}}); "
        f"}})()"
    )
    rc, out = _run(["agent-browser", "eval", js])
    if rc != 0:
        return False

    if '"ok":false' in out or '"ok": false' in out:
        return False

    time.sleep(0.5)
    rc, _ = _run(
        ["agent-browser", "screenshot", f"#{cap_id}", str(target)],
        timeout=15,
    )
    return rc == 0 and target.exists() and target.stat().st_size > 500


def _collect_toc_anchors() -> dict[str, str]:
    js = (
        "(function(){ "
        "const links = document.querySelectorAll('a[href*=\"#\"]'); "
        "const m = {}; "
        "links.forEach(a => { "
        "  const h = a.getAttribute('href') || ''; "
        "  const parts = h.split('#'); "
        "  if (parts.length > 1) { m[a.textContent.trim()] = parts[parts.length-1]; } "
        "}); "
        "return JSON.stringify(m); "
        "})()"
    )
    rc, out = _run(["agent-browser", "eval", js])
    if rc != 0:
        return {}
    try:
        import json

        return json.loads(out.strip('"').replace('\\"', '"'))
    except (ValueError, TypeError):
        return {}


def browser_fallback_boards(
    asset_results: list[dict[str, Any]],
    feishu_url: str,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Try agent-browser screenshot for failed board/mindnote assets.

    Modifies asset_results in-place and returns the same list.
    """
    failed = [
        (i, r) for i, r in enumerate(asset_results) if r.get("status") == "failed" and r.get("kind") in _FALLBACK_KINDS
    ]
    if not failed:
        return asset_results

    if not _agent_browser_available():
        warn(
            f"[browser_fallback] agent-browser 未安装，尝试 playwright fallback ({len(failed)} 个画板资源)。"
            " 如需安装 agent-browser: npm i -g agent-browser && agent-browser install"
        )
        if _playwright_available():
            return _playwright_fallback_boards(asset_results, feishu_url, output_dir)
        warn(
            "[browser_fallback] playwright 也未安装，跳过画板截图。pip install playwright && playwright install chromium"
        )
        return asset_results

    info(f"[browser_fallback] 尝试 browser fallback: {len(failed)} 个画板/思维导图")

    if not _open_document(feishu_url):
        return asset_results

    output_dir.mkdir(parents=True, exist_ok=True)
    toc = _collect_toc_anchors()
    recovered = 0

    for idx, result in failed:
        token = result.get("token", "")
        section = result.get("section_path", "")
        kind = result.get("kind", "board")
        target = Path(result.get("path", ""))
        if not target.name:
            target = output_dir / f"{kind}_{token}.png"

        if section and toc:
            anchor = toc.get(section, "")
            if anchor:
                _scroll_to_section(anchor)
            else:
                for toc_text, toc_anchor in toc.items():
                    if section in toc_text or toc_text in section:
                        _scroll_to_section(toc_anchor)
                        break

        ok = _find_and_capture_board(idx, target)
        if ok:
            result["status"] = "downloaded"
            result["error"] = ""
            result["error_type"] = ""
            result["failure_category"] = ""
            result["path"] = str(target)
            result["attempts"].append(
                {
                    "attempt": len(result.get("attempts", [])) + 1,
                    "local_retry": 1,
                    "use_user_token": None,
                    "error": "",
                    "error_type": "browser_fallback_success",
                }
            )
            recovered += 1
            info(f"[browser_fallback] ✓ {kind} {token[:12]}... → {target.name}")
        else:
            result["attempts"].append(
                {
                    "attempt": len(result.get("attempts", [])) + 1,
                    "local_retry": 1,
                    "use_user_token": None,
                    "error": "browser_fallback_screenshot_failed",
                    "error_type": "browser_fallback_failed",
                }
            )
            warn(f"[browser_fallback] ✗ {kind} {token[:12]}... 截图失败")

    _run(["agent-browser", "close"])
    info(f"[browser_fallback] 完成: {recovered}/{len(failed)} 恢复")
    return asset_results
