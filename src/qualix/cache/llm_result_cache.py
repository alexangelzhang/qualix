"""LLM Result Cache: Judge/Critique/Preference 结果缓存，避免相同上下文重复调用 LLM.

缓存键 = hash(phase_id + 产物文件签名 + skill文件签名 + prompt 类型)
产物文件签名 = hash(文件路径 + mtime + size) 的组合
产物或 skill/rubric 变更时缓存自动失效。
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.constants import REPORT_MAP, SKILL_FILE_MAP, STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json
from qualix.log import get_logger

log = get_logger(__name__)

_CACHE_DIR = "_internal"
_CACHE_FILE = "_llm_result_cache.json"
_STATS_KEY = "__stats__"

# In-memory stats accumulator — flushed to disk only on put/invalidate
_inmemory_stats: dict[str, dict[str, Any]] = {}


def _get_stats(cache_file: Path) -> dict[str, Any]:
    """Get or create in-memory stats for a cache file."""
    key = str(cache_file)
    if key not in _inmemory_stats:
        # Load from disk on first access
        cache = _load_cache(cache_file)
        _inmemory_stats[key] = cache.get(
            _STATS_KEY,
            {
                "total_hits": 0,
                "total_misses": 0,
                "total_puts": 0,
                "saved_calls": {},
                "last_updated": "",
            },
        )
    return _inmemory_stats[key]


def _file_signature(path: Path) -> str:
    """文件签名: path + mtime + size，任一变化则签名不同."""
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}"


def _build_context_hash(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """构建 Phase 产物 + prompt 模板的上下文 hash.

    包含：报告文件 + 结构化 JSON + 推理日志 + skill 文件 + judge rubric 模块。
    任一变更都会导致 hash 变化，缓存自动失效。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    signatures: list[str] = []

    # 产物文件签名
    report_file = REPORT_MAP.get(phase_id)
    if report_file:
        signatures.append(_file_signature(pd / report_file))

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        signatures.append(_file_signature(pd / json_file))

    reasoning_log = pd / "_reasoning_log.md"
    if reasoning_log.exists():
        signatures.append(_file_signature(reasoning_log))

    # skill 文件签名（skill 变更 → prompt 变更 → 缓存失效）
    skill_file = SKILL_FILE_MAP.get(phase_id)
    if skill_file:
        project_root = output_dir.parent
        skill_path = project_root / skill_file
        if skill_path.exists():
            signatures.append("skill:" + _file_signature(skill_path))

    # judge rubric 模块签名（rubric 定义变更 → 缓存失效）
    # Use importlib to locate the module file without importing it (avoids circular import).
    _spec = importlib.util.find_spec("qualix.quality.judge.judge")
    judge_module = Path(_spec.origin) if _spec and _spec.origin else None
    if judge_module and judge_module.exists():
        signatures.append("rubric:" + _file_signature(judge_module))

    if not signatures or all(s == "missing" for s in signatures):
        return None

    combined = "|".join([phase_id, project_id, *signatures])
    return hashlib.sha256(combined.encode()).hexdigest()[:20]


def _cache_path(output_dir: Path, project_id: str, phase_id: str) -> Path:
    """缓存文件路径."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return output_dir / project_id / _CACHE_DIR / _CACHE_FILE
    pd = _phase_dir(output_dir, project_id, phase_def)
    return pd / _CACHE_DIR / _CACHE_FILE


def _load_cache(cache_file: Path) -> dict[str, Any]:
    """加载缓存文件."""
    data = load_json(cache_file)
    return data if isinstance(data, dict) else {}


def _update_stats(cache_file: Path, event: str, result_type: str) -> None:
    """更新内存中的缓存统计（不写磁盘）."""
    stats = _get_stats(cache_file)
    if event == "hit":
        stats["total_hits"] += 1
        stats["saved_calls"][result_type] = stats["saved_calls"].get(result_type, 0) + 1
    elif event == "miss":
        stats["total_misses"] += 1
    elif event == "put":
        stats["total_puts"] += 1
    stats["last_updated"] = datetime.now().isoformat()


def _flush_stats(cache: dict[str, Any], cache_file: Path) -> None:
    """将内存统计合并到 cache dict 中（调用方负责写磁盘）."""
    key = str(cache_file)
    if key in _inmemory_stats:
        cache[_STATS_KEY] = _inmemory_stats[key]


def get_cached_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    result_type: str,
) -> dict[str, Any] | None:
    """查询 LLM 结果缓存.

    Args:
        result_type: "judge" | "critique" | "preference"

    Returns:
        缓存的结果 dict，未命中返回 None
    """
    ctx_hash = _build_context_hash(output_dir, project_id, phase_id)
    if not ctx_hash:
        return None

    cache_file = _cache_path(output_dir, project_id, phase_id)
    cache = _load_cache(cache_file)

    key = f"{result_type}:{ctx_hash}"
    entry = cache.get(key)
    if not entry:
        _update_stats(cache_file, "miss", result_type)
        log.debug("LLM result cache MISS: %s/%s/%s", project_id, phase_id, result_type)
        return None

    if entry.get("context_hash") != ctx_hash:
        _update_stats(cache_file, "miss", result_type)
        log.debug("LLM result cache STALE: hash mismatch for %s/%s/%s", project_id, phase_id, result_type)
        return None

    _update_stats(cache_file, "hit", result_type)
    log.info(
        "LLM result cache HIT: %s/%s/%s (cached at %s)",
        project_id,
        phase_id,
        result_type,
        entry.get("cached_at", "?"),
    )
    return entry.get("result")


def put_cached_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    result_type: str,
    result: dict[str, Any],
) -> None:
    """存入 LLM 结果缓存."""
    ctx_hash = _build_context_hash(output_dir, project_id, phase_id)
    if not ctx_hash:
        return

    cache_file = _cache_path(output_dir, project_id, phase_id)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(cache_file)

    key = f"{result_type}:{ctx_hash}"
    cache[key] = {
        "context_hash": ctx_hash,
        "result_type": result_type,
        "result": result,
        "cached_at": datetime.now().isoformat(),
    }

    # 清理旧的同类型缓存（只保留最新的）
    stale_keys = [k for k in cache if k.startswith(f"{result_type}:") and k != key and k != _STATS_KEY]
    for sk in stale_keys:
        del cache[sk]

    _update_stats(cache_file, "put", result_type)
    _flush_stats(cache, cache_file)
    save_json(cache_file, cache)
    log.info("LLM result cache PUT: %s/%s/%s (hash=%s)", project_id, phase_id, result_type, ctx_hash)


def cache_stats(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """获取缓存统计：命中率、节省的 LLM 调用次数."""
    cache_file = _cache_path(output_dir, project_id, phase_id)
    stats = _get_stats(cache_file)
    hits = stats.get("total_hits", 0)
    misses = stats.get("total_misses", 0)
    total = hits + misses
    return {
        "total_hits": hits,
        "total_misses": misses,
        "total_puts": stats.get("total_puts", 0),
        "hit_rate": f"{hits / total:.0%}" if total > 0 else "N/A",
        "saved_calls": stats.get("saved_calls", {}),
        "last_updated": stats.get("last_updated", ""),
    }


def global_cache_stats(output_dir: Path, project_id: str) -> dict[str, Any]:
    """汇总项目下所有 Phase 的缓存统计."""
    total_hits = 0
    total_misses = 0
    total_puts = 0
    saved_calls: dict[str, int] = {}
    phase_stats: dict[str, dict[str, Any]] = {}

    for phase_id in PHASE_DEFS:
        ps = cache_stats(output_dir, project_id, phase_id)
        if ps["total_hits"] or ps["total_misses"] or ps["total_puts"]:
            phase_stats[phase_id] = ps
            total_hits += ps["total_hits"]
            total_misses += ps["total_misses"]
            total_puts += ps["total_puts"]
            for rt, count in ps.get("saved_calls", {}).items():
                saved_calls[rt] = saved_calls.get(rt, 0) + count

    total = total_hits + total_misses
    return {
        "total_hits": total_hits,
        "total_misses": total_misses,
        "total_puts": total_puts,
        "hit_rate": f"{total_hits / total:.0%}" if total > 0 else "N/A",
        "saved_calls": saved_calls,
        "phase_stats": phase_stats,
    }
