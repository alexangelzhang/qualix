"""语义缓存：相同/相似查询直接返回缓存结果，零 token 消耗.

基于查询文本 hash 缓存，同一 session 内重复查询直接命中。
支持 TTL 过期（默认 1 小时）。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

from dqg.json_utils import dump_json_compact, dump_json_str
from dqg.store import get_connection

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_TTL = 3600  # 1 小时
_CACHE_KEY_VERSION = "v2"


def _normalize_cache_version(cache_version: str | None) -> str:
    return cache_version or _CACHE_KEY_VERSION


def _build_query_text(
    query: str,
    result_type: str = "",
    project_id: str = "",
    cache_version: str | None = None,
) -> str:
    payload = {
        "cache_version": _normalize_cache_version(cache_version),
        "project_id": project_id,
        "query": query,
        "result_type": result_type,
    }
    return dump_json_compact(payload)


def _hash_query(
    query: str,
    result_type: str = "",
    project_id: str = "",
    cache_version: str | None = None,
) -> str:
    key = _build_query_text(query, result_type, project_id, cache_version)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def cache_get(
    output_dir: Path,
    query: str,
    result_type: str = "",
    project_id: str = "",
    ttl: int = _DEFAULT_TTL,
    cache_version: str | None = None,
) -> list[dict[str, Any]] | None:
    """查询缓存. 命中返回结果，未命中返回 None."""
    qhash = _hash_query(query, result_type, project_id, cache_version)
    now = time.time()

    with get_connection(output_dir) as conn:
        row = conn.execute(
            "SELECT result_json, created_at FROM query_cache WHERE query_hash = ?",
            (qhash,),
        ).fetchone()

        if not row:
            return None

        if now - row["created_at"] > ttl:
            conn.execute("DELETE FROM query_cache WHERE query_hash = ?", (qhash,))
            return None

        conn.execute(
            "UPDATE query_cache SET hit_count = hit_count + 1, last_hit_at = ? WHERE query_hash = ?",
            (now, qhash),
        )

        try:
            return json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            return None


def cache_put(
    output_dir: Path,
    query: str,
    results: list[dict[str, Any]],
    result_type: str = "",
    project_id: str = "",
    cache_version: str | None = None,
) -> None:
    """存入缓存."""
    qhash = _hash_query(query, result_type, project_id, cache_version)
    query_text = _build_query_text(query, result_type, project_id, cache_version)
    now = time.time()

    with get_connection(output_dir) as conn:
        conn.execute(
            """INSERT INTO query_cache (query_hash, query_text, result_type, result_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(query_hash) DO UPDATE SET
                query_text=excluded.query_text,
                result_json=excluded.result_json,
                created_at=excluded.created_at,
                hit_count=0,
                last_hit_at=NULL""",
            (qhash, query_text, result_type, dump_json_str(results, indent=None), now),
        )


def cache_invalidate(
    output_dir: Path,
    project_id: str = "",
    result_type: str = "",
    cache_version: str | None = None,
) -> int:
    """清除缓存（项目级或全部，可按类型/版本过滤）."""
    conditions: list[str] = []
    params: list[Any] = []

    if result_type:
        conditions.append("result_type = ?")
        params.append(result_type)
    if project_id:
        conditions.append("query_text LIKE ?")
        params.append(f'%"project_id":"{project_id}"%')
    if cache_version:
        version = _normalize_cache_version(cache_version)
        conditions.append("query_text LIKE ?")
        params.append(f'%"cache_version":"{version}"%')

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_connection(output_dir) as conn:
        deleted = conn.execute(f"DELETE FROM query_cache{where}", params).rowcount
    return deleted


def cache_stats(output_dir: Path) -> dict[str, Any]:
    """缓存统计，包含命中率可观测指标."""
    with get_connection(output_dir) as conn:
        total = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
        total_hits = conn.execute("SELECT SUM(hit_count) FROM query_cache").fetchone()[0] or 0
        # 有命中记录的条目数（hit_count > 0）
        hit_entries = conn.execute(
            "SELECT COUNT(*) FROM query_cache WHERE hit_count > 0"
        ).fetchone()[0]
        # 最近 24h 新增条目（miss = 首次查询）
        recent_misses = conn.execute(
            "SELECT COUNT(*) FROM query_cache WHERE created_at > ?",
            (time.time() - 86400,),
        ).fetchone()[0]
        # 最近 24h 命中次数
        recent_hits = conn.execute(
            "SELECT SUM(hit_count) FROM query_cache WHERE last_hit_at > ?",
            (time.time() - 86400,),
        ).fetchone()[0] or 0

    total_queries = total_hits + total  # hits + unique misses (each entry = 1 miss)
    hit_rate = total_hits / total_queries if total_queries > 0 else 0.0
    recent_total = recent_hits + recent_misses
    recent_hit_rate = recent_hits / recent_total if recent_total > 0 else 0.0

    return {
        "total_entries": total,
        "total_hits": total_hits,
        "hit_entries": hit_entries,
        "hit_rate": round(hit_rate, 3),
        "recent_misses_24h": recent_misses,
        "recent_hits_24h": recent_hits,
        "recent_hit_rate_24h": round(recent_hit_rate, 3),
    }


def cached_search(
    output_dir: Path,
    query: str,
    search_fn,
    result_type: str = "",
    project_id: str = "",
    ttl: int = _DEFAULT_TTL,
    cache_version: str | None = None,
    **search_kwargs,
) -> tuple[list[dict[str, Any]], bool]:
    """带缓存的搜索. 返回 (结果, 是否命中缓存)."""
    cached = cache_get(output_dir, query, result_type, project_id, ttl, cache_version)
    if cached is not None:
        return cached, True

    results = search_fn(output_dir, query, **search_kwargs)
    if results:
        cache_put(output_dir, query, results, result_type, project_id, cache_version)
    return results, False
