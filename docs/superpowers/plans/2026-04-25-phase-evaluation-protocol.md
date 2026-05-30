# Phase-Level Evaluation Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each Phase's Judge and Critique a specialized evaluation protocol (checklist + red lines + domain vocab) backed by automatic experience accumulation and HARD gate enforcement.

**Architecture:** New `evaluation_protocols.py` defines static PhaseProtocol data per Phase. Gene store gets phase_id+agent_role tagging for filtered injection. A new finalize handler enforces checklist coverage as HARD gate via GateVerdict. Adaptive loop wires protocol into Judge/Critique prompts.

**Tech Stack:** Python 3.11+, pytest, existing Qualix modules (gene_store, gate_verdict, lifecycle, adaptive_loop)

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/qualix/quality/evaluation_protocols.py` | PhaseProtocol + AgentProtocol dataclasses + 7 Phase static configs + render functions |
| Create | `tests/test_evaluation_protocols.py` | Protocol data integrity + render tests |
| Modify | `src/qualix/quality/gene_store.py` | Add agent_role field to Gene, filter by phase_id+agent_role in load/match |
| Create | `tests/test_gene_store_phase_filter.py` | Gene phase+role filtering tests |
| Modify | `src/qualix/agents/adaptive_loop.py` | Inject protocol into Judge/Critique prompts |
| Create | `src/qualix/runtime/handlers_protocol.py` | handle_protocol_compliance finalize handler |
| Create | `tests/test_handlers_protocol.py` | Protocol compliance handler tests |
| Create | `tests/test_protocol_integration.py` | End-to-end integration test |

### Task 1: PhaseProtocol Data Structures + 7 Phase Static Configs

**Files:**
- Create: `src/qualix/quality/evaluation_protocols.py`
- Create: `tests/test_evaluation_protocols.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_evaluation_protocols.py` with these tests:
- `test_all_seven_phases_have_protocols`: assert Q01-Q07 all in `PHASE_PROTOCOLS`
- `test_each_protocol_has_judge_and_critique`: each has judge/critique with ≥3 checklist items, ≥1 red_line, ≥2 focus_areas
- `test_judge_and_critique_checklists_are_different`: overlap < 50% (orthogonal views)
- `test_render_protocol_for_prompt`: output contains `## 检查清单` and `## 行为红线`
- `test_render_protocol_includes_domain_vocab`: Q01 judge render contains `## 领域词汇` and `REQ`
- `test_get_protocol_returns_none_for_unknown`: `get_protocol("Q99")` returns None
- `test_get_protocol_returns_correct_phase`: `get_protocol("Q07").phase_id == "Q07"`

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_evaluation_protocols.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create evaluation_protocols.py**

Create `src/qualix/quality/evaluation_protocols.py` with:

1. `AgentProtocol` frozen dataclass: `role_label`, `checklist` (tuple[str,...]), `red_lines` (tuple[str,...]), `domain_vocab` (dict), `focus_areas` (tuple), `not_applicable` (str)
2. `PhaseProtocol` frozen dataclass: `phase_id`, `judge: AgentProtocol`, `critique: AgentProtocol`
3. 7 Phase configs (`_Q01` through `_Q07`) — use the exact checklist/red_lines/domain_vocab/focus_areas from the spec (docs/superpowers/specs/2026-04-25-phase-evaluation-protocol-design.md, Sections "7 Phase Judge Protocol" and "7 Phase Critique Protocol")
4. `PHASE_PROTOCOLS: Final[dict[str, PhaseProtocol]]` registry
5. `get_protocol(phase_id) -> PhaseProtocol | None`
6. `render_protocol_for_prompt(protocol: AgentProtocol) -> str` — renders checklist, red_lines, domain_vocab, focus_areas as markdown. NO role_label in output.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_evaluation_protocols.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/quality/evaluation_protocols.py tests/test_evaluation_protocols.py
git commit -m "feat: add PhaseProtocol data structures with 7 Phase evaluation protocols"
```

### Task 2: Gene Store — Add agent_role Field + Phase Filtering

**Files:**
- Modify: `src/qualix/quality/gene_store.py`
- Create: `tests/test_gene_store_phase_filter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_gene_store_phase_filter.py`:

```python
# tests/test_gene_store_phase_filter.py
"""Tests for Gene store phase_id + agent_role filtering."""
from __future__ import annotations

import json
from pathlib import Path


def _make_gene(gene_id: str, phase_id: str, agent_role: str = "judge") -> dict:
    return {
        "gene_id": gene_id,
        "phase_id": phase_id,
        "agent_role": agent_role,
        "error_type": "FN",
        "severity": "high",
        "target_pattern": "降级|超时",
        "description": "缺少降级策略",
        "action": "补充降级方案",
        "confidence": "high",
        "impact": "high",
        "source": {"project_id": "test", "phase_id": phase_id},
        "match_count": 0,
        "last_matched_at": None,
    }


def test_load_genes_for_phase_and_role(tmp_path):
    """load_genes_for_phase filters by phase_id (existing behavior)."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(tmp_path, [_make_gene("G1", "Q03"), _make_gene("G2", "Q07")])
    q03_genes = load_genes_for_phase(tmp_path, "Q03")
    assert len(q03_genes) == 1
    assert q03_genes[0]["gene_id"] == "G1"


def test_load_genes_filters_by_agent_role(tmp_path):
    """load_genes_for_phase with agent_role filters correctly."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(tmp_path, [
        _make_gene("G1", "Q03", "judge"),
        _make_gene("G2", "Q03", "critique"),
    ])
    judge_genes = load_genes_for_phase(tmp_path, "Q03", agent_role="judge")
    assert len(judge_genes) == 1
    assert judge_genes[0]["agent_role"] == "judge"

    critique_genes = load_genes_for_phase(tmp_path, "Q03", agent_role="critique")
    assert len(critique_genes) == 1
    assert critique_genes[0]["agent_role"] == "critique"


def test_load_genes_no_role_filter_returns_all(tmp_path):
    """Without agent_role filter, returns all genes for the phase."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    save_genes(tmp_path, [
        _make_gene("G1", "Q03", "judge"),
        _make_gene("G2", "Q03", "critique"),
    ])
    all_genes = load_genes_for_phase(tmp_path, "Q03")
    assert len(all_genes) == 2


def test_extract_genes_includes_agent_role():
    """Extracted genes include agent_role field."""
    from qualix.quality.gene_store import extract_genes_from_preference

    preference = {
        "preferred": "v2",
        "confidence": "high",
        "critique_effectiveness": [
            {"was_valid": True, "should_persist": True, "impact": "high", "critique_issue": "缺少降级"}
        ],
    }
    critique = {"issues_found": [{"description": "缺少降级", "type": "FN", "severity": "high"}]}
    genes = extract_genes_from_preference(preference, critique, "Q03", "test-proj", agent_role="judge")
    assert len(genes) >= 1
    assert genes[0].get("agent_role") == "judge"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gene_store_phase_filter.py -v`
Expected: FAIL (agent_role parameter not accepted)

- [ ] **Step 3: Modify gene_store.py**

Three changes to `src/qualix/quality/gene_store.py`:

3a. In `extract_genes_from_preference` (line 45), add `agent_role: str = "judge"` parameter. In the gene dict construction (around line 88), add `"agent_role": agent_role`.

3b. In `load_genes_for_phase` (line 191), add `agent_role: str | None = None` parameter. After loading genes, filter:
```python
    if agent_role:
        genes = [g for g in genes if g.get("agent_role", "judge") == agent_role]
```

3c. No changes to `match_genes` or `render_genes_for_prompt` — they work on already-filtered lists.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_gene_store_phase_filter.py -v`
Expected: 4 passed

- [ ] **Step 5: Run existing tests for regression**

Run: `pytest tests/ -q`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/qualix/quality/gene_store.py tests/test_gene_store_phase_filter.py
git commit -m "feat: add agent_role to Gene store with phase+role filtering"
```

### Task 3: Wire Protocol into Adaptive Loop Judge Prompt

**Files:**
- Modify: `src/qualix/agents/adaptive_loop.py`

- [ ] **Step 1: Add protocol injection in run() method**

In `AdaptiveLoop.run()`, after the P3 compose_rubric block (added in previous plan), add:

```python
        # Protocol: inject Phase-specific checklist + red_lines into judge rubric
        from qualix.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt

        _protocol = get_protocol(phase_id)
        if _protocol:
            _judge_protocol_text = render_protocol_for_prompt(_protocol.judge)
            judge_rubric = _judge_protocol_text + "\n\n" + judge_rubric
            log.info("Protocol injected: phase=%s, judge checklist=%d items",
                     phase_id, len(_protocol.judge.checklist))

            # Inject dynamic experience (genes filtered by phase+role)
            from qualix.quality.gene_store import load_genes_for_phase, match_genes, render_genes_for_prompt

            _phase_genes = load_genes_for_phase(
                self.output_dir.parent, phase_id, agent_role="judge"
            )
            if _phase_genes and report_path.exists():
                _matched = match_genes(_phase_genes, report_path.read_text(encoding="utf-8", errors="replace"))
                if _matched:
                    judge_rubric = judge_rubric + "\n\n" + render_genes_for_prompt(_matched)
                    log.info("Dynamic genes injected: %d matched for judge", len(_matched))
```

- [ ] **Step 2: Add protocol injection for Critique prompt**

In `_execute_iteration`, where the critique Agent is created, prepend protocol to critique_prompt. Change the critique block (inside `if not skip_critique:`) to:

```python
        if not skip_critique:
            _critique_system = critique_prompt
            if _protocol:
                from qualix.quality.evaluation_protocols import render_protocol_for_prompt as _render_proto
                _critique_system = _render_proto(_protocol.critique) + "\n\n" + critique_prompt
```

Note: `_protocol` needs to be passed to `_execute_iteration`. Add `protocol: "PhaseProtocol | None" = None` parameter and pass it from `run()`.

- [ ] **Step 3: Run existing adaptive loop tests**

Run: `pytest tests/test_adaptive_loop_guard.py tests/test_adaptive_loop_cache.py tests/test_adaptive_cache_prefix.py -v`
Expected: All pass (new params have defaults)

- [ ] **Step 4: Commit**

```bash
git add src/qualix/agents/adaptive_loop.py
git commit -m "feat: inject Phase evaluation protocol into Judge/Critique prompts"
```

### Task 4: Protocol Compliance Finalize Handler

**Files:**
- Create: `src/qualix/runtime/handlers_protocol.py`
- Create: `tests/test_handlers_protocol.py`
- Modify: `src/qualix/runtime/handlers_finalize.py` (register the handler)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_handlers_protocol.py
"""Tests for protocol compliance finalize handler."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


def _make_ctx(tmp_path, phase_id="Q07"):
    """Create minimal ExecutionContext mock."""
    ctx = MagicMock()
    ctx.output_dir = tmp_path
    ctx.project_id = "test"
    ctx.phase_id = phase_id
    ctx.internal_dir = tmp_path / "test" / phase_id / "_internal"
    ctx.internal_dir.mkdir(parents=True, exist_ok=True)
    ctx.shared = {}
    return ctx


def _make_result():
    return MagicMock(errors=[], warnings=[])


def test_protocol_compliance_passes_when_all_covered(tmp_path):
    """All checklist items mentioned in judge result → no errors."""
    from qualix.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()

    # Write a judge result that mentions all Q07 checklist keywords
    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [
            {"description": "finding 有具体文件:行号证据"},
            {"description": "REQ/BR/SE 在代码中的实现完整"},
            {"description": "调用链追踪 Controller→Service→Domain→Gateway"},
            {"description": "blast radius 内的 callers 已评估"},
            {"description": "严重级别分级合理"},
        ],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    # No BLOCKED errors
    assert not any("BLOCKED" in str(e) for e in result.errors)


def test_protocol_compliance_blocks_when_checklist_uncovered(tmp_path):
    """Missing checklist items → BLOCKED error."""
    from qualix.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()
    result.errors = []

    # Write a judge result that only covers 1 of 5 items
    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [{"description": "finding 有证据"}],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    blocked = [e for e in result.errors if "BLOCKED" in str(e)]
    assert len(blocked) > 0


def test_protocol_compliance_skips_unknown_phase(tmp_path):
    """Unknown phase → no errors, no warnings."""
    from qualix.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q99")
    result = _make_result()
    handle_protocol_compliance(ctx, result)
    assert len(result.errors) == 0


def test_protocol_compliance_warns_on_zero_dynamic_genes(tmp_path):
    """No dynamic genes → WARNING (SOFT, not BLOCKED)."""
    from qualix.runtime.handlers_protocol import handle_protocol_compliance

    ctx = _make_ctx(tmp_path, "Q07")
    result = _make_result()

    # Full coverage judge result
    judge_result = {
        "verdict": "PASS",
        "overall": 4.0,
        "issues": [
            {"description": "finding 有具体文件:行号证据"},
            {"description": "REQ/BR/SE 在代码中的实现完整"},
            {"description": "调用链追踪 Controller→Service→Domain→Gateway"},
            {"description": "blast radius 内的 callers 已评估"},
            {"description": "严重级别分级合理"},
        ],
    }
    phase_dir = tmp_path / "test" / "Q07"
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "_judge_result.json").write_text(json.dumps(judge_result))

    handle_protocol_compliance(ctx, result)
    warnings = [w for w in result.warnings if "dynamic" in str(w).lower() or "gene" in str(w).lower()]
    assert len(warnings) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_protocol.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create handlers_protocol.py**

Create `src/qualix/runtime/handlers_protocol.py`:

```python
"""Protocol compliance finalize handler.

Checks that Judge output covers all static checklist items from the
Phase's evaluation protocol. Missing items → BLOCKED (HARD gate).
Zero dynamic genes → WARNING (SOFT).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.log import get_logger

if TYPE_CHECKING:
    from qualix.runtime.execution_context import ExecutionContext
    from qualix.runtime.result import PhaseResult

log = get_logger(__name__)


def handle_protocol_compliance(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Check Judge output covers Phase protocol checklist."""
    from qualix.quality.evaluation_protocols import get_protocol

    protocol = get_protocol(ctx.phase_id)
    if not protocol:
        return

    # Load judge result
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json

    phase_dir = ctx.output_dir / ctx.project_id / PHASE_DIR_MAP.get(ctx.phase_id, ctx.phase_id)
    judge_path = phase_dir / "_judge_result.json"
    if not judge_path.exists():
        # No judge result yet — skip (judge runs in adaptive loop, not finalize)
        return

    judge_data = load_json(judge_path)
    if not judge_data:
        return

    # Collect all text from judge issues for matching
    judge_text = ""
    for issue in judge_data.get("issues", []):
        judge_text += " " + issue.get("description", "")
    judge_text = judge_text.lower()

    # Check each checklist item — extract 2-3 keywords per item for fuzzy match
    uncovered = []
    for item in protocol.judge.checklist:
        # Extract Chinese keywords (2+ chars) from checklist item
        import re
        keywords = re.findall(r"[\u4e00-\u9fff]{2,6}", item)
        # Also extract English keywords
        keywords += re.findall(r"[a-zA-Z_]{3,}", item)
        if not keywords:
            continue
        # At least one keyword must appear in judge output
        if not any(kw.lower() in judge_text for kw in keywords):
            uncovered.append(item)

    if uncovered:
        msg = (
            f"BLOCKED: required handler protocol_compliance failed — "
            f"{len(uncovered)}/{len(protocol.judge.checklist)} checklist items uncovered: "
            + "; ".join(uncovered[:3])
        )
        result.errors.append(msg)
        log.warning("Protocol compliance BLOCKED: %d uncovered items", len(uncovered))
    else:
        log.info("Protocol compliance PASS: all %d checklist items covered", len(protocol.judge.checklist))

    # SOFT warning: check dynamic gene injection
    from qualix.quality.gene_store import load_genes_for_phase

    base_dir = ctx.output_dir.parent if ctx.output_dir.parent.exists() else ctx.output_dir
    phase_genes = load_genes_for_phase(base_dir, ctx.phase_id, agent_role="judge")
    if not phase_genes:
        result.warnings.append(
            f"Protocol: zero dynamic genes for {ctx.phase_id} judge — "
            "experience accumulation not yet started for this Phase"
        )
```

- [ ] **Step 4: Register handler in handlers_finalize.py**

In `src/qualix/runtime/handlers_finalize.py`, in the registration block (around line 310), add:

```python
    from qualix.runtime.handlers_protocol import handle_protocol_compliance
    register_handler(
        "protocol_compliance",
        handle_protocol_compliance,
        stage="finalize",
        order=76,
        required=True,
    )
```

Order 76 places it after flow_integrity (order 75/76) and before progress_file (order 80).

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_handlers_protocol.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/qualix/runtime/handlers_protocol.py tests/test_handlers_protocol.py src/qualix/runtime/handlers_finalize.py
git commit -m "feat: add protocol_compliance finalize handler (HARD gate for checklist coverage)"
```

### Task 5: Integration Test + Documentation

**Files:**
- Create: `tests/test_protocol_integration.py`
- Modify: `ROADMAP.md`
- Modify: `docs/multi-agent-architecture.md`

- [ ] **Step 1: Write integration test**

```python
# tests/test_protocol_integration.py
"""Integration tests for Phase evaluation protocol system."""
from __future__ import annotations

import json


def test_protocol_renders_into_judge_prompt():
    """Protocol renders into text suitable for Judge prompt injection."""
    from qualix.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt

    for phase_id in ("Q01", "Q03", "Q04", "Q05", "Q06", "Q07"):
        proto = get_protocol(phase_id)
        assert proto is not None
        judge_text = render_protocol_for_prompt(proto.judge)
        critique_text = render_protocol_for_prompt(proto.critique)
        # Both render to non-empty text
        assert len(judge_text) > 100, f"{phase_id} judge text too short"
        assert len(critique_text) > 100, f"{phase_id} critique text too short"
        # Judge has checklist
        assert "检查清单" in judge_text
        # Critique has focus areas
        assert "重点检查方向" in critique_text


def test_gene_store_phase_filtering_end_to_end(tmp_path):
    """Genes saved with phase+role are correctly filtered on load."""
    from qualix.quality.gene_store import load_genes_for_phase, save_genes

    genes = [
        {"gene_id": "G-Q03-judge", "phase_id": "Q03", "agent_role": "judge",
         "error_type": "FN", "severity": "high", "target_pattern": "降级",
         "description": "缺少降级", "confidence": "high", "impact": "high",
         "source": {}, "match_count": 0, "last_matched_at": None},
        {"gene_id": "G-Q03-critique", "phase_id": "Q03", "agent_role": "critique",
         "error_type": "FN", "severity": "high", "target_pattern": "级联",
         "description": "级联失败", "confidence": "high", "impact": "high",
         "source": {}, "match_count": 0, "last_matched_at": None},
        {"gene_id": "G-Q07-judge", "phase_id": "Q07", "agent_role": "judge",
         "error_type": "FN", "severity": "high", "target_pattern": "注入",
         "description": "SQL注入", "confidence": "high", "impact": "high",
         "source": {}, "match_count": 0, "last_matched_at": None},
    ]
    save_genes(tmp_path, genes)

    # Q03 judge only
    q03j = load_genes_for_phase(tmp_path, "Q03", agent_role="judge")
    assert len(q03j) == 1
    assert q03j[0]["gene_id"] == "G-Q03-judge"

    # Q03 all roles
    q03_all = load_genes_for_phase(tmp_path, "Q03")
    assert len(q03_all) == 2

    # Q07 judge
    q07j = load_genes_for_phase(tmp_path, "Q07", agent_role="judge")
    assert len(q07j) == 1


def test_compose_rubric_plus_protocol():
    """compose_rubric + protocol render can be concatenated."""
    from qualix.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt
    from qualix.quality.judge_rubrics import compose_rubric

    rubric = compose_rubric("Q07")
    proto = get_protocol("Q07")
    assert proto is not None
    protocol_text = render_protocol_for_prompt(proto.judge)

    combined = protocol_text + "\n\n" + rubric
    # Both parts present
    assert "检查清单" in combined
    assert "source_citation" in combined
    assert "finding_validity" in combined
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_protocol_integration.py -v`
Expected: 3 passed

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -q`
Expected: All pass, zero regressions

- [ ] **Step 4: Update ROADMAP.md**

Add under the latest date block in section C:

```markdown
2026-04-25 新增（Phase Evaluation Protocol）：

- Phase-level 评估协议（`quality/evaluation_protocols.py`）— 7 Phase × 2 角色（Judge+Critique）专属检查清单 + 行为红线 + 领域词汇，替代通用人设标签
- Gene Store phase+role 过滤（`quality/gene_store.py`）— Gene 新增 agent_role 字段，注入时按 phase_id + agent_role 过滤，Q03 Judge 只看 Q03 Judge 的历史经验
- Protocol Compliance HARD gate（`runtime/handlers_protocol.py`）— finalize handler 检查 Judge 输出是否覆盖 checklist，未覆盖 → BLOCKED；dynamic 经验为空 → WARNING
- 研究驱动设计：基于 PRISM/EMNLP/Wharton 三篇独立研究结论，具体检查清单 >> 身份标签
```

- [ ] **Step 5: Update docs/multi-agent-architecture.md**

Add after the P1/P2/P3 block (added in previous plan):

```markdown
Phase 评估协议（Evaluation Protocol）：
- 每个 Phase 的 Judge/Critique 有专属检查清单 + 行为红线 + 领域词汇
- 静态层：人工维护的基础协议（低频更新）
- 动态层：Gene Store 按 phase_id + agent_role 过滤注入历史经验
- 门控：protocol_compliance handler (required, HARD gate)
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_protocol_integration.py ROADMAP.md docs/multi-agent-architecture.md
git commit -m "test+docs: integration tests and documentation for Phase evaluation protocols"
```
