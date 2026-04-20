"""LLM-Wiki 管理器：编译与清理当前项目的 `.dqg-wiki`."""

from __future__ import annotations

from pathlib import Path

from dqg.constants import WIKI_COMPILE_CONTEXT_LIMIT, WIKI_DIR, WIKI_LINT_FILE_EXCERPT_LIMIT, WIKI_LINT_TOTAL_EXCERPT_LIMIT, WIKI_RAW_TEXT_FALLBACK_LIMIT
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.path_utils import resolve_ingest_file, resolve_internal_file


def _read_excerpt(path: Path, limit: int) -> str:
    """读取受限摘录，避免把整份大文件塞入 prompt."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    if len(text) > limit:
        return text[:limit] + "\n...(截断)"
    return text


def _find_phase_file(output_dir: Path, project_id: str, phase_id: str, filename: str) -> Path:
    """定位 Phase 目录中的文件，兼容旧布局与新布局。"""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return output_dir / project_id / filename
    phase_root = _phase_dir(output_dir, project_id, phase_def)
    if filename in {"plain_text_summary.md", "plain_text.txt"}:
        return resolve_ingest_file(phase_root, filename)
    return resolve_internal_file(phase_root, filename)


class WikiManager:
    """管理 `.dqg-wiki` 的编译和 lint。"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def _wiki_root(self) -> Path:
        return Path(WIKI_DIR)

    def _load_compile_context(self, project_id: str) -> str:
        """优先使用摘要，fallback 到原始文本，并截断到固定上限。"""
        phase_a = _find_phase_file(self.output_dir, project_id, "Q01", "plain_text_summary.md")
        summary = _read_excerpt(phase_a, WIKI_COMPILE_CONTEXT_LIMIT)
        if summary:
            return summary

        raw_text = _read_excerpt(_find_phase_file(self.output_dir, project_id, "Q01", "plain_text.txt"), WIKI_RAW_TEXT_FALLBACK_LIMIT)
        return raw_text

    def _collect_lint_bundle(self, project_id: str) -> str:
        """收集当前 wiki 的受限摘录，供 lint 使用。"""
        wiki_root = self._wiki_root()
        if not wiki_root.exists():
            return ""

        parts: list[str] = []
        used = 0
        for md_file in sorted(wiki_root.rglob("*.md")):
            excerpt = _read_excerpt(md_file, WIKI_LINT_FILE_EXCERPT_LIMIT)
            if not excerpt:
                continue
            remaining = WIKI_LINT_TOTAL_EXCERPT_LIMIT - used
            if remaining <= 0:
                break
            if len(excerpt) > remaining:
                excerpt = excerpt[:remaining] + "\n...(截断)"
            parts.append(f"<!-- {md_file.relative_to(wiki_root)} -->\n{excerpt}")
            used += len(excerpt)

        return "\n\n".join(parts)

    def compile_wiki(self, project_id: str) -> str:
        """编译初始 wiki 文本，保持调用面兼容。"""
        context = self._load_compile_context(project_id)
        if not context:
            return "[Wiki] 没有可用的编译上下文。"
        return context

    def lint_wiki(self, project_id: str) -> str:
        """整理当前 wiki 的受限摘录，供 lint/清理使用。"""
        bundle = self._collect_lint_bundle(project_id)
        if not bundle:
            return "[Wiki] 当前没有可 lint 的 wiki 内容。"
        return bundle
