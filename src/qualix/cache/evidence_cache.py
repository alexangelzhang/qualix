"""Structure-aware Evidence Pack cache.

Caches rendered Evidence Pack text keyed by structural hash of input files.
Hash = sha256(phase_id + sorted file signatures). File signature = path:mtime_ns:size.
Any file change (content, addition, removal) produces a different hash → auto-invalidation.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

from qualix.json_utils import dump_json_str
from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


def _file_signature(path: Path) -> str:
    """File signature: path + mtime_ns + size. Any change → different sig."""
    if not path.exists():
        return f"{path.name}:missing"
    stat = path.stat()
    return f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}"


class EvidencePackCache:
    """In-memory + SQLite cache for rendered Evidence Pack text."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._hits = 0
        self._misses = 0
        self._tokens_saved = 0

    def _structural_hash(self, phase_id: str, file_paths: list[Path]) -> str:
        """Compute structural hash from phase_id + sorted file signatures."""
        sigs = sorted(_file_signature(f) for f in file_paths)
        combined = f"{phase_id}|{'|'.join(sigs)}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:20]

    def get(self, phase_id: str, file_paths: list[Path]) -> dict[str, Any] | None:
        """Lookup cached Evidence Pack. Returns None on miss."""
        if not file_paths and not self._has_empty_entry(phase_id):
            self._misses += 1
            return None

        struct_hash = self._structural_hash(phase_id, file_paths)

        from qualix.store import get_connection

        with get_connection(self.output_dir) as conn:
            row = conn.execute(
                "SELECT result_json FROM query_cache WHERE query_hash = ? AND result_type = ?",
                (struct_hash, "evidence_pack"),
            ).fetchone()

        if not row:
            self._misses += 1
            log.debug("Evidence cache MISS: %s (hash=%s)", phase_id, struct_hash)
            return None

        try:
            data = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            self._misses += 1
            return None

        # Verify structural hash still matches (double-check against stored hash)
        if data.get("structural_hash") != struct_hash:
            self._misses += 1
            return None

        self._hits += 1
        self._tokens_saved += data.get("token_count", 0)
        log.info("Evidence cache HIT: %s (hash=%s)", phase_id, struct_hash)
        return data

    def _has_empty_entry(self, phase_id: str) -> bool:
        """Check if there's a cached entry for empty file list."""
        struct_hash = self._structural_hash(phase_id, [])
        from qualix.store import get_connection

        with get_connection(self.output_dir) as conn:
            row = conn.execute(
                "SELECT 1 FROM query_cache WHERE query_hash = ? AND result_type = ?",
                (struct_hash, "evidence_pack"),
            ).fetchone()
        return row is not None

    def put(
        self,
        phase_id: str,
        file_paths: list[Path],
        rendered: str,
        token_count: int = 0,
    ) -> None:
        """Store rendered Evidence Pack in cache."""
        struct_hash = self._structural_hash(phase_id, file_paths)

        from qualix.store import get_connection

        payload = {
            "structural_hash": struct_hash,
            "phase_id": phase_id,
            "rendered": rendered,
            "token_count": token_count,
            "file_count": len(file_paths),
            "file_sigs": [_file_signature(f) for f in file_paths],
        }

        with get_connection(self.output_dir) as conn:
            conn.execute(
                """INSERT INTO query_cache (query_hash, query_text, result_type, result_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(query_hash) DO UPDATE SET
                    result_json=excluded.result_json,
                    created_at=excluded.created_at,
                    hit_count=0,
                    last_hit_at=NULL""",
                (
                    struct_hash,
                    f"evidence_pack:{phase_id}",
                    "evidence_pack",
                    dump_json_str(payload, indent=None),
                    time.time(),
                ),
            )
        log.info(
            "Evidence cache PUT: %s (hash=%s, %d files, %d tokens)", phase_id, struct_hash, len(file_paths), token_count
        )

    def stats(self) -> dict[str, Any]:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "estimated_tokens_saved": self._tokens_saved,
        }
