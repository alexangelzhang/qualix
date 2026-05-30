# P0: Adaptive Loop Static/Dynamic Message Separation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate static context (system prompt, Evidence Pack) from dynamic content (Judge feedback) in Adaptive Loop messages, so Anthropic prompt cache hits on iterations 2/3 and input cost drops 80-90%.

**Architecture:** Currently `Agent.run()` is called fresh per iteration — each call builds a new `messages` list from scratch. The system prompt and context_payload are byte-identical across iterations (same worker_prompt, same context_files), but the Anthropic prompt cache is prefix-based: it only hits when the message sequence prefix is identical. Today, iteration 2+ prepends a handoff document to `context_files`, which changes the context_payload message, breaking the cache prefix. The fix: ensure the static messages (system + evidence) come first and are byte-identical, then append dynamic content (handoff/feedback) as a separate non-cached message.

**Tech Stack:** Python, Anthropic API (prompt caching with `cache_control: {"type": "ephemeral"}`)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/qualix/agents/adaptive_loop.py` | Split context_files into static (evidence) vs dynamic (handoff); pass both to Agent |
| Modify | `src/qualix/agents/agent.py` | Accept optional `dynamic_context_files` param; build messages with static prefix + dynamic suffix |
| Create | `tests/test_adaptive_cache_prefix.py` | Verify message prefix stability across iterations |
| Modify | `tests/test_agent_evidence_pack.py` | Add test for dynamic_context_files separation |

---

### Task 1: Add `dynamic_context_files` parameter to `Agent.run()`

**Files:**
- Modify: `src/qualix/agents/agent.py:244` (run method signature)
- Modify: `src/qualix/agents/agent.py:120` (add `_build_dynamic_payload`)
- Test: `tests/test_agent_evidence_pack.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_agent_evidence_pack.py`, add a test that verifies dynamic_context_files produce a separate non-cached message:

```python
def test_agent_run_separates_dynamic_context(monkeypatch, tmp_path: Path) -> None:
    """dynamic_context_files should produce a separate user message WITHOUT cache_control."""
    backend = _FakeBackend()
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *args, **kwargs: backend)

    static_file = tmp_path / "evidence.md"
    static_file.write_text("REQ-001 需求内容", encoding="utf-8")

    dynamic_file = tmp_path / "handoff.md"
    dynamic_file.write_text("Judge 反馈：缺少异常处理分析", encoding="utf-8")

    agent = Agent(
        name="demo",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    agent.run("修正报告", context_files=[static_file], dynamic_context_files=[dynamic_file])

    assert len(backend.calls) == 1
    msgs = backend.calls[0]
    # Expected: system(cached) + static_context(cached) + dynamic_context(NOT cached) + user_message
    assert len(msgs) == 4
    assert msgs[0]["role"] == "system"
    assert msgs[0].get("cache_control") is True
    assert msgs[1]["role"] == "user"
    assert msgs[1].get("cache_control") is True
    assert "REQ-001" in msgs[1]["content"]
    assert msgs[2]["role"] == "user"
    assert msgs[2].get("cache_control") is None or msgs[2].get("cache_control") is False
    assert "Judge 反馈" in msgs[2]["content"]
    assert msgs[3]["role"] == "user"
    assert msgs[3]["content"] == "修正报告"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/qualix && python -m pytest tests/test_agent_evidence_pack.py::test_agent_run_separates_dynamic_context -v`
Expected: FAIL — `Agent.run()` does not accept `dynamic_context_files`

- [ ] **Step 3: Add `_build_dynamic_payload` method and update `run()` signature**

In `src/qualix/agents/agent.py`, add the dynamic payload builder and update `run()`:

```python
# After _build_context_payload (line ~142), add:
def _build_dynamic_payload(self, dynamic_files: list[Path] | None) -> str:
    """Build dynamic context (handoff, feedback) — NOT cached."""
    if not dynamic_files:
        return ""
    blocks: list[str] = []
    seen: set[str] = set()
    used = 0
    for f in dynamic_files:
        key = str(f)
        if key in seen or not f.exists():
            continue
        seen.add(key)
        remaining = AGENT_EVIDENCE_TOTAL_LIMIT - used
        if remaining <= 0:
            break
        excerpt = self._read_excerpt(f, min(AGENT_EVIDENCE_EXCERPT_LIMIT, remaining))
        if not excerpt:
            continue
        blocks.append(f"## 文件: {f.name}\n\n{excerpt}")
        used += len(excerpt)
    return "\n\n---\n\n".join(blocks)
```

Update `run()` method signature (line 244):

```python
def run(
    self,
    user_message: str,
    context_files: list[Path] | None = None,
    dynamic_context_files: list[Path] | None = None,
) -> AgentResult:
```

Update `_cache_key_components` (line 236) to also accept dynamic_context_files:

```python
def _cache_key_components(
    self, backend_name: str, context_files: list[Path] | None, user_message: str,
    dynamic_context_files: list[Path] | None = None,
) -> tuple[str, str, str, str]:
    system_content = self._build_system_content()
    context_payload = self._build_context_payload(context_files)
    dynamic_payload = self._build_dynamic_payload(dynamic_context_files)
    payload_json = self._cache_key_payload(backend_name, system_content, context_payload + dynamic_payload, user_message)
    return system_content, context_payload, dynamic_payload, payload_json
```

Update message construction in `run()` (lines 268-273):

```python
messages = []
if system_content and system_content.strip():
    messages.append({"role": "system", "content": system_content, "cache_control": True})
if context_payload:
    messages.append({"role": "user", "content": context_payload, "cache_control": True})
if dynamic_payload:
    messages.append({"role": "user", "content": dynamic_payload})
messages.append({"role": "user", "content": user_message})
```

Also update the cache lookup/store calls and prompt_hash computation to use the new 4-tuple return.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /path/to/qualix && python -m pytest tests/test_agent_evidence_pack.py -v`
Expected: ALL PASS (including existing tests — they don't pass dynamic_context_files, so behavior unchanged)

- [ ] **Step 5: Commit**

```bash
git add src/qualix/agents/agent.py tests/test_agent_evidence_pack.py
git commit -m "feat(agent): add dynamic_context_files param for cache-friendly message separation"
```

---

### Task 2: Verify existing tests still pass (no regression)

**Files:**
- Test: `tests/test_agent_evidence_pack.py`
- Test: `tests/test_agent_cache.py`

- [ ] **Step 1: Run all agent-related tests**

Run: `cd /path/to/qualix && python -m pytest tests/test_agent_evidence_pack.py tests/test_agent_cache.py tests/test_adaptive_loop_cache.py tests/test_adaptive_loop_guard.py -v`
Expected: ALL PASS — the `dynamic_context_files` param defaults to None, so all existing call sites are unaffected.

- [ ] **Step 2: Run full test suite**

Run: `cd /path/to/qualix && python -m pytest tests/ -x -q`
Expected: ALL PASS

---

### Task 3: Update AdaptiveLoop to separate static vs dynamic context

**Files:**
- Modify: `src/qualix/agents/adaptive_loop.py:262-296` (_execute_iteration method)
- Test: `tests/test_adaptive_cache_prefix.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_adaptive_cache_prefix.py`:

```python
"""Verify Adaptive Loop produces cache-stable message prefixes across iterations."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class FakeBackend:
    def __init__(self):
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kwargs):
        self.calls.append([dict(m) for m in messages])
        return "## 报告\n内容", {"input_tokens": 100, "output_tokens": 50}

    def name(self):
        return "fake-backend"


def _make_judge_result(consensus="FAIL", avg_score=2.0):
    """Create a minimal VoteResult for testing."""
    from qualix.agents.judge_vote import JudgeVote, VoteResult
    vote = JudgeVote(model="fake", verdict=consensus, overall=avg_score, issues=["issue1"])
    return VoteResult(votes=[vote], consensus=consensus, avg_score=avg_score, disagreements=[])


@pytest.fixture
def loop_env(tmp_path):
    """Set up minimal environment for AdaptiveLoop."""
    project_id = "test-project"
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    # Create state.json
    from qualix.json_utils import save_json
    state_dir = output_dir / project_id
    state_dir.mkdir()
    save_json(state_dir / "state.json", {"project_id": project_id, "current_phase": "Q07"})

    # Create phase dir
    phase_dir = state_dir / "phaseD"
    phase_dir.mkdir()
    int_dir = phase_dir / "_internal"
    int_dir.mkdir()

    # Create context files (static evidence)
    evidence = int_dir / "_upstream_context.md"
    evidence.write_text("REQ-001 需求内容\nBR-001 业务规则", encoding="utf-8")

    return {
        "output_dir": output_dir,
        "project_id": project_id,
        "evidence": evidence,
    }


def test_static_prefix_identical_across_iterations(loop_env, monkeypatch):
    """The system + context_payload messages must be byte-identical in iter 1 and iter 2."""
    backend = FakeBackend()
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *a, **kw: backend)

    # Capture Agent.run calls
    run_calls: list[dict] = []
    original_run = None

    from qualix.agents.agent import Agent
    original_run = Agent.run

    def patched_run(self, user_message, context_files=None, dynamic_context_files=None):
        run_calls.append({
            "context_files": context_files,
            "dynamic_context_files": dynamic_context_files,
        })
        return original_run(self, user_message, context_files=context_files, dynamic_context_files=dynamic_context_files)

    monkeypatch.setattr(Agent, "run", patched_run)

    # Mock judge to FAIL first, PASS second
    judge_results = iter([
        _make_judge_result("FAIL", 2.0),
        _make_judge_result("PASS", 4.0),
    ])
    monkeypatch.setattr(
        "qualix.agents.adaptive_loop.multi_judge_vote",
        lambda *a, **kw: next(judge_results),
    )

    # Mock task_store
    monkeypatch.setattr("qualix.agents.adaptive_loop.create_task_run", lambda *a, **kw: "task-1")
    monkeypatch.setattr("qualix.agents.adaptive_loop.complete_task_run", lambda *a, **kw: None)
    monkeypatch.setattr("qualix.agents.adaptive_loop.add_task_event", lambda *a, **kw: None)
    monkeypatch.setattr("qualix.agents.adaptive_loop.save_checkpoint", lambda *a, **kw: None)

    from qualix.agents.adaptive_loop import AdaptiveLoop
    loop = AdaptiveLoop(loop_env["output_dir"])

    loop.run(
        project_id=loop_env["project_id"],
        phase_id="Q07",
        worker_prompt="审查代码",
        judge_rubric="评分标准",
        critique_prompt="找出问题",
        context_files=[loop_env["evidence"]],
        max_iterations=2,
        worker_model="fake-model",
        judge_models=["fake-model"],
        fallback="fake-model",
    )

    # Iteration 1: worker call — context_files has evidence, no dynamic
    # Iteration 2: fixer call — context_files has evidence (same), dynamic has handoff
    assert len(run_calls) >= 2  # At least worker + fixer (+ critiques)

    worker_call = run_calls[0]  # iter 1 worker
    fixer_call = run_calls[2]   # iter 2 fixer (run_calls[1] is iter 1 critique)

    # Static context_files must be identical
    worker_static = [str(f) for f in (worker_call["context_files"] or [])]
    fixer_static = [str(f) for f in (fixer_call["context_files"] or [])]
    assert worker_static == fixer_static, (
        f"Static context_files differ between iterations:\n"
        f"  iter1: {worker_static}\n"
        f"  iter2: {fixer_static}"
    )

    # Fixer should have dynamic_context_files (handoff + report)
    assert fixer_call["dynamic_context_files"] is not None
    assert len(fixer_call["dynamic_context_files"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/qualix && python -m pytest tests/test_adaptive_cache_prefix.py::test_static_prefix_identical_across_iterations -v`
Expected: FAIL — AdaptiveLoop still prepends handoff to context_files

- [ ] **Step 3: Modify `_execute_iteration` to separate static/dynamic context**

In `src/qualix/agents/adaptive_loop.py`, change the fixer iteration (lines 276-296):

Current code (iteration > 0):
```python
fixer_context = [handoff_path, report_path] + (context_files or [])
record.worker_result = fixer.run(
    f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
    context_files=fixer_context,
)
```

New code:
```python
record.worker_result = fixer.run(
    f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
    context_files=context_files,
    dynamic_context_files=[handoff_path, report_path],
)
```

This keeps `context_files` (the static evidence) identical across iterations, and moves the per-iteration handoff + report into `dynamic_context_files`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /path/to/qualix && python -m pytest tests/test_adaptive_cache_prefix.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /path/to/qualix && python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/qualix/agents/adaptive_loop.py tests/test_adaptive_cache_prefix.py
git commit -m "feat(adaptive-loop): separate static/dynamic context for prompt cache hits on retries"
```

---

### Task 4: Verify cache token metrics in telemetry

**Files:**
- Modify: `src/qualix/agents/agent.py:45-57` (extract_llm_call)
- Test: `tests/test_adaptive_cache_prefix.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_adaptive_cache_prefix.py`:

```python
def test_cache_tokens_reported_in_telemetry(loop_env, monkeypatch):
    """AgentResult.token_usage should include cache_read_input_tokens when available."""
    class CacheAwareBackend:
        def __init__(self):
            self.call_count = 0

        def chat(self, messages, **kwargs):
            self.call_count += 1
            usage = {"input_tokens": 100, "output_tokens": 50}
            if self.call_count > 1:
                usage["cache_read_input_tokens"] = 80
                usage["cache_creation_input_tokens"] = 0
            else:
                usage["cache_creation_input_tokens"] = 90
                usage["cache_read_input_tokens"] = 0
            return "## 报告\n内容", usage

        def name(self):
            return "fake-cache-backend"

    backend = CacheAwareBackend()
    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *a, **kw: backend)

    from qualix.agents.agent import Agent
    from qualix.agents.llm_backends import LLMConfig

    agent = Agent(
        name="test",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )

    # First call — cache creation
    r1 = agent.run("task 1")
    assert r1.token_usage.get("cache_creation_input_tokens", 0) == 90

    # Second call — cache read (different agent instance, same prompt)
    agent2 = Agent(
        name="test2",
        role="worker",
        system_prompt="system",
        model=LLMConfig(primary="fake-model", fallback=None),
    )
    r2 = agent2.run("task 2")
    assert r2.token_usage.get("cache_read_input_tokens", 0) == 80
```

- [ ] **Step 2: Run test to verify it passes (or fails)**

Run: `cd /path/to/qualix && python -m pytest tests/test_adaptive_cache_prefix.py::test_cache_tokens_reported_in_telemetry -v`

Check: The `token_usage` dict in `AgentResult` already accumulates whatever the backend returns. If the test passes, no code change needed. If it fails, update the token accumulation in `Agent.run()` (line 328) to also capture cache tokens:

```python
# After line 328-329:
total_input_tokens += usage.get("input_tokens", 0)
total_output_tokens += usage.get("output_tokens", 0)
# Add:
total_cache_creation += usage.get("cache_creation_input_tokens", 0)
total_cache_read += usage.get("cache_read_input_tokens", 0)
```

And include them in the final `token_usage` dict (line 377).

- [ ] **Step 3: Update `extract_llm_call` to surface cache metrics**

In `src/qualix/agents/agent.py`, update `extract_llm_call()` (line 45):

```python
def extract_llm_call(result: AgentResult) -> dict[str, int | str | bool | float]:
    """Extract LLM call telemetry from an AgentResult."""
    return {
        "agent_name": result.agent_name,
        "agent_role": result.role,
        "model_id": result.model_used,
        "prompt_hash": result.prompt_hash,
        "input_tokens": result.token_usage.get("input_tokens", 0),
        "output_tokens": result.token_usage.get("output_tokens", 0),
        "cache_creation_input_tokens": result.token_usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": result.token_usage.get("cache_read_input_tokens", 0),
        "cache_hit": result.cache_hit,
        "duration_seconds": round(result.duration_seconds, 2),
        "status": result.status,
    }
```

- [ ] **Step 4: Run tests**

Run: `cd /path/to/qualix && python -m pytest tests/test_adaptive_cache_prefix.py tests/test_agent_evidence_pack.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/qualix/agents/agent.py tests/test_adaptive_cache_prefix.py
git commit -m "feat(telemetry): surface cache_creation/cache_read token metrics in LLM call telemetry"
```

---

### Task 5: Integration smoke test — end-to-end cache prefix verification

**Files:**
- Test: `tests/test_adaptive_cache_prefix.py`

- [ ] **Step 1: Write integration test**

Add to `tests/test_adaptive_cache_prefix.py`:

```python
def test_message_bytes_prefix_stable(monkeypatch, tmp_path):
    """Directly verify that the first N messages sent to the backend are byte-identical across iterations."""
    all_message_lists: list[list[dict]] = []

    class SpyBackend:
        def chat(self, messages, **kwargs):
            all_message_lists.append([
                {"role": m["role"], "content": m["content"], "cache_control": m.get("cache_control")}
                for m in messages
            ])
            return "## 报告\n内容", {"input_tokens": 100, "output_tokens": 50}

        def name(self):
            return "spy-backend"

    monkeypatch.setattr("qualix.agents.agent.create_backend", lambda *a, **kw: SpyBackend())

    from qualix.agents.agent import Agent
    from qualix.agents.llm_backends import LLMConfig

    evidence = tmp_path / "evidence.md"
    evidence.write_text("REQ-001 需求\nBR-001 规则\nSE-001 语义期望", encoding="utf-8")

    handoff = tmp_path / "handoff.md"
    handoff.write_text("Judge 反馈：缺少边界条件分析", encoding="utf-8")

    # Iteration 1: worker (static only)
    agent1 = Agent(
        name="worker-iter1", role="worker", system_prompt="审查代码",
        model=LLMConfig(primary="fake", fallback=None),
    )
    agent1.run("执行审查", context_files=[evidence])

    # Iteration 2: fixer (static + dynamic)
    agent2 = Agent(
        name="fixer-iter2", role="worker", system_prompt="审查代码",
        model=LLMConfig(primary="fake", fallback=None),
    )
    agent2.run("修正报告", context_files=[evidence], dynamic_context_files=[handoff])

    assert len(all_message_lists) == 2

    iter1_msgs = all_message_lists[0]
    iter2_msgs = all_message_lists[1]

    # The cached prefix (system + static context) must be identical
    # iter1: [system, static_context, user_message]
    # iter2: [system, static_context, dynamic_context, user_message]
    assert iter1_msgs[0] == iter2_msgs[0], "System message differs"
    assert iter1_msgs[1] == iter2_msgs[1], "Static context message differs"

    # iter2 has an extra dynamic message before user_message
    assert len(iter2_msgs) == len(iter1_msgs) + 1
    assert iter2_msgs[2]["cache_control"] is None  # dynamic = not cached
    assert "Judge 反馈" in iter2_msgs[2]["content"]
```

- [ ] **Step 2: Run test**

Run: `cd /path/to/qualix && python -m pytest tests/test_adaptive_cache_prefix.py::test_message_bytes_prefix_stable -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /path/to/qualix && python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_adaptive_cache_prefix.py
git commit -m "test: add integration test verifying byte-stable cache prefix across adaptive iterations"
```

---

## Cost Impact Analysis

**Before (per Adaptive Loop retry):**
- System prompt: ~2K tokens × $15/M = $0.03
- Evidence Pack: ~50K tokens × $15/M = $0.75
- Total static per retry: ~$0.78

**After (cache read pricing):**
- System prompt: ~2K tokens × $1.5/M = $0.003
- Evidence Pack: ~50K tokens × $1.5/M = $0.075
- Total static per retry: ~$0.078

**Savings per retry: ~$0.70 (90%)**
**Savings per run (7 phases × 0.5 avg retries): ~$2.45**

## Risks & Mitigations

1. **Cache miss if Evidence Pack contains timestamps or random ordering** — The current `_build_context_payload` reads files deterministically (same file list → same output). No timestamps are injected. Risk: LOW.

2. **Anthropic cache eviction** — Ephemeral cache has a 5-minute TTL. Adaptive Loop iterations typically complete within 2-3 minutes. Risk: LOW.

3. **Dynamic payload exceeds token budget** — The handoff document + report could be large. Mitigation: `_build_dynamic_payload` applies the same `AGENT_EVIDENCE_TOTAL_LIMIT` cap. The total prompt size is bounded.
