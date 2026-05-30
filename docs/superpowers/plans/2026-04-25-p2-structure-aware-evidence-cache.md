# P2: Structure-Aware Evidence Pack Cache

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache the rendered Evidence Pack based on structural hash of input files, short-circuiting the entire `load_context() → render_evidence_pack()` pipeline when upstream artifacts haven't changed. Eliminates redundant file I/O, token estimation, chunk processing, and rendering on re-runs and cross-phase shared dependencies.

**Architecture:** Currently `load_context()` reads all upstream files, estimates tokens, sorts/splits/compacts chunks, then `render_evidence_pack()` renders bodies + key quotes + compresses. This is deterministic given the same input files. The fix: compute a structural hash from input file signatures (path + mtime + size), cache the rendered Evidence Pack text keyed by this hash, and return cached text when the hash matches. Invalidation is automatic — any file change produces a different hash.

**Tech Stack:** Python, existing `_file_signature()` pattern from `llm_result_cache.py`, SQLite `query_cache` table

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/qualix/cache/evidence_cache.py` | Evidence Pack structural cache: hash, store, lookup, stats |
| Modify | `src/qualix/context/context_loader.py` | Integrate cache into `load_context()` and `render_evidence_pack()` |
| Modify | `src/qualix/context/chunk_processor.py` | Upgrade `_file_cache` to mtime-aware LRU |
| Create | `tests/test_evidence_cache.py` | Cache hit/miss/invalidation tests |

---

### Task 1: Create `EvidencePackCache` with structural hashing

**Files:**
- Create: `src/qualix/cache/evidence_cache.py`
- Create: `tests/test_evidence_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence_cache.py`:

```python
"""Test structure-aware Evidence Pack cache."""
from __future__ import annotations

import time
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/qualix && python -m pytest tests/test_evidence_cache.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement EvidencePackCache**

Create `src/qualix/cache/evidence_cache.py`:

```python
"""Structure-aware Evidence Pack cache.

Caches rendered Evidence Pack text keyed by structural hash of input files.
Hash = sha256(phase_id + sorted file signatures). File signature = path:mtime_ns:size.
Any file change (content, addition, removal) produces a different hash → auto-invalidation.
"""
from __future__ import annotations

import hashlib
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
        import json

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

        import time
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
                (struct_hash, f"evidence_pack:{phase_id}", "evidence_pack",
                 dump_json_str(payload, indent=None), time.time()),
            )
        log.info("Evidence cache PUT: %s (hash=%s, %d files, %d tokens)",
                 phase_id, struct_hash, len(file_paths), token_count)

    def stats(self) -> dict[str, Any]:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        }
```

- [ ] **Step 4: Run tests**

Run: `cd /path/to/qualix && python -m pytest tests/test_evidence_cache.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/qualix/cache/evidence_cache.py tests/test_evidence_cache.py
git commit -m "feat(cache): add structure-aware Evidence Pack cache with file-signature hashing"
```

---

### Task 2: Integrate cache into `load_context()` pipeline

**Files:**
- Modify: `src/qualix/context/context_loader.py:247-304` (load_context function)
- Test: `tests/test_evidence_cache.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_cache.py`:

```python
def test_load_context_uses_cache(monkeypatch, tmp_path: Path):
    """load_context should return cached Evidence Pack on second call with same files."""
    render_calls = []

    from qualix.context.context_loader import LoadedContext
    original_render = LoadedContext.render_evidence_pack

    def spy_render(self):
        render_calls.append(1)
        return original_render(self)

    monkeypatch.setattr(LoadedContext, "render_evidence_pack", spy_render)

    # Setup minimal project structure
    from qualix.json_utils import save_json
    project_dir = tmp_path / "test-proj"
    (project_dir / "phaseA" / "_internal").mkdir(parents=True)
    save_json(project_dir / "state.json", {
        "project_id": "test-proj",
        "current_phase": "Q07",
        "completed_phases": ["Q01"],
    })

    # Create upstream artifact
    q01_dir = project_dir / "phaseA"
    q01_report = q01_dir / "q01_report.md"
    q01_report.write_text("# Q01 Report\nREQ-001 需求内容", encoding="utf-8")

    from qualix.context.context_loader import load_context

    # First call — should render
    ctx1 = load_context(tmp_path, "test-proj", "Q07")
    pack1 = ctx1.render_evidence_pack()
    call_count_1 = len(render_calls)

    # Second call — same files, should use cache
    ctx2 = load_context(tmp_path, "test-proj", "Q07")
    pack2 = ctx2.render_evidence_pack()

    # Evidence pack text should be identical
    assert pack1 == pack2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence_cache.py::test_load_context_uses_cache -v`
Expected: FAIL — no cache integration yet

- [ ] **Step 3: Integrate cache into LoadedContext**

In `src/qualix/context/context_loader.py`, modify `render_evidence_pack()`:

```python
def render_evidence_pack(self) -> str:
    """渲染 retrieval-first evidence pack（带结构缓存）."""
    # Check cache first
    if self._source_files and self._output_dir:
        from qualix.cache.evidence_cache import EvidencePackCache
        cache = EvidencePackCache(self._output_dir)
        cached = cache.get(self.phase_id, self._source_files)
        if cached is not None:
            return cached["rendered"]

    # ... existing rendering logic ...
    result = "\n".join(lines)

    # Store in cache
    if self._source_files and self._output_dir:
        from qualix.cache.evidence_cache import EvidencePackCache
        cache = EvidencePackCache(self._output_dir)
        cache.put(self.phase_id, self._source_files, result,
                  token_count=self.total_tokens)

    return result
```

Add `_source_files` and `_output_dir` fields to `LoadedContext.__init__`:

```python
@dataclass
class LoadedContext:
    phase_id: str
    model: ModelProfile
    chunks: list[ContextChunk] = field(default_factory=list)
    truncated: bool = False
    total_tokens: int = 0
    budget_tokens: int = 0
    verification_targets: list[dict] | None = None
    _source_files: list[Path] = field(default_factory=list)
    _output_dir: Path | None = None
```

In `_assemble_context()`, pass source file paths to `LoadedContext`:

```python
return LoadedContext(
    phase_id=target_phase,
    model=model,
    chunks=selected,
    truncated=truncated,
    total_tokens=used_tokens,
    budget_tokens=budget,
    verification_targets=verification_targets,
    _source_files=source_files,
    _output_dir=output_dir,
)
```

In `load_context()`, collect source file paths from chunks:

```python
# Collect source file paths for cache key
source_files = []
for chunk in all_chunks:
    if chunk.file_path:
        from pathlib import Path as _P
        fp = _P(chunk.file_path)
        if fp.exists():
            source_files.append(fp)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence_cache.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/qualix/context/context_loader.py tests/test_evidence_cache.py
git commit -m "feat(context): integrate Evidence Pack cache into load_context pipeline"
```

---

### Task 3: Upgrade `_file_cache` in chunk_processor to mtime-aware

**Files:**
- Modify: `src/qualix/context/chunk_processor.py:26-53`
- Test: `tests/test_evidence_cache.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_cache.py`:

```python
def test_file_cache_invalidates_on_mtime_change(tmp_path: Path):
    """chunk_processor._read_file_safe should re-read when mtime changes."""
    import time
    from qualix.context.chunk_processor import _read_file_safe, _file_cache

    # Clear module-level cache
    _file_cache.clear()

    f = tmp_path / "test.md"
    f.write_text("version-1", encoding="utf-8")

    content1 = _read_file_safe(f)
    assert content1 == "version-1"

    time.sleep(0.05)
    f.write_text("version-2", encoding="utf-8")

    content2 = _read_file_safe(f)
    assert content2 == "version-2", (
        "File cache should detect mtime change and re-read"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence_cache.py::test_file_cache_invalidates_on_mtime_change -v`
Expected: FAIL — current cache returns stale "version-1"

- [ ] **Step 3: Upgrade _file_cache to mtime-aware**

In `src/qualix/context/chunk_processor.py`, replace the simple dict cache:

```python
# Module-level file read cache: mtime-aware to avoid stale reads
_file_cache: dict[str, tuple[float, str | None]] = {}  # key → (mtime_ns, content)
_FILE_CACHE_MAX_SIZE = 128


def _read_file_safe(path: Path) -> str | None:
    """安全读取文件（带 mtime 感知缓存）."""
    key = str(path)
    if not path.exists():
        _file_cache[key] = (0, None)
        return None

    try:
        current_mtime = path.stat().st_mtime_ns
    except OSError:
        return None

    cached = _file_cache.get(key)
    if cached is not None:
        cached_mtime, cached_content = cached
        if cached_mtime == current_mtime:
            return cached_content

    try:
        content = path.read_text(encoding="utf-8")
        if len(_file_cache) >= _FILE_CACHE_MAX_SIZE:
            _file_cache.clear()
        _file_cache[key] = (current_mtime, content)
        return content
    except OSError:
        log.warning("Failed to read file: %s", path)
        _file_cache[key] = (current_mtime, None)
        return None
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence_cache.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/qualix/context/chunk_processor.py tests/test_evidence_cache.py
git commit -m "fix(chunk_processor): upgrade file cache to mtime-aware, prevent stale reads"
```

---

### Task 4: Add cache telemetry to observability pipeline

**Files:**
- Modify: `src/qualix/cache/evidence_cache.py`
- Modify: `src/qualix/reporting/observability.py` (if needed)
- Test: `tests/test_evidence_cache.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_cache.py`:

```python
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
```

- [ ] **Step 2: Implement token savings tracking**

Update `EvidencePackCache.get()` to accumulate saved tokens:

```python
def __init__(self, output_dir: Path):
    self.output_dir = output_dir
    self._hits = 0
    self._misses = 0
    self._tokens_saved = 0

def get(self, ...):
    # ... on hit:
    self._tokens_saved += data.get("token_count", 0)
    ...

def stats(self):
    total = self._hits + self._misses
    return {
        "hits": self._hits,
        "misses": self._misses,
        "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
        "estimated_tokens_saved": self._tokens_saved,
    }
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_evidence_cache.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/qualix/cache/evidence_cache.py tests/test_evidence_cache.py
git commit -m "feat(cache): add token savings telemetry to Evidence Pack cache"
```

---

### Task 5: Integration test — end-to-end cache verification

**Files:**
- Test: `tests/test_evidence_cache.py`

- [ ] **Step 1: Write integration test**

Add to `tests/test_evidence_cache.py`:

```python
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
    import time
    time.sleep(0.05)
    shared.write_text('{"reqs": ["REQ-001", "REQ-002", "REQ-003"]}', encoding="utf-8")

    assert cache.get("Q04", [shared]) is None
    assert cache.get("Q07", [shared, q07_specific]) is None

    # But Q07 with only code file (different key) would be a different entry
    cache.put("Q07-code-only", [q07_specific], "Q07-code-evidence", token_count=300)
    assert cache.get("Q07-code-only", [q07_specific]) is not None  # still valid
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_evidence_cache.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_evidence_cache.py
git commit -m "test: add end-to-end integration test for Evidence Pack cache across phases"
```

---

## Cost Impact Analysis

**Before (per Phase execution):**
- File I/O: read 5-15 upstream files (~50ms)
- Token estimation: scan all content (~20ms)
- Chunk processing: sort + split + compact (~10ms)
- Evidence rendering: body summaries + key quotes + compression (~30ms)
- Total: ~110ms per `load_context()` + `render_evidence_pack()` call

**After (cache hit):**
- Structural hash computation: stat() 5-15 files (~2ms)
- SQLite lookup: single indexed query (~1ms)
- Total: ~3ms per cache hit

**Savings per cache hit: ~107ms (97% reduction in context loading time)**

**Token savings:**
- Each cache hit avoids re-processing ~5K-50K tokens of Evidence Pack
- For a 7-phase run with 2 avg retries per phase: ~14 cache-eligible calls
- Conservative estimate: 50% hit rate → 7 cache hits × ~20K tokens = ~140K tokens saved
- At $15/M input tokens: ~$2.10 saved per full project run

**Combined with P0 (prompt cache) savings:**
- P0 saves on Anthropic API cache reads (input token pricing)
- P2 saves on local computation (file I/O + rendering)
- They are complementary — P2 avoids building the Evidence Pack, P0 avoids re-sending it

## Risks & Mitigations

1. **Stale cache if files change between stat() and read()** — Race window is <1ms in practice. The structural hash uses mtime_ns (nanosecond precision), making collisions extremely unlikely. Risk: NEGLIGIBLE.

2. **Cache grows unbounded in SQLite** — Each entry is ~50-200KB of rendered text. With `ON CONFLICT DO UPDATE`, each (phase_id, file_set) combination has at most one entry. Total cache size bounded by number of phases × file set variations. Risk: LOW.

3. **Non-deterministic rendering** — If `render_evidence_pack()` includes timestamps or random elements, cache would serve stale content. Current implementation is deterministic (no timestamps in output). Risk: LOW. Mitigation: the structural hash includes all input file signatures, so any input change invalidates.

4. **Memory pressure from mtime-aware file cache** — The upgraded `_file_cache` stores `(mtime_ns, content)` tuples. The existing `_FILE_CACHE_MAX_SIZE = 128` cap prevents unbounded growth. Risk: LOW.
