"""代码智能搜索：业务概念→代码关键词映射 + 结构索引 + 语义搜索.

三层架构：
1. 概念映射：搜"幂等"自动展开为 unique_no|idempotent|@Lock 等
2. 结构索引：类/方法/注解/字段存入 SQLite，支持调用链追踪
3. 语义搜索：基于 FTS5 的代码语义检索
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from qualix.json_utils import dump_json_str
from qualix.log import get_logger

log = get_logger(__name__)

from qualix.store import get_connection
from qualix.text_utils import build_fts_query, text_query_has_signal, tokenize_chinese

# ---------------------------------------------------------------------------
# 1. 业务概念 → 代码关键词映射
# ---------------------------------------------------------------------------

CONCEPT_MAP: Final = MappingProxyType(
    {
        "幂等": ["idempotent", "unique_no", "distribute_unique", "dedup", "幂等", "@Idempotent", "idempotentKey"],
        "并发": [
            "synchronized",
            "@Lock",
            "RedissonLock",
            "tryLock",
            "ConcurrentHashMap",
            "AtomicInteger",
            "ReentrantLock",
            "分布式锁",
            "concurrent",
        ],
        "事务": ["@Transactional", "TransactionTemplate", "rollback", "commit", "propagation", "REQUIRES_NEW", "事务"],
        "权限": [
            "@UserLogin",
            "permission",
            "authorize",
            "role",
            "权限",
            "checkPermission",
            "hasRole",
            "SecurityContext",
        ],
        "校验": [
            "validate",
            "check",
            "assert",
            "Preconditions",
            "校验",
            "@NotNull",
            "@NotBlank",
            "@Valid",
            "BusinessException",
        ],
        "缓存": ["@Cacheable", "RedisTemplate", "cache", "expire", "evict", "缓存", "CacheManager"],
        "异步": ["@Async", "CompletableFuture", "ThreadPool", "ExecutorService", "异步", "MQ", "RocketMQ", "Kafka"],
        "重试": ["@Retryable", "retry", "backoff", "maxAttempts", "重试", "RetryTemplate"],
        "降级": ["fallback", "degrade", "熔断", "降级", "CircuitBreaker", "Sentinel", "Hystrix"],
        "日志": ["log.info", "log.error", "log.warn", "@Slf4j", "Logger", "MDC", "traceId"],
        "定时任务": ["@Scheduled", "cron", "ScheduledTask", "Timer", "定时", "xxl-job"],
        "状态机": ["StateMachine", "status", "state", "transition", "状态机", "StatusEnum", "changeStatus"],
        "审批": ["approval", "bpm", "audit", "审批", "process", "workflow", "AuditStatus"],
        "脱敏": ["desensitize", "mask", "encrypt", "脱敏", "加密", "DataDesensitiz"],
        "分页": ["PageHelper", "PageInfo", "pageNum", "pageSize", "分页", "Pageable"],
        "导出": ["export", "Excel", "导出", "EasyExcel", "POI", "AsyncExport"],
        "通知": ["notify", "message", "push", "通知", "feishu", "飞书", "sms"],
        "金额": ["BigDecimal", "amount", "price", "金额", "ROUND_HALF_UP", "分", "元"],
        "DDD领域": ["DomainService", "Repository", "Aggregate", "ValueObject", "Entity", "Gateway"],
        "TMF链路": ["Step", "Ability", "Extension", "TMF", "decideSteps", "execute"],
    }
)


def expand_query(query: str) -> list[str]:
    """将业务概念展开为代码关键词列表."""
    keywords = [query]
    for concept, code_keywords in CONCEPT_MAP.items():
        if concept in query or query.lower() in [k.lower() for k in code_keywords]:
            keywords.extend(code_keywords)
    return list(set(keywords))


# ---------------------------------------------------------------------------
# 2. 代码结构索引
# ---------------------------------------------------------------------------


def index_java_repo(output_dir: Path, repo_path: str | Path, max_files: int = 500) -> int:
    """索引 Java 代码仓库的类/方法/字段/注解."""
    repo = Path(repo_path)
    if not repo.exists():
        return 0

    repo_str = str(repo.resolve())
    count = 0

    # 清除旧索引
    with get_connection(output_dir) as conn:
        conn.execute("DELETE FROM code_symbols WHERE repo_path = ?", (repo_str,))

    java_files = list(repo.rglob("*.java"))[:max_files]

    for java_file in java_files:
        try:
            content = java_file.read_text(encoding="utf-8", errors="ignore")
            symbols = _parse_java_file(content, str(java_file.relative_to(repo)))
            _save_symbols(output_dir, repo_str, symbols)
            count += len(symbols)
        except Exception:
            log.debug("Failed to parse %s, skipping", java_file, exc_info=True)
            continue

    return count


def _parse_java_file(content: str, file_path: str) -> list[dict[str, Any]]:
    """简易 Java 解析：提取类/方法/字段/注解."""
    symbols = []
    lines = content.split("\n")
    current_class = ""
    annotations_buffer: list[str] = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # 注解
        ann_match = re.match(r"^@(\w+)", stripped)
        if ann_match:
            annotations_buffer.append(ann_match.group(0))
            continue

        # 类/接口/枚举
        class_match = re.match(r"(?:public\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)", stripped)
        if class_match:
            current_class = class_match.group(1)
            symbols.append(
                {
                    "file_path": file_path,
                    "symbol_type": "class",
                    "symbol_name": current_class,
                    "parent_symbol": "",
                    "annotations": annotations_buffer.copy(),
                    "line_number": i,
                    "signature": stripped[:200],
                }
            )
            annotations_buffer.clear()
            continue

        # 方法
        method_match = re.match(
            r"(?:public|private|protected)?\s*(?:static\s+)?(?:[\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)",
            stripped,
        )
        if method_match and current_class and not stripped.startswith("//"):
            method_name = method_match.group(1)
            if method_name not in ("if", "for", "while", "switch", "catch", "return"):
                symbols.append(
                    {
                        "file_path": file_path,
                        "symbol_type": "method",
                        "symbol_name": method_name,
                        "parent_symbol": current_class,
                        "annotations": annotations_buffer.copy(),
                        "line_number": i,
                        "signature": stripped[:200],
                    }
                )
            annotations_buffer.clear()
            continue

        # 字段（枚举值或成员变量）
        field_match = re.match(
            r"(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(\w+)\s+(\w+)\s*[=;]",
            stripped,
        )
        if field_match and current_class:
            symbols.append(
                {
                    "file_path": file_path,
                    "symbol_type": "field",
                    "symbol_name": field_match.group(2),
                    "parent_symbol": current_class,
                    "annotations": annotations_buffer.copy(),
                    "line_number": i,
                    "signature": stripped[:200],
                }
            )
            annotations_buffer.clear()
            continue

        # 非注解行清空 buffer
        if stripped and not stripped.startswith("//") and not stripped.startswith("*"):
            annotations_buffer.clear()

    return symbols


def _save_symbols(output_dir: Path, repo_path: str, symbols: list[dict[str, Any]]) -> None:
    with get_connection(output_dir) as conn:
        for sym in symbols:
            ann_str = dump_json_str(sym.get("annotations", []), indent=None)
            conn.execute(
                """INSERT INTO code_symbols
                (repo_path, file_path, symbol_type, symbol_name, parent_symbol, annotations, line_number, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    repo_path,
                    sym["file_path"],
                    sym["symbol_type"],
                    sym["symbol_name"],
                    sym.get("parent_symbol", ""),
                    ann_str,
                    sym.get("line_number", 0),
                    sym.get("signature", ""),
                ),
            )
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            tokenized = tokenize_chinese(f"{sym['symbol_name']} {sym.get('signature', '')} {ann_str}")
            conn.execute(
                "INSERT INTO code_symbols_fts(rowid, symbol_name, signature, doc_comment, annotations) VALUES (?, ?, ?, ?, ?)",
                (row_id, tokenize_chinese(sym["symbol_name"]), tokenized, "", tokenize_chinese(ann_str)),
            )


# ---------------------------------------------------------------------------
# 3. 智能搜索
# ---------------------------------------------------------------------------


def search_code(
    output_dir: Path,
    query: str,
    repo_path: str | None = None,
    symbol_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """智能代码搜索：自动展开业务概念为代码关键词."""

    # 展开查询
    keywords = expand_query(query)

    all_results = []
    seen = set()

    for kw in keywords[:10]:  # 限制展开数量
        fts_query_and = build_fts_query(kw, mode="AND")
        fts_query_or = build_fts_query(kw, mode="OR")
        if not fts_query_and and not fts_query_or:
            continue

        for fts_query in (fts_query_and, fts_query_or):
            if not fts_query:
                continue
            conditions = []
            params: list[Any] = [fts_query]

            if repo_path:
                conditions.append("s.repo_path = ?")
                params.append(repo_path)
            if symbol_type:
                conditions.append("s.symbol_type = ?")
                params.append(symbol_type)

            where = f"AND {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            with get_connection(output_dir) as conn:
                rows = conn.execute(
                    f"""SELECT s.* FROM code_symbols s
                    JOIN code_symbols_fts f ON s.id = f.rowid
                    WHERE code_symbols_fts MATCH ? {where}
                    ORDER BY rank LIMIT ?""",
                    params,
                ).fetchall()

                for r in rows:
                    d = dict(r)
                    candidate = f"{d['symbol_name']} {d.get('signature', '')} {d.get('annotations', '')}"
                    if not text_query_has_signal(kw, candidate):
                        continue
                    key = (d["file_path"], d["line_number"])
                    if key not in seen:
                        seen.add(key)
                        d["matched_keyword"] = kw
                        all_results.append(d)

            if all_results:
                break

    # LIKE fallback
    if not all_results:
        for kw in keywords[:5]:
            with get_connection(output_dir) as conn:
                conditions = ["(symbol_name LIKE ? OR signature LIKE ? OR annotations LIKE ?)"]
                like = f"%{kw}%"
                params = [like, like, like]
                if repo_path:
                    conditions.append("repo_path = ?")
                    params.append(repo_path)
                if symbol_type:
                    conditions.append("symbol_type = ?")
                    params.append(symbol_type)
                params.append(limit)
                rows = conn.execute(
                    f"SELECT * FROM code_symbols WHERE {' AND '.join(conditions)} LIMIT ?",
                    params,
                ).fetchall()
                for r in rows:
                    key = (r["file_path"], r["line_number"])
                    if key not in seen:
                        seen.add(key)
                        d = dict(r)
                        d["matched_keyword"] = kw
                        all_results.append(d)

    return all_results[:limit]


def format_search_results(results: list[dict[str, Any]]) -> str:
    """格式化搜索结果."""
    if not results:
        return "  无匹配结果"

    lines = [f"  代码搜索: {len(results)} 个匹配"]
    for r in results[:15]:
        ann = r.get("annotations", "[]")
        if isinstance(ann, str):
            try:
                ann = json.loads(ann)
            except Exception:
                ann = []
        ann_str = " ".join(ann) if ann else ""
        lines.append(
            f"    [{r['symbol_type']}] {r.get('parent_symbol', '')}.{r['symbol_name']} "
            f"({r['file_path']}:{r['line_number']}) {ann_str}"
        )
    return "\n".join(lines)
