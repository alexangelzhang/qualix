# P1-B: Oracle-Guided Evidence Selection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace regex-driven key quote selection with requirement-aware selection that prioritizes quotes relevant to the current Phase's verification targets, improving Evidence Pack signal-to-noise ratio and reducing Adaptive Loop retries.

**Architecture:** `render_key_quotes()` currently selects quotes by regex pattern matching (`REQ-|BR-|SE-|...`). The fix: pass `verification_targets` (from phase_contract) into the evidence rendering pipeline, use the SE→BR→REQ mapping to boost quotes that reference requirements actually under review, then fall back to regex for remaining quota. This is a priority boost, not a replacement — regex still fills gaps.

**Tech Stack:** Python, existing phase_contract + evidence_renderer modules

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/dqg/context/evidence_renderer.py` | Add `priority_ids` param to `render_key_quotes()` for boosted selection |
| Modify | `src/dqg/context/context_loader.py` | Pass verification_targets IDs into `render_key_quotes()` |
| Modify | `src/dqg/runtime/phase_contract.py` | Add helper to extract flat ID set from verification_targets |
| Create | `tests/test_evidence_priority.py` | Test priority-boosted quote selection |

---

### Task 1: Add `priority_ids` parameter to `render_key_quotes()`

**Files:**
- Modify: `src/dqg/context/evidence_renderer.py:123-161`
- Create: `tests/test_evidence_priority.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evidence_priority.py`:

```python
"""Test Oracle-guided evidence selection with priority IDs."""
from __future__ import annotations

from types import SimpleNamespace


def _make_chunk(source: str, content: str, file_path: str = "") -> SimpleNamespace:
    return SimpleNamespace(source=source, content=content, file_path=file_path)


def test_priority_ids_boost_relevant_quotes():
    """Quotes matching priority_ids should be selected first."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [
        _make_chunk("Phase A", (
            "REQ-001 用户登录需要手机验证码\n\n"
            "REQ-002 管理员可以重置密码\n\n"
            "REQ-003 系统支持 OAuth2 登录\n\n"
            "BR-001 验证码 60 秒内有效\n\n"
            "BR-002 密码重置需要邮箱确认\n\n"
            "BR-003 OAuth2 回调必须验证 state 参数\n\n"
            "SE-001 登录接口返回 JWT token\n\n"
            "SE-002 重置密码接口发送邮件\n\n"
        ), "phase_a.json"),
    ]

    # Without priority: regex picks all REQ/BR/SE paragraphs in order
    result_no_priority = render_key_quotes(chunks, max_quotes=3)
    # First 3 quotes should be REQ-001, REQ-002, REQ-003 (order of appearance)

    # With priority: REQ-003 and BR-003 should come first
    result_with_priority = render_key_quotes(
        chunks, max_quotes=3, priority_ids={"REQ-003", "BR-003"}
    )

    # Priority quotes should appear before non-priority
    combined_text = "\n".join(result_with_priority)
    req003_pos = combined_text.find("REQ-003")
    req001_pos = combined_text.find("REQ-001")
    assert req003_pos >= 0, "REQ-003 should be in priority results"
    assert req003_pos < req001_pos or req001_pos == -1, (
        "REQ-003 (priority) should appear before REQ-001 (non-priority)"
    )


def test_priority_ids_empty_falls_back_to_regex():
    """Empty priority_ids should behave identically to current regex selection."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [
        _make_chunk("Phase A", "REQ-001 需求内容\n\nBR-001 业务规则", "phase_a.json"),
    ]

    result_none = render_key_quotes(chunks)
    result_empty = render_key_quotes(chunks, priority_ids=set())

    assert result_none == result_empty


def test_priority_ids_with_no_matches_falls_back():
    """If no quotes match priority_ids, fall back to regex selection."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [
        _make_chunk("Phase A", "REQ-001 需求内容\n\nBR-001 业务规则", "phase_a.json"),
    ]

    result = render_key_quotes(chunks, priority_ids={"REQ-999", "BR-999"})
    # Should still return quotes (regex fallback)
    assert len(result) > 0
    assert "REQ-001" in "\n".join(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/zhangyiqian/git_dev/dev-quality-gate/dev-quality-gate && python -m pytest tests/test_evidence_priority.py -v`
Expected: FAIL — `render_key_quotes()` does not accept `priority_ids`

- [ ] **Step 3: Implement priority-boosted selection**

In `src/dqg/context/evidence_renderer.py`, update `render_key_quotes()`:

```python
def render_key_quotes(
    chunks,
    *,
    max_quotes: int = 0,
    total_char_limit: int = 0,
    priority_ids: set[str] | None = None,
) -> list[str]:
    """从 chunks 中提取关键引用行，附 file:line citation.

    Args:
        priority_ids: Oracle-guided IDs (e.g. {"REQ-003", "BR-003"}).
            Quotes containing these IDs are selected first, remaining
            quota filled by regex fallback.
    """
    if not max_quotes:
        max_quotes = EVIDENCE_PACK_MAX_QUOTES
    if not total_char_limit:
        total_char_limit = EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT

    # Phase 1: Collect all candidate quotes with metadata
    all_candidates: list[tuple[str, str, str, bool]] = []  # (quote, source, file_path, is_priority)
    for chunk in chunks:
        file_path = getattr(chunk, "file_path", "") or ""
        for para in _pick_quote_candidates(chunk.content):
            is_priority = bool(priority_ids and any(pid in para for pid in priority_ids))
            all_candidates.append((para, chunk.source, file_path, is_priority))

    # Phase 2: Sort — priority first, then original order
    if priority_ids:
        priority_candidates = [c for c in all_candidates if c[3]]
        regular_candidates = [c for c in all_candidates if not c[3]]
        sorted_candidates = priority_candidates + regular_candidates
    else:
        sorted_candidates = all_candidates

    # Phase 3: Render quotes with budget
    lines: list[str] = []
    quote_count = 0
    used_chars = 0

    for para, source, file_path, _is_priority in sorted_candidates:
        if quote_count >= max_quotes or used_chars >= total_char_limit:
            break
        remaining = total_char_limit - used_chars
        if remaining <= 0:
            break
        quote = truncate_chars(para, min(EVIDENCE_PACK_QUOTE_CHAR_LIMIT, remaining))
        if not quote:
            continue
        quote_count += 1
        used_chars += len(quote)
        citation = source
        if file_path:
            citation += f" [来源: {file_path}]"
        lines.append(f"### 引用 {quote_count}: {citation}")
        lines.extend(f"> {line}" for line in quote.splitlines())
        lines.append("")

    if not lines:
        return ["（无可用关键引用）"]
    if lines[-1] == "":
        lines.pop()
    return lines
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence_priority.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/context/evidence_renderer.py tests/test_evidence_priority.py
git commit -m "feat(evidence): add priority_ids param to render_key_quotes for Oracle-guided selection"
```

---

### Task 2: Add helper to extract flat ID set from verification_targets

**Files:**
- Modify: `src/dqg/runtime/phase_contract.py`
- Test: `tests/test_evidence_priority.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_priority.py`:

```python
def test_extract_priority_ids_from_targets():
    """extract_priority_ids should return flat set of SE/BR/REQ IDs."""
    from dqg.runtime.phase_contract import extract_priority_ids

    targets = [
        {"se_id": "SE-001", "mapping_target": "REQ-001", "source": "phase_a"},
        {"se_id": "SE-002", "mapping_target": "BR-003", "source": "phase_a"},
        {"se_id": "PROFILE-RISK-001", "mapping_target": "profile_baseline", "source": "profile"},
    ]

    ids = extract_priority_ids(targets)
    assert "SE-001" in ids
    assert "SE-002" in ids
    assert "REQ-001" in ids
    assert "BR-003" in ids
    # Profile targets should also be included
    assert "PROFILE-RISK-001" in ids


def test_extract_priority_ids_empty():
    """Empty targets should return empty set."""
    from dqg.runtime.phase_contract import extract_priority_ids

    assert extract_priority_ids([]) == set()
    assert extract_priority_ids(None) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence_priority.py::test_extract_priority_ids_from_targets -v`
Expected: FAIL — `extract_priority_ids` does not exist

- [ ] **Step 3: Implement the helper**

In `src/dqg/runtime/phase_contract.py`, add:

```python
def extract_priority_ids(targets: list[dict[str, str]] | None) -> set[str]:
    """Extract flat set of requirement IDs from verification_targets.

    Collects se_id and mapping_target from each target.
    Used by evidence renderer to prioritize relevant quotes.
    """
    if not targets:
        return set()
    ids: set[str] = set()
    for t in targets:
        se_id = t.get("se_id", "")
        if se_id:
            ids.add(se_id)
        mapping = t.get("mapping_target", "")
        if mapping and mapping != "profile_baseline":
            ids.add(mapping)
        elif mapping == "profile_baseline" and se_id:
            # For profile targets, the se_id itself is the priority
            ids.add(se_id)
    return ids
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence_priority.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/runtime/phase_contract.py tests/test_evidence_priority.py
git commit -m "feat(contract): add extract_priority_ids helper for Oracle-guided evidence selection"
```

---

### Task 3: Wire priority_ids into the evidence rendering pipeline

**Files:**
- Modify: `src/dqg/context/context_loader.py:50-104` (render_evidence_pack)
- Test: `tests/test_evidence_priority.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_evidence_priority.py`:

```python
def test_loaded_context_passes_priority_ids(monkeypatch, tmp_path):
    """LoadedContext.render_evidence_pack() should pass priority_ids to render_key_quotes."""
    from types import SimpleNamespace

    from dqg.context.context_loader import LoadedContext

    # Track render_key_quotes calls
    render_calls = []
    original_render = None

    import dqg.context.evidence_renderer as er
    original_render = er.render_key_quotes

    def spy_render(chunks, **kwargs):
        render_calls.append(kwargs)
        return original_render(chunks, **kwargs)

    monkeypatch.setattr(er, "render_key_quotes", spy_render)

    # Create LoadedContext with verification_targets
    chunk = SimpleNamespace(
        source="Phase A",
        content="REQ-001 需求\n\nREQ-002 需求",
        file_path="phase_a.json",
        priority=1,
        token_estimate=100,
    )

    ctx = LoadedContext(
        phase_id="Q07",
        chunks=[chunk],
        total_tokens=100,
        budget_tokens=10000,
        truncated=False,
        model=SimpleNamespace(available_for_context=10000),
        verification_targets=[
            {"se_id": "SE-001", "mapping_target": "REQ-001", "source": "phase_a"},
        ],
    )

    ctx.render_evidence_pack()

    assert len(render_calls) >= 1
    last_call = render_calls[-1]
    assert "priority_ids" in last_call
    assert "REQ-001" in last_call["priority_ids"]
    assert "SE-001" in last_call["priority_ids"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_evidence_priority.py::test_loaded_context_passes_priority_ids -v`
Expected: FAIL — LoadedContext doesn't accept verification_targets or pass priority_ids

- [ ] **Step 3: Update LoadedContext**

In `src/dqg/context/context_loader.py`:

1. Add `verification_targets` field to `LoadedContext.__init__` (default `None`):

```python
def __init__(self, ..., verification_targets: list[dict] | None = None):
    ...
    self.verification_targets = verification_targets
```

2. In `render_evidence_pack()`, compute priority_ids and pass to `render_key_quotes()`:

```python
# Before the render_key_quotes call, add:
priority_ids = None
if self.verification_targets:
    from dqg.runtime.phase_contract import extract_priority_ids
    priority_ids = extract_priority_ids(self.verification_targets)

# Update the render_key_quotes call to include priority_ids:
key_quotes = render_key_quotes(
    self.chunks,
    max_quotes=limits["max_quotes"],
    total_char_limit=limits["total_quote_char_limit"],
    priority_ids=priority_ids,
)
```

Also update the fallback call:
```python
key_quotes = render_key_quotes(self.chunks, priority_ids=priority_ids)
```

3. In `load_context()` / `_assemble_context()`, load verification_targets from phase_contract.json and pass to LoadedContext:

```python
# In _assemble_context or load_context, after loading chunks:
contract_path = phase_root / "_internal" / "_phase_contract.json"
verification_targets = None
if contract_path.exists():
    from dqg.json_utils import load_json
    contract = load_json(contract_path)
    if contract:
        verification_targets = contract.get("verification_targets")
```

Pass `verification_targets` to the `LoadedContext` constructor.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_evidence_priority.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/context/context_loader.py src/dqg/context/evidence_renderer.py tests/test_evidence_priority.py
git commit -m "feat(evidence): wire Oracle-guided priority_ids through evidence rendering pipeline"
```

---

## Expected Impact

- Q07 reviewing a PR that touches REQ-003 and REQ-007 will now get Evidence Pack quotes focused on those requirements instead of a random sample of all REQ-* paragraphs
- Higher signal-to-noise ratio → Judge makes better decisions → fewer Adaptive Loop retries
- Indirect token savings: each avoided retry saves ~$0.78 (pre-P0) or ~$0.08 (post-P0) in input costs
- Conservative estimate: 20-30% reduction in retry rate for Q07
