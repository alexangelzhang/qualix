"""LLM Result Cache: Judge/Critique 结果缓存，避免相同上下文重复调用 LLM.

缓存键 = hash(phase_id + 产物文件签名 + prompt 类型)
产物文件签名 = hash(文件路径 + mtime + size) 的组合
产物变更时缓存自动失效（签名不匹配）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)

_CACHE_DIR = "_internal"
_CACHE_FILE = "_llm_result_cache.json"


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
    """构建 Phase 产物的上下文 hash.

    基于报告文件 + 结构化 JSON 的文件签名，产物任何变更都会导致 hash 变化。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    signatures: list[str] = []

    # 报告文件签名
    report_file = REPORT_MAP.get(phase_id)
    if report_file:
        signatures.append(_file_signature(pd / report_file))

    # 结构化 JSON 签名
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        signatures.append(_file_signature(pd / json_file))

    # 推理日志签名
    reasoning_log = pd / "_reasoning_log.md"
    if reasoning_log.exists():
        signatures.append(_file_signature(reasoning_log))

    if not signatures or all(s == "missing" for s in signatures):
        return None

    combined = "|".join([phase_id, project_id] + signatures)
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
        log.debug("LLM result cache MISS: %s/%s/%s", project_id, phase_id, result_type)
        return None

    # 验证 context_hash 仍然匹配（双重校验）
    if entry.get("context_hash") != ctx_hash:
        log.debug("LLM result cache STALE: hash mismatch for %s/%s/%s", project_id, phase_id, result_type)
        return None

    log.info(
        "LLM result cache HIT: %s/%s/%s (cached at %s)",
        project_id, phase_id, result_type, entry.get("cached_at", "?"),
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
        "cached_at": __import__("datetime").datetime.now().isoformat(),
    }

    # 清理旧的同类型缓存（只保留最新的）
    stale_keys = [
        k for k in cache
        if k.startswith(f"{result_type}:") and k != key
    ]
    for sk in stale_keys:
        del cache[sk]

    save_json(cache_file, cache)
    log.info("LLM result cache PUT: %s/%s/%s (hash=%s)", project_id, phase_id, result_type, ctx_hash)


def invalidate_cache(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    result_type: str | None = None,
) -> int:
    """清除缓存.

    Args:
        result_type: 指定类型清除，None 清除该 Phase 全部缓存
    """
    cache_file = _cache_path(output_dir, project_id, phase_id)
    cache = _load_cache(cache_file)
    if not cache:
        return 0

    if result_type:
        stale_keys = [k for k in cache if k.startswith(f"{result_type}:")]
    else:
        stale_keys = list(cache.keys())

    for k in stale_keys:
        del cache[k]

    if cache:
        save_json(cache_file, cache)
    elif cache_file.exists():
        cache_file.unlink()

    count = len(stale_keys)
    if count:
        log.info("LLM result cache INVALIDATED: %s/%s, removed %d entries", project_id, phase_id, count)
    return count
