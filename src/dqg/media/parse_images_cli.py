"""Parse Images CLI: 输出写入 + 命令行入口.

从 parse_images.py 拆分而来。
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import save_json
from dqg.media.parse_images import (
    analyze_assets,
    discover_from_dir,
    discover_from_manifest,
    info,
    load_prompt,
    sanitize_filename,
    warn,
)


def write_outputs(
    results: list[dict[str, Any]],
    output_json: Path,
    output_md: Path,
    details_dir: Path,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    details_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total": len(results),
        "ok": len([r for r in results if r.get("status") == "ok"]),
        "manual_review_required": len([r for r in results if r.get("status") == "manual_review_required"]),
        "failed": len([r for r in results if r.get("status") == "failed"]),
        "items": results,
    }
    save_json(output_json, payload)

    md_lines: list[str] = []
    md_lines.append("# 图片语义解析结果")
    md_lines.append("")
    md_lines.append(f"- 生成时间: {payload['generated_at']}")
    md_lines.append(f"- 总数: {payload['total']}")
    md_lines.append(f"- 成功: {payload['ok']}")
    md_lines.append(f"- 需人工补录: {payload['manual_review_required']}")
    md_lines.append(f"- 失败: {payload['failed']}")
    md_lines.append("")
    md_lines.append("| # | 类型 | Token | 章节 | 状态 | 摘要 |")
    md_lines.append("|---:|---|---|---|---|---|")

    for row in results:
        idx = row["index"]
        token = row.get("token", "")
        token_short = token[:12] + ("..." if len(token) > 12 else "")
        section = row.get("section_path", "") or "-"
        summary = (row.get("summary", "") or "-").replace("|", "\\|")
        status = row.get("status", "")
        md_lines.append(f"| {idx} | {row.get('kind', '-')} | {token_short} | {section} | {status} | {summary} |")

        detail_name = sanitize_filename(f"{idx:03d}_{row.get('kind', 'image')}_{token or 'no_token'}.md")
        detail_path = details_dir / detail_name
        detail_lines = [
            f"# 资产 {idx}",
            "",
            f"- 类型: {row.get('kind', '')}",
            f"- Token: {token}",
            f"- 路径: {row.get('path', '')}",
            f"- 章节: {row.get('section_path', '')}",
            f"- 状态: {status}",
            "",
            "## 解析结果",
            "",
            row.get("analysis", "") or "",
        ]
        if row.get("error"):
            detail_lines.extend(["", "## 错误", "", row["error"]])
        detail_path.write_text("\n".join(detail_lines).strip() + "\n", encoding="utf-8")

    output_md.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse image assets into requirement semantics")
    parser.add_argument("--manifest", help="asset_manifest.json 路径")
    parser.add_argument("--assets-dir", help="图片目录路径（manifest 为空时使用）")
    parser.add_argument("--output-json", required=True, help="输出 JSON 路径")
    parser.add_argument("--output-md", required=True, help="输出 Markdown 路径")
    parser.add_argument("--details-dir", required=True, help="单图明细输出目录")
    parser.add_argument(
        "--backend",
        choices=["auto", "dashscope", "anthropic", "openai", "none"],
        default="auto",
        help="VLM 后端（auto 自动检测环境变量）",
    )
    parser.add_argument("--model", default="", help="VLM 模型名（留空使用各后端默认值）")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--api-key", default=None, help="VLM API Key（也可通过环境变量配置）")
    parser.add_argument("--prompt-file", default=None, help="提示词文件路径")
    parser.add_argument("--max-workers", type=int, default=5, help="VLM 并发数（默认5）")

    args = parser.parse_args()

    assets: list[dict[str, Any]] = []
    if args.manifest:
        manifest_path = Path(args.manifest).expanduser().resolve()
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest 不存在: {manifest_path}")
        assets = discover_from_manifest(manifest_path)
        if not assets:
            # manifest 中所有图片下载失败时，fallback 到同目录 assets/ 扫描
            fallback_dir = manifest_path.parent / "assets"
            if fallback_dir.is_dir():
                info(f"manifest 无可用图片，fallback 到目录扫描: {fallback_dir}")
                assets = discover_from_dir(fallback_dir)
    elif args.assets_dir:
        assets_dir = Path(args.assets_dir).expanduser().resolve()
        if not assets_dir.exists():
            raise FileNotFoundError(f"assets 目录不存在: {assets_dir}")
        assets = discover_from_dir(assets_dir)
    else:
        raise ValueError("必须提供 --manifest 或 --assets-dir")

    if not assets:
        warn("未发现可解析图片")

    prompt = load_prompt(Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None)
    api_key = (
        args.api_key
        or os.getenv("DASHSCOPE_API_KEY", "")
        or os.getenv("ANTHROPIC_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
    )

    output_json = Path(args.output_json).expanduser().resolve()

    results = analyze_assets(
        assets=assets,
        backend=args.backend,
        prompt=prompt,
        model=args.model,
        timeout=args.timeout,
        api_key=api_key,
        cache_path=output_json if output_json.exists() else None,
        max_workers=args.max_workers,
    )

    output_md = Path(args.output_md).expanduser().resolve()
    details_dir = Path(args.details_dir).expanduser().resolve()

    write_outputs(results, output_json, output_md, details_dir)

    info(f"输出 JSON: {output_json}")
    info(f"输出 Markdown: {output_md}")
    info(f"输出明细目录: {details_dir}")
    info(
        "统计: "
        f"total={len(results)}, ok={len([r for r in results if r.get('status') == 'ok'])}, "
        f"manual={len([r for r in results if r.get('status') == 'manual_review_required'])}, "
        f"failed={len([r for r in results if r.get('status') == 'failed'])}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
