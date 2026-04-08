"""统一记忆层：整合所有缓存和知识系统为单一 API.

DQG Memory Layer
├── 事实存储: REQ/BR/SE/GAP/OPEN 结构化事实
├── 时序图谱: 需求版本演进 + 过期标记
├── 知识网络: 跨项目/跨Phase 知识链接
├── 语义缓存: 重复查询直接返回
├── 图片缓存: 图片语义 FTS5 索引
├── 文本缓存: 文档分段 FTS5 索引
├── 文档摘要: 长文档自动压缩
└── 代码搜索: 业务概念→代码关键词映射 + 结构索引
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from dqg.cache.code_search import format_search_results, index_java_repo, search_code
from dqg.cache.fact_cache import index_phase_facts, search_facts
from dqg.cache.image_cache import save_batch as save_image_batch
from dqg.cache.image_cache import search_image_semantics
from dqg.cache.semantic_cache import cache_invalidate, cache_stats, cached_search
from dqg.cache.text_cache import cache_document, get_cache_stats, is_cached, search_text
from dqg.constants import MEMORY_INDEX_STATE_FILE
from dqg.context.doc_summary import generate_summary_file
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json, save_json
from dqg.memory.knowledge_network import (
    build_cross_project_links,
    format_insights,
    get_cross_project_insights,
    index_bug_cases,
    index_project_facts,
)
from dqg.memory.version_tracker import (
    extract_facts_from_json,
    get_changes_since,
    get_fact_history,
    track_version,
)
from dqg.text_utils import STRUCTURED_JSON_MAP


class MemoryLayer:
    """统一记忆层 API."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def _phase_root(self, project_id: str, phase_id: str) -> Path | None:
        phase_def = PHASE_DEFS.get(phase_id)
        if not phase_def:
            return None
        return _phase_dir(self.output_dir, project_id, phase_def)

    def _index_state_path(self, project_id: str, phase_id: str) -> Path | None:
        phase_def = PHASE_DEFS.get(phase_id)
        if not phase_def:
            return None
        return _internal_dir(self.output_dir, project_id, phase_def) / MEMORY_INDEX_STATE_FILE

    def _candidate_index_paths(self, project_id: str, phase_id: str) -> list[Path]:
        phase_root = self._phase_root(project_id, phase_id)
        if phase_root is None:
            return []

        candidates: list[Path] = []
        json_file = STRUCTURED_JSON_MAP.get(phase_id)
        if json_file:
            candidates.append(phase_root / json_file)

        for filename in ("aggregate_plain_text.txt", "plain_text.txt"):
            candidates.append(phase_root / "ingest" / filename)
            candidates.append(phase_root / filename)

        return [path for path in candidates if path.exists() and path.is_file()]

    def _collect_phase_signatures(self, project_id: str, phase_id: str) -> dict[str, str]:
        phase_root = self._phase_root(project_id, phase_id)
        if phase_root is None or not phase_root.exists():
            return {}

        signatures: dict[str, str] = {}
        for path in self._candidate_index_paths(project_id, phase_id):
            stat = path.stat()
            rel = path.relative_to(phase_root).as_posix()
            signatures[rel] = f"{stat.st_mtime_ns}:{stat.st_size}"
        return signatures

    def _build_index_signature(self, project_id: str, phase_id: str) -> str:
        signatures = self._collect_phase_signatures(project_id, phase_id)
        payload = "\n".join(f"{key}:{value}" for key, value in signatures.items())
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load_index_state(self, project_id: str, phase_id: str) -> dict[str, Any]:
        state_path = self._index_state_path(project_id, phase_id)
        if state_path is None:
            return {}
        data = load_json(state_path)
        return data if isinstance(data, dict) else {}

    def _save_index_state(self, project_id: str, phase_id: str, state: dict[str, Any]) -> None:
        state_path = self._index_state_path(project_id, phase_id)
        if state_path is None:
            return
        save_json(state_path, state)

    def _project_fact_cache_version(self, project_id: str) -> str:
        parts: list[str] = []
        for phase_id in PHASE_DEFS:
            state = self._load_index_state(project_id, phase_id)
            signature = state.get("signature")
            if signature:
                parts.append(f"{phase_id}:{signature}")
        if not parts:
            return project_id
        payload = "\n".join(sorted(parts))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        return f"{project_id}:{digest}"

    def _invalidate_project_fact_search_cache(self, project_id: str) -> None:
        cache_invalidate(self.output_dir, project_id=project_id, result_type="fact")

    # ----- 搜索（统一入口）-----

    def search(
        self,
        query: str,
        project_id: str | None = None,
        scope: str = "all",
        limit: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        """统一搜索：同时查事实/图片/文本/代码，返回分类结果.

        scope: "all" | "facts" | "images" | "text" | "code"
        """
        results: dict[str, list[dict[str, Any]]] = {}

        if scope in ("all", "facts"):
            if project_id:
                facts, _ = cached_search(
                    self.output_dir,
                    query,
                    search_facts,
                    result_type="fact",
                    project_id=project_id,
                    limit=limit,
                    cache_version=self._project_fact_cache_version(project_id),
                )
            else:
                facts = search_facts(self.output_dir, query, limit=limit)
            results["facts"] = facts if isinstance(facts, list) else []

        if scope in ("all", "images"):
            results["images"] = search_image_semantics(self.output_dir, query, project_id=project_id, limit=limit)

        if scope in ("all", "text"):
            results["text"] = search_text(self.output_dir, query, project_id=project_id, limit=limit)

        if scope in ("all", "code"):
            results["code"] = search_code(self.output_dir, query, limit=limit)

        return results

    # ----- 索引（Phase 完成后调用）-----

    def index_phase(self, project_id: str, phase_id: str, force: bool = False) -> dict[str, Any]:
        """索引一个 Phase 的所有产物，支持按签名跳过未变化重建。"""
        counts: dict[str, Any] = {}
        current_signature = self._build_index_signature(project_id, phase_id)
        state = self._load_index_state(project_id, phase_id)
        previous_signature = state.get("signature", "")

        if not force and current_signature and current_signature == previous_signature:
            counts["skipped"] = 1
            counts["signature_unchanged"] = 1
            counts["reindexed"] = 0
            counts["facts"] = state.get("facts", 0)
            counts["knowledge_nodes"] = state.get("knowledge_nodes", 0)
            counts["version_changes"] = state.get("version_changes", 0)
            counts["summary_generated"] = 0
            counts["version_diff"] = None
            return counts

        counts["reindexed"] = 1
        counts["facts"] = index_phase_facts(self.output_dir, project_id, phase_id)
        counts["knowledge_nodes"] = index_project_facts(self.output_dir, project_id, phase_id)
        counts["version_changes"] = 0
        counts["version_diff"] = None

        json_file = STRUCTURED_JSON_MAP.get(phase_id)
        phase_root = self._phase_root(project_id, phase_id)
        if json_file and phase_root is not None:
            json_path = phase_root / json_file
            if json_path.exists():
                facts = extract_facts_from_json(json_path)
                if facts:
                    version_diff = track_version(self.output_dir, project_id, phase_id, facts)
                    counts["version_diff"] = version_diff
                    counts["version_changes"] = (
                        version_diff["added"] + version_diff["modified"] + version_diff["removed"]
                    )

        counts["summary_generated"] = 0
        if phase_root is not None:
            summary_path = generate_summary_file(phase_root)
            counts["summary_generated"] = 1 if summary_path else 0

        self._invalidate_project_fact_search_cache(project_id)
        self._save_index_state(
            project_id,
            phase_id,
            {
                "signature": current_signature,
                "facts": counts["facts"],
                "knowledge_nodes": counts["knowledge_nodes"],
                "version_changes": counts["version_changes"],
            },
        )
        return counts

    def build_links(self) -> int:
        """构建跨项目知识链接."""
        index_bug_cases(self.output_dir)
        return build_cross_project_links(self.output_dir)

    # ----- 跨项目经验 -----

    def get_insights(self, project_id: str, phase_id: str) -> list[dict[str, Any]]:
        return get_cross_project_insights(self.output_dir, project_id, phase_id)

    def format_insights(self, insights: list[dict[str, Any]]) -> str:
        return format_insights(insights)

    # ----- 版本历史 -----

    def get_history(self, project_id: str, fact_id: str) -> list[dict[str, Any]]:
        return get_fact_history(self.output_dir, project_id, fact_id)

    def get_changes(self, project_id: str, phase_id: str, since: str | None = None) -> list[dict[str, Any]]:
        return get_changes_since(self.output_dir, project_id, phase_id, since)

    # ----- 缓存管理 -----

    def cache_text(self, project_id: str, phase_id: str, text: str, doc_name: str = "") -> int:
        return cache_document(self.output_dir, project_id, phase_id, text, doc_name)

    def cache_images(self, project_id: str, phase_id: str, records: list[dict[str, Any]]) -> int:
        return save_image_batch(self.output_dir, project_id, phase_id, records)

    def is_text_cached(self, project_id: str, phase_id: str) -> bool:
        return is_cached(self.output_dir, project_id, phase_id)

    def sync_wiki_to_sqlite(self, project_id: str = "global") -> int:
        """双轨桥接：静默读取 .dqg-wiki 中的全部文本更新到 FTS5 缓冲。"""
        wiki_dir = Path(".dqg-wiki")
        if not wiki_dir.exists():
            return 0

        count = 0
        for md_file in wiki_dir.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            if content.strip():
                self.cache_text(
                    project_id,
                    f"wiki-{md_file.name}",
                    content,
                    doc_name=str(md_file.relative_to(wiki_dir)),
                )
                count += 1
        return count

    # ----- 代码搜索 -----

    def index_repo(self, repo_path: str | Path, max_files: int = 500) -> int:
        """索引代码仓库."""
        return index_java_repo(self.output_dir, repo_path, max_files)

    def search_code(
        self, query: str, repo_path: str | None = None, symbol_type: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """智能代码搜索（自动展开业务概念）."""
        return search_code(self.output_dir, query, repo_path, symbol_type, limit)

    def format_code_results(self, results: list[dict[str, Any]]) -> str:
        return format_search_results(results)

    def get_text_stats(self, project_id: str, phase_id: str) -> dict[str, Any]:
        return get_cache_stats(self.output_dir, project_id, phase_id)

    def get_cache_stats(self) -> dict[str, Any]:
        return cache_stats(self.output_dir)

    # ----- 统计 -----

    def stats(self) -> dict[str, Any]:
        """全局统计."""
        from dqg.store import get_connection

        stats: dict[str, Any] = {}
        with get_connection(self.output_dir) as conn:
            for table in (
                "structured_facts",
                "image_semantics",
                "text_segments",
                "knowledge_nodes",
                "knowledge_links",
                "requirement_versions",
                "query_cache",
            ):
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    stats[table] = count
                except Exception:
                    stats[table] = 0
        stats["cache"] = cache_stats(self.output_dir)
        return stats
