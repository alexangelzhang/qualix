#!/usr/bin/env python3
"""文档分块摘要：用小模型对 plain_text 按章节做结构化摘要.

将 ~30KB 原文压缩为 ~5KB 结构化摘要，供下游 Phase 消费，
避免大模型重复处理完整原文。

输入: plain_text.txt（飞书 ingest 产物）
输出: plain_text_summary.md（结构化摘要）

支持的 backend:
- dashscope: 调用 DashScope qwen-plus（默认）
- none: 跳过摘要，输出原文分块标记
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any


def info(msg: str) -> None:
    print(f"[summarize_text] {msg}")


def warn(msg: str) -> None:
    print(f"[summarize_text][WARN] {msg}", file=sys.stderr)


# --- 分块逻辑 ---

def split_into_sections(text: str, max_chars: int = 6000, min_section_chars: int = 100) -> list[dict[str, str]]:
    """按标题行分块，超长段落再按段落拆分.

    Args:
        text: 原始文本
        max_chars: 单章节最大字符数
        min_section_chars: 最小章节字符数，过短的段落合并到上一章节

    Returns:
        list of {"title": str, "content": str}
    """
    lines = text.split("\n")
    sections: list[dict[str, str]] = []
    current_title = "文档开头"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # 检测标题行：# 开头，或中文标题格式（数字+点/顿号+至少2个中文字符）
        is_heading = (
            bool(re.match(r"^#{1,4}\s+\S", line))
            or bool(re.match(r"^\d+[\.\、]\s*[\u4e00-\u9fff]{2,}", stripped))
        )
        if is_heading and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append({"title": current_title, "content": content})
            current_title = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    # 最后一段
    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append({"title": current_title, "content": content})

    # 合并过短的章节到前一个
    merged: list[dict[str, str]] = []
    for sec in sections:
        if merged and len(sec["content"]) < min_section_chars:
            merged[-1]["content"] += f"\n\n### {sec['title']}\n{sec['content']}"
        else:
            merged.append(sec)

    # 超长段落再拆分
    result: list[dict[str, str]] = []
    for sec in merged:
        if len(sec["content"]) <= max_chars:
            result.append(sec)
        else:
            paragraphs = sec["content"].split("\n\n")
            chunk_lines: list[str] = []
            chunk_len = 0
            part = 1
            for para in paragraphs:
                if chunk_len + len(para) > max_chars and chunk_lines:
                    result.append({
                        "title": f"{sec['title']}（第{part}部分）",
                        "content": "\n\n".join(chunk_lines),
                    })
                    part += 1
                    chunk_lines = []
                    chunk_len = 0
                chunk_lines.append(para)
                chunk_len += len(para)
            if chunk_lines:
                title = f"{sec['title']}（第{part}部分）" if part > 1 else sec["title"]
                result.append({"title": title, "content": "\n\n".join(chunk_lines)})

    return result


# --- DashScope 文本摘要 ---

def call_dashscope_text(
    api_key: str,
    text: str,
    section_title: str,
    model: str = "qwen-plus",
    timeout: int = 60,
) -> str:
    """调用 DashScope 文本模型做结构化摘要."""
    try:
        import dashscope  # type: ignore
        dashscope.api_key = api_key
    except ImportError:
        raise RuntimeError("dashscope 未安装，请 pip install dashscope")

    prompt = (
        f"你是需求文档摘要助手。以下是文档章节「{section_title}」的内容。\n"
        "请提取其中的关键业务信息，输出结构化摘要：\n"
        "1) 核心功能点（按条列出）\n"
        "2) 关键业务规则和约束\n"
        "3) 涉及的状态/流程变化\n"
        "4) 明显的缺口或待确认项\n"
        "要求：保留具体数值、枚举值、字段名等关键细节，删除冗余描述。输出中文。\n\n"
        f"---\n{text}\n---"
    )

    response = dashscope.Generation.call(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout=timeout,
        result_format="message",
    )

    if getattr(response, "status_code", None) != 200:
        code = getattr(response, "code", "unknown")
        msg = getattr(response, "message", "unknown error")
        raise RuntimeError(f"DashScope 调用失败: code={code}, message={msg}")

    output = response.output if hasattr(response, "output") else {}
    choices = output.get("choices", []) if isinstance(output, dict) else []
    if not choices:
        raise RuntimeError("DashScope 返回内容为空")

    message = choices[0].get("message", {})
    return message.get("content", "").strip()


def summarize_section(
    section: dict[str, str],
    api_key: str,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    """摘要单个章节."""
    title = section["title"]
    content = section["content"]
    original_chars = len(content)

    if not api_key:
        return {
            "title": title,
            "summary": content,  # 无 API Key 时保留原文
            "original_chars": original_chars,
            "summary_chars": original_chars,
            "status": "passthrough",
        }

    try:
        summary = call_dashscope_text(
            api_key=api_key,
            text=content,
            section_title=title,
            model=model,
            timeout=timeout,
        )
        return {
            "title": title,
            "summary": summary,
            "original_chars": original_chars,
            "summary_chars": len(summary),
            "status": "ok",
        }
    except Exception as exc:
        warn(f"章节「{title}」摘要失败: {exc}")
        return {
            "title": title,
            "summary": content,  # 失败时保留原文
            "original_chars": original_chars,
            "summary_chars": original_chars,
            "status": "failed",
            "error": str(exc),
        }


def summarize_document(
    text: str,
    api_key: str,
    model: str = "qwen-plus",
    timeout: int = 60,
    max_workers: int = 3,
    max_section_chars: int = 6000,
) -> dict[str, Any]:
    """对完整文档做分块摘要.

    Returns:
        {"sections": [...], "full_summary": str, "stats": {...}}
    """
    sections = split_into_sections(text, max_chars=max_section_chars)
    info(f"文档分为 {len(sections)} 个章节")

    results: list[dict[str, Any]] = []

    if api_key and len(sections) > 1:
        effective_workers = min(max_workers, len(sections))
        info(f"并发摘要（{effective_workers} workers）")
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_map = {
                executor.submit(
                    summarize_section, sec, api_key, model, timeout
                ): i
                for i, sec in enumerate(sections)
            }
            indexed_results: dict[int, dict[str, Any]] = {}
            for future in as_completed(future_map):
                i = future_map[future]
                try:
                    indexed_results[i] = future.result()
                except Exception as exc:
                    indexed_results[i] = {
                        "title": sections[i]["title"],
                        "summary": sections[i]["content"],
                        "original_chars": len(sections[i]["content"]),
                        "summary_chars": len(sections[i]["content"]),
                        "status": "failed",
                        "error": str(exc),
                    }
            results = [indexed_results[i] for i in range(len(sections))]
    else:
        for sec in sections:
            results.append(summarize_section(sec, api_key, model, timeout))

    total_original = sum(r["original_chars"] for r in results)
    total_summary = sum(r["summary_chars"] for r in results)
    ok_count = sum(1 for r in results if r["status"] == "ok")

    return {
        "sections": results,
        "stats": {
            "total_sections": len(results),
            "ok": ok_count,
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "passthrough": sum(1 for r in results if r["status"] == "passthrough"),
            "original_chars": total_original,
            "summary_chars": total_summary,
            "compression_ratio": f"{total_summary / max(total_original, 1):.1%}",
        },
    }


def write_summary_outputs(
    result: dict[str, Any],
    output_md: Path,
    output_json: Path | None = None,
) -> None:
    """写入摘要产物."""
    output_md.parent.mkdir(parents=True, exist_ok=True)

    md_lines = [
        "# 文档结构化摘要",
        "",
        f"- 生成时间: {datetime.now().isoformat()}",
        f"- 章节数: {result['stats']['total_sections']}",
        f"- 原文字符: {result['stats']['original_chars']}",
        f"- 摘要字符: {result['stats']['summary_chars']}",
        f"- 压缩率: {result['stats']['compression_ratio']}",
        "",
    ]

    for sec in result["sections"]:
        md_lines.append(f"## {sec['title']}")
        md_lines.append("")
        md_lines.append(sec["summary"])
        md_lines.append("")

    output_md.write_text("\n".join(md_lines).strip() + "\n", encoding="utf-8")

    if output_json:
        from dqg.json_utils import save_json
        save_json(output_json, result)


def main() -> int:
    parser = argparse.ArgumentParser(description="文档分块摘要（小模型预处理）")
    parser.add_argument("--input", required=True, help="plain_text.txt 路径")
    parser.add_argument("--output-md", required=True, help="输出摘要 Markdown 路径")
    parser.add_argument("--output-json", default=None, help="输出摘要 JSON 路径（可选）")
    parser.add_argument("--model", default="qwen-plus", help="DashScope 文本模型")
    parser.add_argument("--timeout", type=int, default=60, help="单次调用超时（秒）")
    parser.add_argument("--max-workers", type=int, default=3, help="并发数")
    parser.add_argument("--max-section-chars", type=int, default=6000, help="单章节最大字符数")
    parser.add_argument("--api-key", default=None, help="DashScope API Key")

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    text = input_path.read_text(encoding="utf-8")
    if not text.strip():
        warn("输入文件为空")
        return 0

    api_key = args.api_key or os.getenv("DASHSCOPE_API_KEY", "")

    result = summarize_document(
        text=text,
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        max_workers=args.max_workers,
        max_section_chars=args.max_section_chars,
    )

    output_md = Path(args.output_md).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve() if args.output_json else None

    write_summary_outputs(result, output_md, output_json)

    stats = result["stats"]
    info(f"摘要完成: {stats['total_sections']} 章节, "
         f"{stats['original_chars']} → {stats['summary_chars']} 字符 "
         f"({stats['compression_ratio']})")
    info(f"输出: {output_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
