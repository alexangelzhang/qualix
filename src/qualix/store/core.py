"""SQLite 存储层核心：连接管理、schema 初始化、通用工具函数."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from qualix.constants import DB_FILENAME as _DB_FILENAME
from qualix.log import get_logger

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

log = get_logger(__name__)


def _ensure_image_semantics_tokenized_column(conn: sqlite3.Connection) -> None:
    """已有库补建 image_semantics.description_tokenized 列及关联触发器（幂等）.

    旧库升级路径：
    1. 加列
    2. 重建触发器（DROP + CREATE，使用新列）
    3. 回填 description_tokenized
    4. 重建 FTS 索引
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(image_semantics)")}
    if "description_tokenized" in cols:
        return

    conn.execute("ALTER TABLE image_semantics ADD COLUMN description_tokenized TEXT DEFAULT ''")

    conn.execute("DROP TRIGGER IF EXISTS img_sem_ai")
    conn.execute("DROP TRIGGER IF EXISTS img_sem_au")
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS img_sem_ai AFTER INSERT ON image_semantics BEGIN
            INSERT INTO image_semantics_fts(rowid, filename, description, related_reqs, mermaid_code, section_context)
            VALUES (new.id, new.filename, new.description_tokenized, new.related_reqs, new.mermaid_code, new.section_context);
        END;"""
    )
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS img_sem_au AFTER UPDATE ON image_semantics BEGIN
            INSERT INTO image_semantics_fts(image_semantics_fts, rowid, filename, description, related_reqs, mermaid_code, section_context)
            VALUES ('delete', old.id, old.filename, old.description_tokenized, old.related_reqs, old.mermaid_code, old.section_context);
            INSERT INTO image_semantics_fts(rowid, filename, description, related_reqs, mermaid_code, section_context)
            VALUES (new.id, new.filename, new.description_tokenized, new.related_reqs, new.mermaid_code, new.section_context);
        END;"""
    )

    try:
        from qualix.text_utils import tokenize_chinese

        rows = conn.execute(
            "SELECT id, filename, description, related_reqs, mermaid_code, section_context FROM image_semantics"
        ).fetchall()
        for row in rows:
            row_id, filename, desc, reqs, mermaid, section = row
            tokenized = tokenize_chinese(f"{filename} {desc} {reqs} {mermaid} {section}")
            conn.execute("UPDATE image_semantics SET description_tokenized=? WHERE id=?", (tokenized, row_id))
            conn.execute(
                "INSERT OR REPLACE INTO image_semantics_fts(rowid, filename, description, related_reqs, mermaid_code, section_context) VALUES (?, ?, ?, ?, ?, ?)",
                (row_id, filename, tokenized, reqs, mermaid, section),
            )
    except Exception:
        pass  # 回填失败不阻断启动，下次 save_image_semantic 写入正确值

    log.info("image_semantics: description_tokenized column added and backfilled")


def _ensure_feedback_trust_table(conn: sqlite3.Connection) -> None:
    """已有库补建 feedback_trust（CREATE IF NOT EXISTS 幂等）."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_trust (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            phase_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trust_level TEXT NOT NULL,
            payload TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_trust_project ON feedback_trust(project_id, phase_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fb_trust_created ON feedback_trust(created_at);")


def _ensure_prompt_versions_table(conn: sqlite3.Connection) -> None:
    """P2: 已有库补建 prompt_versions（CREATE IF NOT EXISTS 幂等）."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            version INTEGER NOT NULL,
            agent_name TEXT DEFAULT '',
            agent_role TEXT DEFAULT '',
            trace_run_id TEXT DEFAULT '',
            prompt_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(prompt_hash, content_hash)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_promptver_hash ON prompt_versions(prompt_hash, version DESC);")


# ---------------------------------------------------------------------------
# Harness 层 Schema：通用基础设施表（LLM cache、代码索引、知识图谱）
# 这些表不含 DQG 业务概念，可被任何 Domain App 复用
# ---------------------------------------------------------------------------

_HARNESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    query_text TEXT NOT NULL,
    result_type TEXT DEFAULT '',
    result_json TEXT DEFAULT '[]',
    hit_count INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    last_hit_at REAL
);
CREATE INDEX IF NOT EXISTS idx_qcache_hash ON query_cache(query_hash);

CREATE TABLE IF NOT EXISTS code_symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    symbol_type TEXT NOT NULL,
    symbol_name TEXT NOT NULL,
    parent_symbol TEXT DEFAULT '',
    annotations TEXT DEFAULT '[]',
    line_number INTEGER DEFAULT 0,
    signature TEXT DEFAULT '',
    doc_comment TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_codesym_repo ON code_symbols(repo_path);
CREATE INDEX IF NOT EXISTS idx_codesym_type ON code_symbols(symbol_type);
CREATE INDEX IF NOT EXISTS idx_codesym_name ON code_symbols(symbol_name);
CREATE VIRTUAL TABLE IF NOT EXISTS code_symbols_fts USING fts5(
    symbol_name, signature, doc_comment, annotations,
    content='code_symbols', content_rowid='id'
);

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT UNIQUE NOT NULL,
    node_type TEXT NOT NULL,
    project_id TEXT DEFAULT '',
    phase_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_knode_type ON knowledge_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_knode_project ON knowledge_nodes(project_id);

CREATE TABLE IF NOT EXISTS knowledge_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    strength REAL DEFAULT 1.0,
    reason TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(source_id, target_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_klink_source ON knowledge_links(source_id);
CREATE INDEX IF NOT EXISTS idx_klink_target ON knowledge_links(target_id);

CREATE TABLE IF NOT EXISTS knowledge_hyperedges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hyperedge_id TEXT UNIQUE NOT NULL,
    edge_type TEXT NOT NULL,
    label TEXT DEFAULT '',
    description TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    strength REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hyper_type ON knowledge_hyperedges(edge_type);
CREATE INDEX IF NOT EXISTS idx_hyper_project ON knowledge_hyperedges(project_id);

CREATE TABLE IF NOT EXISTS knowledge_hyperedge_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hyperedge_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    role TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(hyperedge_id, node_id),
    FOREIGN KEY (hyperedge_id) REFERENCES knowledge_hyperedges(hyperedge_id)
);
CREATE INDEX IF NOT EXISTS idx_hypermember_edge ON knowledge_hyperedge_members(hyperedge_id);
CREATE INDEX IF NOT EXISTS idx_hypermember_node ON knowledge_hyperedge_members(node_id);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    metric_data TEXT DEFAULT '{}',
    period TEXT DEFAULT 'daily',
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_metrics_project ON metrics(project_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);
"""

# ---------------------------------------------------------------------------
# Domain 层 Schema：DQG 质量门禁业务表
# 这些表包含 Phase、Judge、Bug Case 等 DQG 特有概念
# ---------------------------------------------------------------------------

_DOMAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    phase_name TEXT DEFAULT '',
    action TEXT DEFAULT '',
    status TEXT DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    duration_seconds REAL,
    validation_errors TEXT DEFAULT '[]',
    comment TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    os_type TEXT DEFAULT '',
    python_version TEXT DEFAULT '',
    llm_calls TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_telemetry_project ON telemetry(project_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_phase ON telemetry(project_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    action TEXT DEFAULT '',
    message TEXT DEFAULT '',
    data_json TEXT DEFAULT '{}',
    duration_ms INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_phase ON events(project_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    preferred TEXT DEFAULT '',
    confidence TEXT DEFAULT '',
    dimensions TEXT DEFAULT '{}',
    critique_effectiveness TEXT DEFAULT '[]',
    summary TEXT DEFAULT '',
    timestamp TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pref_project ON preferences(project_id);

CREATE TABLE IF NOT EXISTS bug_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT UNIQUE NOT NULL,
    phase TEXT NOT NULL,
    error_type TEXT NOT NULL,
    severity TEXT DEFAULT 'medium',
    title TEXT DEFAULT '',
    root_cause TEXT DEFAULT '',
    fix_target TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    status TEXT DEFAULT 'open',
    source TEXT DEFAULT '{}',
    expected TEXT DEFAULT '{}',
    actual TEXT DEFAULT '{}',
    lesson TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_bug_phase ON bug_cases(phase);
CREATE INDEX IF NOT EXISTS idx_bug_status ON bug_cases(status);

CREATE TABLE IF NOT EXISTS judge_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    overall_score REAL,
    precision_estimate REAL,
    recall_estimate REAL,
    dimensions TEXT DEFAULT '[]',
    gate_checklist TEXT DEFAULT '[]',
    top_issues TEXT DEFAULT '[]',
    summary TEXT DEFAULT '',
    judged_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_judge_project ON judge_results(project_id, phase_id);

CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT UNIQUE NOT NULL,
    skill_file TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    cycle INTEGER NOT NULL,
    benchmark_case TEXT DEFAULT '',
    prompt_diff TEXT DEFAULT '',
    prompt_hash TEXT DEFAULT '',
    judge_score REAL,
    judge_dimensions TEXT DEFAULT '{}',
    baseline_score REAL,
    delta REAL,
    accepted INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    duration_seconds REAL,
    token_count INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_exp_skill ON experiments(skill_file);
CREATE INDEX IF NOT EXISTS idx_exp_phase ON experiments(phase_id);
CREATE INDEX IF NOT EXISTS idx_exp_accepted ON experiments(accepted);

CREATE TABLE IF NOT EXISTS image_semantics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    kind TEXT DEFAULT 'image',
    description TEXT DEFAULT '',
    description_tokenized TEXT DEFAULT '',
    related_reqs TEXT DEFAULT '[]',
    mermaid_code TEXT DEFAULT '',
    section_context TEXT DEFAULT '',
    token_estimate INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, phase_id, filename)
);
CREATE INDEX IF NOT EXISTS idx_img_project ON image_semantics(project_id, phase_id);
CREATE VIRTUAL TABLE IF NOT EXISTS image_semantics_fts USING fts5(
    filename, description, related_reqs, mermaid_code, section_context,
    content='image_semantics', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS img_sem_ai AFTER INSERT ON image_semantics BEGIN
    INSERT INTO image_semantics_fts(rowid, filename, description, related_reqs, mermaid_code, section_context)
    VALUES (new.id, new.filename, new.description_tokenized, new.related_reqs, new.mermaid_code, new.section_context);
END;

CREATE TRIGGER IF NOT EXISTS img_sem_au AFTER UPDATE ON image_semantics BEGIN
    INSERT INTO image_semantics_fts(image_semantics_fts, rowid, filename, description, related_reqs, mermaid_code, section_context)
    VALUES ('delete', old.id, old.filename, old.description_tokenized, old.related_reqs, old.mermaid_code, old.section_context);
    INSERT INTO image_semantics_fts(rowid, filename, description, related_reqs, mermaid_code, section_context)
    VALUES (new.id, new.filename, new.description_tokenized, new.related_reqs, new.mermaid_code, new.section_context);
END;

CREATE TRIGGER IF NOT EXISTS img_sem_ad AFTER DELETE ON image_semantics BEGIN
    INSERT INTO image_semantics_fts(image_semantics_fts, rowid, filename, description, related_reqs, mermaid_code, section_context)
    VALUES ('delete', old.id, old.filename, old.description_tokenized, old.related_reqs, old.mermaid_code, old.section_context);
END;

CREATE TABLE IF NOT EXISTS text_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    doc_name TEXT DEFAULT '',
    section_path TEXT DEFAULT '',
    heading TEXT DEFAULT '',
    content TEXT DEFAULT '',
    content_tokenized TEXT DEFAULT '',
    line_start INTEGER DEFAULT 0,
    line_end INTEGER DEFAULT 0,
    char_count INTEGER DEFAULT 0,
    keywords TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, phase_id, doc_name, line_start)
);
CREATE INDEX IF NOT EXISTS idx_textseg_project ON text_segments(project_id, phase_id);
CREATE VIRTUAL TABLE IF NOT EXISTS text_segments_fts USING fts5(
    heading, content_tokenized, keywords,
    content='text_segments', content_rowid='id'
);

CREATE TABLE IF NOT EXISTS structured_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    description TEXT DEFAULT '',
    related_ids TEXT DEFAULT '[]',
    extra TEXT DEFAULT '{}',
    confidence TEXT DEFAULT 'EXTRACTED',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, phase_id, fact_id)
);
CREATE INDEX IF NOT EXISTS idx_fact_project ON structured_facts(project_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_fact_type ON structured_facts(fact_type);
CREATE VIRTUAL TABLE IF NOT EXISTS structured_facts_fts USING fts5(
    fact_id, description, related_ids,
    content='structured_facts', content_rowid='id'
);

CREATE TABLE IF NOT EXISTS observe_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    severity TEXT NOT NULL,
    rule TEXT NOT NULL,
    project_id TEXT NOT NULL,
    phase TEXT DEFAULT '',
    message TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_obs_alert_label ON observe_alerts(label);
CREATE INDEX IF NOT EXISTS idx_obs_alert_project ON observe_alerts(project_id);
CREATE INDEX IF NOT EXISTS idx_obs_alert_severity ON observe_alerts(severity);

CREATE TABLE IF NOT EXISTS requirement_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT DEFAULT 'active',
    prev_description TEXT DEFAULT '',
    change_type TEXT DEFAULT 'added',
    change_reason TEXT DEFAULT '',
    valid_from TEXT NOT NULL,
    valid_until TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reqver_project ON requirement_versions(project_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_reqver_fact ON requirement_versions(fact_id);
CREATE INDEX IF NOT EXISTS idx_reqver_status ON requirement_versions(status);

CREATE TABLE IF NOT EXISTS feedback_trust (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fb_trust_project ON feedback_trust(project_id, phase_id);
CREATE INDEX IF NOT EXISTS idx_fb_trust_created ON feedback_trust(created_at);
"""

# 合并后的完整 schema（向后兼容）
_SCHEMA = _HARNESS_SCHEMA + _DOMAIN_SCHEMA

# Schema 初始化缓存：每个数据库文件只执行一次
_initialized_dbs: set[str] = set()

# 线程本地连接池：同一线程内复用连接，避免重复 connect/close
_thread_local = threading.local()


def _db_path(output_dir: Path) -> Path:
    return output_dir / _DB_FILENAME


def _get_cached_connection(db_str: str) -> sqlite3.Connection:
    """获取线程本地缓存的连接，不存在则创建."""
    cache: dict[str, sqlite3.Connection] = getattr(_thread_local, "connections", None) or {}
    if not hasattr(_thread_local, "connections"):
        _thread_local.connections = cache

    conn = cache.get(db_str)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            # 连接已关闭，移除缓存
            cache.pop(db_str, None)

    conn = sqlite3.connect(db_str, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    if db_str not in _initialized_dbs:
        conn.executescript(_SCHEMA)
        # Migrate: add llm_calls column to telemetry if missing (for existing DBs)
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(telemetry)").fetchall()}
            if "llm_calls" not in cols:
                conn.execute("ALTER TABLE telemetry ADD COLUMN llm_calls TEXT DEFAULT '[]'")
        except Exception:
            log.debug("Schema migration check failed for %s", db_str, exc_info=True)
        _initialized_dbs.add(db_str)
        log.debug("Schema initialized: %s", db_str)
    try:
        _ensure_feedback_trust_table(conn)
    except Exception:
        log.debug("feedback_trust table ensure failed", exc_info=True)
    try:
        _ensure_prompt_versions_table(conn)
    except Exception:
        log.debug("prompt_versions table ensure failed", exc_info=True)
    try:
        _ensure_image_semantics_tokenized_column(conn)
    except Exception:
        log.debug("image_semantics tokenized column ensure failed", exc_info=True)
    cache[db_str] = conn
    return conn


@contextmanager
def get_connection(output_dir: Path) -> Generator[sqlite3.Connection, None, None]:
    """获取数据库连接（线程本地复用，schema 只在首次执行）."""
    db = _db_path(output_dir)
    db.parent.mkdir(parents=True, exist_ok=True)
    db_str = str(db)
    conn = _get_cached_connection(db_str)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """将 sqlite3.Row 转为 dict，自动解析 JSON 字段."""
    d = dict(row)
    for key in (
        "validation_errors",
        "dimensions",
        "critique_effectiveness",
        "tags",
        "source",
        "expected",
        "actual",
        "metric_data",
        "gate_checklist",
        "top_issues",
        "llm_calls",
    ):
        if key in d and isinstance(d[key], str):
            with suppress(json.JSONDecodeError, TypeError):
                d[key] = json.loads(d[key])
    return d
