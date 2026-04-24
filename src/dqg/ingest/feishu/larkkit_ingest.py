"""larkkit CLI 集成模块 — 调用 larkkit download 获取文档文本、评论、表格.

图片下载由于 API 权限限制（403），仍走现有浏览器/API 方案。
本模块只负责文本层面的摄入，输出 DQG 标准格式。

Usage:
    result = ingest_via_larkkit(url, output_dir)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.ingest.common import info
from dqg.json_utils import dump_json_str
from dqg.log import get_logger

log = get_logger(__name__)


def _find_larkkit_bin() -> str:
    """定位 larkkit 可执行文件."""
    # 优先用 PATH 中的
    which = shutil.which("larkkit")
    if which:
        return which
    # fallback: 常见 uv 安装位置
    home_bin = Path.home() / ".local/bin/larkkit"
    if home_bin.exists():
        return str(home_bin)
    raise RuntimeError("找不到 larkkit CLI。请先安装: pip install larkkit 或 uv tool install larkkit")


def _run_larkkit_download(
    url: str,
    output_dir: Path,
    *,
    no_images: bool = True,
    no_comments: bool = False,
    use_user_token: bool = True,
    timeout: int = 120,
) -> tuple[bool, str, str]:
    """调用 larkkit download CLI."""
    bin_path = _find_larkkit_bin()
    cmd = [bin_path, "download", url, "-o", str(output_dir)]
    if no_images:
        cmd.append("--no-images")
    if no_comments:
        cmd.append("--no-comments")
    if use_user_token:
        cmd.append("--use-user-token")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"larkkit download timeout after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def _find_output_files(output_dir: Path) -> dict[str, Path | None]:
    """在 larkkit 输出目录中定位生成的文件."""
    md_files = sorted(output_dir.glob("*.md"))

    doc_md: Path | None = None
    comments_md: Path | None = None
    report_md: Path | None = None

    for f in md_files:
        name = f.name
        if name.startswith("download_report"):
            report_md = f
        elif name.endswith("_comments.md"):
            comments_md = f
        elif not name.startswith("download_report"):
            doc_md = f

    return {
        "doc_md": doc_md,
        "comments_md": comments_md,
        "report_md": report_md,
    }


def _extract_title_from_md(md_path: Path) -> str:
    """从 Markdown 文件第一行 # 标题提取文档标题."""
    try:
        first_line = md_path.read_text(encoding="utf-8").split("\n", 1)[0]
        if first_line.startswith("# "):
            return first_line[2:].strip()
    except Exception:
        log.debug("Failed to extract title from %s", md_path, exc_info=True)
    return md_path.stem


def _parse_report_stats(report_path: Path | None) -> dict[str, int]:
    """从 download_report 提取统计信息."""
    stats: dict[str, int] = {"image_count": 0, "comment_count": 0, "char_count": 0}
    if not report_path or not report_path.exists():
        return stats
    try:
        text = report_path.read_text(encoding="utf-8")
        m = re.search(r"\*\*图片数\*\*\s*\|\s*(\d+)", text)
        if m:
            stats["image_count"] = int(m.group(1))
        m = re.search(r"\*\*评论数\*\*\s*\|\s*(\d+)", text)
        if m:
            stats["comment_count"] = int(m.group(1))
        m = re.search(r"\*\*字符数\*\*\s*\|\s*([\d,]+)", text)
        if m:
            stats["char_count"] = int(m.group(1).replace(",", ""))
    except Exception:
        log.debug("Failed to parse report stats", exc_info=True)
    return stats


def ingest_via_larkkit(
    url: str,
    output_dir: Path,
    *,
    use_user_token: bool = True,
    timeout: int = 120,
) -> dict[str, Any]:
    """通过 larkkit CLI 摄入飞书文档.

    输出文件写入 output_dir/ingest/ 目录：
    - plain_text.txt: 文档 Markdown 全文
    - comments.md: 评论详情
    - ingest.json: 摄入元数据

    Args:
        url: 飞书文档 URL
        output_dir: 项目 Phase 输出目录（如 output/kind-care/Q01）
        use_user_token: 是否使用 user token
        timeout: CLI 超时秒数

    Returns:
        ingest 结果字典，兼容 ingest_single_document 返回格式
    """
    ingest_subdir = output_dir / "ingest"
    ingest_subdir.mkdir(parents=True, exist_ok=True)

    # larkkit 输出到临时目录，再搬到标准位置
    with tempfile.TemporaryDirectory(prefix="larkkit_") as tmp:
        tmp_dir = Path(tmp)
        info(f"[larkkit] 下载文档: {url}")

        ok, stdout, stderr = _run_larkkit_download(
            url,
            tmp_dir,
            no_images=True,
            use_user_token=use_user_token,
            timeout=timeout,
        )

        if not ok:
            raise RuntimeError(f"larkkit download 失败: {stderr[:500]}")

        files = _find_output_files(tmp_dir)
        if not files["doc_md"]:
            raise RuntimeError(
                f"larkkit 输出中未找到文档 Markdown 文件。目录内容: {[f.name for f in tmp_dir.iterdir()]}"
            )

        # 提取元数据
        doc_md_path = files["doc_md"]
        title = _extract_title_from_md(doc_md_path)
        report_stats = _parse_report_stats(files["report_md"])

        # 复制到标准位置
        plain_text_path = ingest_subdir / "plain_text.txt"
        shutil.copy2(doc_md_path, plain_text_path)
        info(f"[larkkit] 文档已保存: {plain_text_path}")

        comments_path: str = ""
        if files["comments_md"] and files["comments_md"].exists():
            target = ingest_subdir / "comments.md"
            shutil.copy2(files["comments_md"], target)
            comments_path = str(target)
            info(f"[larkkit] 评论已保存: {target} ({report_stats['comment_count']} 条)")

        if files["report_md"] and files["report_md"].exists():
            shutil.copy2(files["report_md"], ingest_subdir / "download_report.md")

    # 构建 ingest.json
    ingest_payload = {
        "source": {
            "url": url,
            "title": title,
            "ingest_method": "larkkit",
            "larkkit_version": _get_larkkit_version(),
            "generated_at": datetime.now().isoformat(),
        },
        "summary": {
            "char_count": report_stats["char_count"],
            "image_count": report_stats["image_count"],
            "comment_count": report_stats["comment_count"],
            "images_downloaded": False,
        },
    }

    ingest_path = ingest_subdir / "ingest.json"
    ingest_path.write_text(dump_json_str(ingest_payload), encoding="utf-8")

    return {
        "status": "ok",
        "url": url,
        "title": title,
        "ingest_method": "larkkit",
        "ingest_path": str(ingest_path),
        "plain_text_path": str(plain_text_path),
        "comments_path": comments_path,
        "asset_manifest_path": "",
        "raw_blocks_path": "",
        "mention_docs": [],
        "summary": ingest_payload["summary"],
    }


def _get_larkkit_version() -> str:
    """获取 larkkit 版本号."""
    try:
        bin_path = _find_larkkit_bin()
        result = subprocess.run(
            [bin_path, "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        m = re.search(r"版本号:\s*([\d.]+)", result.stdout)
        if m:
            return m.group(1)
    except Exception:
        log.debug("Failed to get larkkit version", exc_info=True)
    return "unknown"
