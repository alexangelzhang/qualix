"""Test structure-aware Evidence Pack cache."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_cache_miss_then_hit(tmp_path: Path):
    """First call should miss, second with same files should hit."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)

    # Create fake upstream files
    f1 = tmp_path / "upstream_q01.json"
    f1.write_text('{"reqs": ["REQ-001"]}', encoding="utf-8")
    f2 = tmp_path / "upstream_q02.md"
    f2.write_text("# Phase Q02 Report\nContent here", encoding="utf-8")

    file_paths = [f1, f2]

    # Miss
    result = cache.get("Q07", file_paths)
    assert result is None

    # Store
    rendered = "## Evidence Pack\n\nRendered content here"
    cache.put("Q07", file_paths, rendered, token_count=500)

    # Hit
    result = cache.get("Q07", file_paths)
    assert result is not None
    assert result["rendered"] == rendered
    assert result["token_count"] == 500


def test_cache_invalidates_on_file_change(tmp_path: Path):
    """Modifying a source file should invalidate the cache."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)

    f1 = tmp_path / "upstream.json"
    f1.write_text('{"v": 1}', encoding="utf-8")

    cache.put("Q07", [f1], "rendered-v1", token_count=100)
    assert cache.get("Q07", [f1]) is not None

    # Modify file — need to ensure mtime changes
    time.sleep(0.05)
    f1.write_text('{"v": 2}', encoding="utf-8")

    # Should miss now
    assert cache.get("Q07", [f1]) is None


def test_cache_invalidates_on_file_added(tmp_path: Path):
    """Adding a new file to the input set should invalidate."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)

    f1 = tmp_path / "a.md"
    f1.write_text("content-a", encoding="utf-8")

    cache.put("Q07", [f1], "rendered-1file", token_count=50)
    assert cache.get("Q07", [f1]) is not None

    f2 = tmp_path / "b.md"
    f2.write_text("content-b", encoding="utf-8")

    # Different file set — should miss
    assert cache.get("Q07", [f1, f2]) is None


def test_cache_stats(tmp_path: Path):
    """Stats should track hits and misses."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)
    f1 = tmp_path / "x.md"
    f1.write_text("x", encoding="utf-8")

    cache.get("Q07", [f1])  # miss
    cache.put("Q07", [f1], "rendered", token_count=10)
    cache.get("Q07", [f1])  # hit
    cache.get("Q07", [f1])  # hit

    stats = cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] > 0.5


def test_empty_file_list(tmp_path: Path):
    """Empty file list should not crash."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)
    assert cache.get("Q07", []) is None
    cache.put("Q07", [], "empty-evidence", token_count=0)
    assert cache.get("Q07", []) is not None


def test_file_cache_invalidates_on_mtime_change(tmp_path: Path):
    """chunk_processor._read_file_safe should re-read when mtime changes."""
    from qualix.context.chunk_processor import _file_cache, _read_file_safe

    # Clear module-level cache
    _file_cache.clear()

    f = tmp_path / "test.md"
    f.write_text("version-1", encoding="utf-8")

    content1 = _read_file_safe(f)
    assert content1 == "version-1"

    time.sleep(0.05)
    f.write_text("version-2", encoding="utf-8")

    content2 = _read_file_safe(f)
    assert content2 == "version-2", "File cache should detect mtime change and re-read"


def test_cache_reports_savings(tmp_path: Path):
    """Cache should report estimated token savings on hit."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)
    f1 = tmp_path / "big.md"
    f1.write_text("x" * 10000, encoding="utf-8")

    cache.put("Q07", [f1], "rendered-big", token_count=5000)
    cache.get("Q07", [f1])  # hit
    cache.get("Q07", [f1])  # hit

    stats = cache.stats()
    assert stats["estimated_tokens_saved"] == 10000  # 5000 * 2 hits


def test_end_to_end_cache_across_phases(tmp_path: Path):
    """Verify cache works across multiple phases sharing upstream artifacts."""
    from qualix.cache.evidence_cache import EvidencePackCache

    cache = EvidencePackCache(tmp_path)

    # Shared upstream file
    shared = tmp_path / "shared_upstream.json"
    shared.write_text('{"reqs": ["REQ-001", "REQ-002"]}', encoding="utf-8")

    # Phase-specific file
    q07_specific = tmp_path / "q07_code.ts"
    q07_specific.write_text("export class Foo {}", encoding="utf-8")

    # Q04 uses only shared
    cache.put("Q04", [shared], "Q04-evidence", token_count=200)
    # Q07 uses shared + code
    cache.put("Q07", [shared, q07_specific], "Q07-evidence", token_count=800)

    # Both should hit
    assert cache.get("Q04", [shared]) is not None
    assert cache.get("Q07", [shared, q07_specific]) is not None

    # Modify shared file — both should invalidate
    time.sleep(0.05)
    shared.write_text('{"reqs": ["REQ-001", "REQ-002", "REQ-003"]}', encoding="utf-8")

    assert cache.get("Q04", [shared]) is None
    assert cache.get("Q07", [shared, q07_specific]) is None

    # But Q07 with only code file (different key) would be a different entry
    cache.put("Q07-code-only", [q07_specific], "Q07-code-evidence", token_count=300)
    assert cache.get("Q07-code-only", [q07_specific]) is not None  # still valid
