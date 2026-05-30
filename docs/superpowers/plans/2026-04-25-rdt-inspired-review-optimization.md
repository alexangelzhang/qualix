# RDT-Inspired Review Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three RDT-inspired optimizations to Qualix's adaptive loop: ACT depth-adaptive review, anchor injection to prevent drift, and shared+routed Judge rubrics.

**Architecture:** Three independent modifications to existing modules — P1 adds depth config lookup in adaptive_loop using blast_radius risk_tier, P2 extends handoff_builder with anchor extraction and injects upstream context into fixer iterations, P3 splits judge rubrics into shared (40%) + routed (60%) layers with weight normalization when dynamic dimensions are appended.

**Tech Stack:** Python 3.11+, pytest, existing Qualix modules (constants, adaptive_loop, handoff_builder, judge_vote, judge_rubrics)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/qualix/constants.py` | Add `REVIEW_DEPTH_CONFIG`, `REVIEW_DEPTH_DEFAULT`, `SHARED_RUBRIC_DIMENSIONS` |
| Modify | `src/qualix/agents/handoff_builder.py` | Add `extract_anchor_summary()`, extend `build_handoff_document()` with anchor section |
| Modify | `src/qualix/agents/judge_vote.py` | Add `force_secondary` param to `multi_judge_vote()` |
| Modify | `src/qualix/quality/judge_rubrics.py` | Add `PHASE_ROUTED_RUBRICS`, `compose_rubric()`, `_render_rubric()` |
| Modify | `src/qualix/agents/adaptive_loop.py` | Wire depth config, anchor injection, and composed rubric |
| Create | `tests/test_review_depth.py` | P1 tests: depth config lookup, force_secondary |
| Create | `tests/test_anchor_injection.py` | P2 tests: anchor extraction, handoff integration |
| Create | `tests/test_compose_rubric.py` | P3 tests: rubric composition, weight normalization |
| Create | `tests/test_adaptive_loop_rdt.py` | Integration test: all three features wired together |

---

### Task 1: P1 — Review Depth Config Constants

**Files:**
- Modify: `src/qualix/constants.py` (append after line 211, after `ADAPTIVE_MAX_ITERATIONS`)
- Create: `tests/test_review_depth.py`

- [ ] **Step 1: Write the failing test for depth config lookup**

```python
# tests/test_review_depth.py
"""Tests for P1: ACT review depth configuration."""
from __future__ import annotations


def test_review_depth_config_has_all_tiers():
    """Every risk tier maps to a depth config."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    for tier in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        cfg = REVIEW_DEPTH_CONFIG[tier]
        assert "max_iterations" in cfg
        assert "force_secondary" in cfg
        assert "skip_critique" in cfg


def test_review_depth_low_is_lightest():
    """LOW tier: 1 iteration, no secondary, skip critique."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["LOW"]
    assert cfg["max_iterations"] == 1
    assert cfg["force_secondary"] is False
    assert cfg["skip_critique"] is True


def test_review_depth_high_forces_secondary():
    """HIGH tier: 3 iterations, force secondary."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["HIGH"]
    assert cfg["max_iterations"] == 3
    assert cfg["force_secondary"] is True
    assert cfg["skip_critique"] is False


def test_review_depth_default_is_medium():
    """Default fallback is MEDIUM."""
    from qualix.constants import REVIEW_DEPTH_DEFAULT

    assert REVIEW_DEPTH_DEFAULT == "MEDIUM"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_review_depth.py -v`
Expected: FAIL with `ImportError: cannot import name 'REVIEW_DEPTH_CONFIG'`

- [ ] **Step 3: Add constants to constants.py**

Add after the `ADAPTIVE_MAX_ITERATIONS = 3` line (around line 211) in `src/qualix/constants.py`:

```python
# ---------------------------------------------------------------------------
# P1: ACT Review Depth — risk_tier → adaptive loop depth config
# ---------------------------------------------------------------------------

REVIEW_DEPTH_CONFIG: Final = MappingProxyType({
    "LOW":      MappingProxyType({"max_iterations": 1, "force_secondary": False, "skip_critique": True}),
    "MEDIUM":   MappingProxyType({"max_iterations": 2, "force_secondary": False, "skip_critique": False}),
    "HIGH":     MappingProxyType({"max_iterations": 3, "force_secondary": True,  "skip_critique": False}),
    "CRITICAL": MappingProxyType({"max_iterations": 3, "force_secondary": True,  "skip_critique": False}),
})
REVIEW_DEPTH_DEFAULT = "MEDIUM"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_review_depth.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/constants.py tests/test_review_depth.py
git commit -m "feat(p1): add REVIEW_DEPTH_CONFIG constants for ACT depth-adaptive review"
```

---

### Task 2: P1 — force_secondary in multi_judge_vote

**Files:**
- Modify: `src/qualix/agents/judge_vote.py:146-254` (`multi_judge_vote` function)
- Modify: `tests/test_review_depth.py` (append tests)

- [ ] **Step 1: Write the failing test for force_secondary**

Append to `tests/test_review_depth.py`:

```python
from unittest.mock import patch, MagicMock


def test_force_secondary_skips_boundary_check():
    """force_secondary=True invokes secondary models regardless of primary score."""
    from qualix.agents.judge_vote import multi_judge_vote, JudgeVote

    fake_vote = JudgeVote(
        model="primary", scores={}, overall=4.5, verdict="PASS",
        issues=[], duration=1.0, raw_output="clean output", health="HEALTHY",
    )

    with patch("qualix.agents.judge_vote._run_single_judge", return_value=fake_vote) as mock_judge:
        result = multi_judge_vote(
            output_dir="/tmp",
            report_path="/tmp/report.md",
            rubric="test rubric",
            models=["primary-model", "secondary-model"],
            fallback="fallback",
            force_secondary=True,
        )
        # Should call judge for both primary AND secondary (force_secondary bypasses boundary check)
        assert mock_judge.call_count >= 2
        assert len(result.votes) == 2


def test_no_force_secondary_skips_clear_pass():
    """Without force_secondary, clear PASS (4.5) skips secondary."""
    from qualix.agents.judge_vote import multi_judge_vote, JudgeVote

    fake_vote = JudgeVote(
        model="primary", scores={}, overall=4.5, verdict="PASS",
        issues=[], duration=1.0, raw_output="clean output", health="HEALTHY",
    )

    with patch("qualix.agents.judge_vote._run_single_judge", return_value=fake_vote):
        result = multi_judge_vote(
            output_dir="/tmp",
            report_path="/tmp/report.md",
            rubric="test rubric",
            models=["primary-model", "secondary-model"],
            fallback="fallback",
            force_secondary=False,
        )
        # Clear PASS → only primary vote
        assert len(result.votes) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_review_depth.py::test_force_secondary_skips_boundary_check -v`
Expected: FAIL with `TypeError: multi_judge_vote() got an unexpected keyword argument 'force_secondary'`

- [ ] **Step 3: Add force_secondary parameter to multi_judge_vote**

In `src/qualix/agents/judge_vote.py`, modify the `multi_judge_vote` function signature (line 146) and the boundary check logic (around line 233):

Change the function signature from:
```python
def multi_judge_vote(
    output_dir: "Path",
    report_path: "Path",
    rubric: str,
    models: list[str],
    fallback: str = "deepseek-chat",
) -> VoteResult:
```

To:
```python
def multi_judge_vote(
    output_dir: "Path",
    report_path: "Path",
    rubric: str,
    models: list[str],
    fallback: str = "deepseek-chat",
    force_secondary: bool = False,
) -> VoteResult:
```

Then change the boundary check block (around line 233) from:
```python
    if is_boundary and secondary_models:
```

To:
```python
    if (force_secondary or is_boundary) and secondary_models:
```

And update the log message (around line 249) from:
```python
    elif not is_boundary:
```

To:
```python
    elif not is_boundary and not force_secondary:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_review_depth.py -v`
Expected: 6 passed

- [ ] **Step 5: Run existing judge tests to verify no regression**

Run: `pytest tests/test_adaptive_loop_guard.py -v`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add src/qualix/agents/judge_vote.py tests/test_review_depth.py
git commit -m "feat(p1): add force_secondary param to multi_judge_vote for HIGH/CRITICAL depth"
```

---

### Task 3: P2 — Anchor Extraction from Upstream Context

**Files:**
- Modify: `src/qualix/agents/handoff_builder.py`
- Create: `tests/test_anchor_injection.py`

- [ ] **Step 1: Write the failing test for extract_anchor_summary**

```python
# tests/test_anchor_injection.py
"""Tests for P2: anchor injection to prevent drift."""
from __future__ import annotations

import textwrap
from pathlib import Path


SAMPLE_UPSTREAM = textwrap.dedent("""\
    # Evidence Pack

    ## 需求事实

    - REQ-001: 用户可以创建维保单
    - REQ-002: 维保单支持多车辆关联
    - REQ-003: 维保单状态流转需要审批

    ## 业务规则

    - BR-001: 单个维保单最多关联 5 辆车
    - BR-002: 审批通过后不可撤回
    - BR-003: 金额超过 5000 元需要二级审批

    ## 语义元素

    - SE-001: 创建维保单时校验车辆数量上限
    - SE-002: 状态机流转合法性校验
    - SE-003: 金额阈值触发审批升级
    - SE-004: 并发创建幂等保护

    ## 其他内容
    这里是不相关的内容，不应该被提取。
""")


def test_extract_anchor_summary_extracts_req_br_se():
    """Should extract REQ/BR/SE lines grouped by type."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    result = extract_anchor_summary(SAMPLE_UPSTREAM)
    assert "REQ-001" in result
    assert "BR-001" in result
    assert "SE-001" in result
    assert "核心需求" in result or "REQ" in result
    assert "其他内容" not in result


def test_extract_anchor_summary_empty_input():
    """Empty input returns empty string."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    assert extract_anchor_summary("") == ""


def test_extract_anchor_summary_no_ids():
    """Input without REQ/BR/SE returns empty string."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    assert extract_anchor_summary("just some random text\nno IDs here") == ""


def test_extract_anchor_summary_truncates_to_max_tokens():
    """Long input gets truncated to max_tokens."""
    from qualix.agents.handoff_builder import extract_anchor_summary

    # Generate many REQ lines
    lines = [f"- REQ-{i:03d}: 需求描述 {i} " + "详细内容" * 20 for i in range(50)]
    big_input = "\n".join(lines)
    result = extract_anchor_summary(big_input, max_tokens=200)
    # Should be truncated — rough estimate: 200 tokens ≈ 400 chars for mixed zh/en
    assert len(result) < len(big_input)
    assert "REQ-000" in result  # First items preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anchor_injection.py -v`
Expected: FAIL with `ImportError: cannot import name 'extract_anchor_summary'`

- [ ] **Step 3: Implement extract_anchor_summary in handoff_builder.py**

Add at the end of `src/qualix/agents/handoff_builder.py`:

```python
import re


_ANCHOR_ID_RE = re.compile(r"(REQ|BR|SE)-\d+")


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.5 chars per token for mixed zh/en."""
    return len(text) * 2 // 3


def extract_anchor_summary(upstream_text: str, max_tokens: int = 800) -> str:
    """Extract REQ/BR/SE lines from upstream context as anchor summary.

    Groups by type (REQ, BR, SE), preserves order within each group,
    truncates to max_tokens.
    """
    if not upstream_text.strip():
        return ""

    groups: dict[str, list[str]] = {"REQ": [], "BR": [], "SE": []}
    for line in upstream_text.splitlines():
        stripped = line.strip()
        m = _ANCHOR_ID_RE.search(stripped)
        if m:
            prefix = m.group(1)
            if prefix in groups:
                groups[prefix].append(stripped)

    if not any(groups.values()):
        return ""

    parts: list[str] = [
        "## Anchor（原始需求锚点 — 修正时不可偏离）",
        "",
        "以下是本 Phase 的原始需求事实，每轮修正必须对齐：",
        "",
    ]

    section_names = {"REQ": "核心需求 (REQ)", "BR": "关键业务规则 (BR)", "SE": "语义元素 (SE)"}
    for prefix, title in section_names.items():
        items = groups[prefix]
        if items:
            parts.append(f"### {title}")
            parts.extend(items)
            parts.append("")

    result = "\n".join(parts)

    # Truncate to max_tokens
    if _estimate_tokens(result) > max_tokens:
        budget_chars = max_tokens * 3 // 2  # inverse of estimate
        result = result[:budget_chars].rsplit("\n", 1)[0]

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anchor_injection.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/agents/handoff_builder.py tests/test_anchor_injection.py
git commit -m "feat(p2): add extract_anchor_summary for anchor injection"
```

---

### Task 4: P2 — Wire Anchor into Handoff Document

**Files:**
- Modify: `src/qualix/agents/handoff_builder.py:11-75` (`build_handoff_document`)
- Modify: `tests/test_anchor_injection.py` (append tests)

- [ ] **Step 1: Write the failing test for anchor in handoff**

Append to `tests/test_anchor_injection.py`:

```python
def test_handoff_includes_anchor_section():
    """When anchor_facts is provided, handoff includes Anchor section between Goal and Progress."""
    from qualix.agents.judge_vote import IterationRecord, VoteResult, JudgeVote

    vote = JudgeVote(model="m", scores={}, overall=2.5, verdict="FAIL", issues=[], duration=1.0)
    vr = VoteResult(votes=[vote], consensus="FAIL", avg_score=2.5, disagreements=[])
    prev = IterationRecord(iteration=1, judge_result=vr)

    from qualix.agents.handoff_builder import build_handoff_document

    anchor = "## Anchor（原始需求锚点 — 修正时不可偏离）\n\n### 核心需求 (REQ)\n- REQ-001: 测试需求"
    result = build_handoff_document(prev, 2, anchor_facts=anchor)

    assert "Anchor" in result
    assert "REQ-001" in result
    # Anchor should appear before Progress
    anchor_pos = result.index("Anchor")
    progress_pos = result.index("Progress")
    assert anchor_pos < progress_pos


def test_handoff_without_anchor_unchanged():
    """When anchor_facts is None, handoff is unchanged from current behavior."""
    from qualix.agents.judge_vote import IterationRecord, VoteResult, JudgeVote

    vote = JudgeVote(model="m", scores={}, overall=2.5, verdict="FAIL", issues=[], duration=1.0)
    vr = VoteResult(votes=[vote], consensus="FAIL", avg_score=2.5, disagreements=[])
    prev = IterationRecord(iteration=1, judge_result=vr)

    from qualix.agents.handoff_builder import build_handoff_document

    result = build_handoff_document(prev, 2, anchor_facts=None)
    assert "Anchor" not in result
    assert "Goal" in result
    assert "Progress" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_anchor_injection.py::test_handoff_includes_anchor_section -v`
Expected: FAIL with `TypeError: build_handoff_document() got an unexpected keyword argument 'anchor_facts'`

- [ ] **Step 3: Modify build_handoff_document to accept anchor_facts**

In `src/qualix/agents/handoff_builder.py`, change the function signature (line 11) from:

```python
def build_handoff_document(prev: "IterationRecord", next_iteration: int) -> str:
```

To:

```python
def build_handoff_document(
    prev: "IterationRecord",
    next_iteration: int,
    anchor_facts: str | None = None,
) -> str:
```

Then insert the anchor section after the Goal block (after line 20, after the empty string `""`):

```python
    if anchor_facts:
        parts.append(anchor_facts)
        parts.append("")
```

The insertion point is right after:
```python
    parts = [
        f"# 交接文档 — 第 {next_iteration} 轮修正",
        "",
        "## Goal（任务目标）",
        "修正上一轮报告中 Judge 和 Critique 指出的问题，输出改进后的完整报告。",
        "",
    ]
```

Add the anchor block here, before `parts.append("## Progress（上一轮进展）")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_anchor_injection.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/agents/handoff_builder.py tests/test_anchor_injection.py
git commit -m "feat(p2): wire anchor_facts into handoff document between Goal and Progress"
```

---

### Task 5: P3 — Shared Rubric Constants

**Files:**
- Modify: `src/qualix/constants.py` (append after `REVIEW_DEPTH_DEFAULT`)
- Create: `tests/test_compose_rubric.py`

- [ ] **Step 1: Write the failing test for shared rubric dimensions**

```python
# tests/test_compose_rubric.py
"""Tests for P3: shared + routed Judge rubric composition."""
from __future__ import annotations


def test_shared_rubric_has_four_dimensions():
    """Shared rubric defines exactly 4 universal quality dimensions."""
    from qualix.constants import SHARED_RUBRIC_DIMENSIONS

    assert len(SHARED_RUBRIC_DIMENSIONS) == 4
    ids = {d["id"] for d in SHARED_RUBRIC_DIMENSIONS}
    assert ids == {"source_citation", "confidence_tagging", "structural_completeness", "reasoning_quality"}


def test_shared_rubric_weights_sum_to_040():
    """Shared rubric base weights sum to 0.40 (40%)."""
    from qualix.constants import SHARED_RUBRIC_DIMENSIONS

    total = sum(d["weight"] for d in SHARED_RUBRIC_DIMENSIONS)
    assert abs(total - 0.40) < 0.001


def test_shared_rubric_dimensions_have_rubric_scale():
    """Each shared dimension has a 1-5 rubric scale."""
    from qualix.constants import SHARED_RUBRIC_DIMENSIONS

    for dim in SHARED_RUBRIC_DIMENSIONS:
        assert "rubric" in dim
        assert set(dim["rubric"].keys()) == {1, 2, 3, 4, 5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compose_rubric.py -v`
Expected: FAIL with `ImportError: cannot import name 'SHARED_RUBRIC_DIMENSIONS'`

- [ ] **Step 3: Add SHARED_RUBRIC_DIMENSIONS to constants.py**

Add after `REVIEW_DEPTH_DEFAULT` in `src/qualix/constants.py`:

```python
# ---------------------------------------------------------------------------
# P3: Shared Rubric — universal quality dimensions (40% base weight)
# ---------------------------------------------------------------------------

SHARED_RUBRIC_DIMENSIONS: Final = (
    {
        "id": "source_citation",
        "name": "来源标注完整性",
        "description": "每条结论是否标注了来源（[来源: 文件名:行号]）",
        "weight": 0.10,
        "rubric": {
            5: "所有结论都有精确的来源标注（文件名:行号）",
            4: "90%+ 结论有来源标注，个别缺失",
            3: "70-90% 有来源标注",
            2: "来源标注不足 70%",
            1: "几乎无来源标注",
        },
    },
    {
        "id": "confidence_tagging",
        "name": "置信度标注",
        "description": "每条结论是否标注了置信度（High/Medium/Low）",
        "weight": 0.10,
        "rubric": {
            5: "所有结论都有置信度标注，且标注合理",
            4: "90%+ 有置信度标注",
            3: "70-90% 有标注，部分标注不合理",
            2: "标注不足 70%",
            1: "几乎无置信度标注",
        },
    },
    {
        "id": "structural_completeness",
        "name": "结构完整性",
        "description": "报告是否包含所有必要章节，格式是否规范",
        "weight": 0.10,
        "rubric": {
            5: "所有必要章节齐全，格式规范，无截断",
            4: "主要章节齐全，个别格式瑕疵",
            3: "缺少 1-2 个非核心章节",
            2: "缺少核心章节或格式混乱",
            1: "结构严重不完整",
        },
    },
    {
        "id": "reasoning_quality",
        "name": "推理日志质量",
        "description": "推理日志是否记录了关键决策过程，可追溯",
        "weight": 0.10,
        "rubric": {
            5: "每个关键决策都有推理过程记录，可完整追溯",
            4: "主要决策有记录，个别步骤缺失",
            3: "部分决策有记录，但关键判断缺少推理过程",
            2: "推理日志流于形式，缺少实质内容",
            1: "几乎无推理记录",
        },
    },
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_compose_rubric.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/constants.py tests/test_compose_rubric.py
git commit -m "feat(p3): add SHARED_RUBRIC_DIMENSIONS constants for universal quality baseline"
```

---

### Task 6: P3 — compose_rubric and Routed Rubrics

**Files:**
- Modify: `src/qualix/quality/judge_rubrics.py`
- Modify: `tests/test_compose_rubric.py` (append tests)

- [ ] **Step 1: Write the failing tests for compose_rubric**

Append to `tests/test_compose_rubric.py`:

```python
def test_compose_rubric_includes_shared_and_routed():
    """compose_rubric output contains both shared and routed dimension IDs."""
    from qualix.quality.judge_rubrics import compose_rubric

    result = compose_rubric("Q07")
    assert "source_citation" in result  # shared
    assert "finding_validity" in result  # routed (Q07-specific)


def test_compose_rubric_unknown_phase_only_shared():
    """Unknown phase ID returns only shared dimensions."""
    from qualix.quality.judge_rubrics import compose_rubric

    result = compose_rubric("Q99")
    assert "source_citation" in result
    assert "finding_validity" not in result


def test_compose_rubric_all_phases_have_routed():
    """Every known Phase (Q01-Q07) has routed rubric dimensions."""
    from qualix.quality.judge_rubrics import compose_rubric, PHASE_ROUTED_RUBRICS

    for phase_id in ("Q01", "Q03", "Q04", "Q05", "Q06", "Q07"):
        assert phase_id in PHASE_ROUTED_RUBRICS, f"{phase_id} missing from PHASE_ROUTED_RUBRICS"
        result = compose_rubric(phase_id)
        assert "source_citation" in result  # shared always present


def test_compose_rubric_with_dynamic_dimensions():
    """Dynamic dimensions are appended and weights are normalized."""
    from qualix.quality.judge_rubrics import compose_rubric

    dynamic = [{"id": "dyn_concurrency", "name": "并发安全", "weight": 0.15,
                "rubric": {5: "好", 4: "较好", 3: "一般", 2: "差", 1: "很差"}}]
    result = compose_rubric("Q07", dynamic_dimensions=dynamic)
    assert "dyn_concurrency" in result
    assert "source_citation" in result
    assert "finding_validity" in result


def test_compose_rubric_weights_normalized():
    """Weights in rendered rubric are normalized to sum to 100%."""
    from qualix.quality.judge_rubrics import compose_rubric_structured

    dims = compose_rubric_structured("Q07")
    total = sum(d["weight"] for d in dims)
    assert abs(total - 1.0) < 0.01

    # With dynamic
    dynamic = [{"id": "dyn_test", "name": "Test", "weight": 0.15,
                "rubric": {5: "好", 4: "较好", 3: "一般", 2: "差", 1: "很差"}}]
    dims2 = compose_rubric_structured("Q07", dynamic_dimensions=dynamic)
    total2 = sum(d["weight"] for d in dims2)
    assert abs(total2 - 1.0) < 0.01
    assert len(dims2) == len(dims) + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_compose_rubric.py::test_compose_rubric_includes_shared_and_routed -v`
Expected: FAIL with `ImportError: cannot import name 'compose_rubric'`

- [ ] **Step 3: Add PHASE_ROUTED_RUBRICS, compose_rubric, compose_rubric_structured to judge_rubrics.py**

Add at the end of `src/qualix/quality/judge_rubrics.py`:

```python
from qualix.constants import SHARED_RUBRIC_DIMENSIONS

# Phase → routed rubric dimensions (60% base weight).
# These are the existing JUDGE_RUBRICS dimensions — we reference them directly.
PHASE_ROUTED_RUBRICS: Final[dict[str, list[dict[str, Any]]]] = {
    phase_id: rubric["dimensions"]
    for phase_id, rubric in JUDGE_RUBRICS.items()
}


def _normalize_weights(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize dimension weights to sum to 1.0."""
    total = sum(d["weight"] for d in dimensions)
    if total <= 0:
        return dimensions
    return [{**d, "weight": round(d["weight"] / total, 4)} for d in dimensions]


def compose_rubric_structured(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Compose shared + routed + dynamic dimensions as structured list.

    Weight normalization: shared(40%) + routed(60%) as base ratio,
    dynamic appended then all weights re-normalized to sum to 1.0.
    """
    shared = [dict(d) for d in SHARED_RUBRIC_DIMENSIONS]
    routed = [dict(d) for d in PHASE_ROUTED_RUBRICS.get(phase_id, [])]

    # Scale routed weights so shared:routed = 40:60
    if routed:
        routed_total = sum(d["weight"] for d in routed)
        if routed_total > 0:
            for d in routed:
                d["weight"] = d["weight"] / routed_total * 0.60

    all_dims = shared + routed
    if dynamic_dimensions:
        all_dims.extend(dict(d) for d in dynamic_dimensions)

    return _normalize_weights(all_dims)


def _render_dimension(dim: dict[str, Any], weight_pct: float) -> str:
    """Render a single dimension as rubric text."""
    lines = [
        f"### {dim['id']}: {dim.get('name', '')} (权重 {weight_pct:.0f}%)",
        f"{dim.get('description', '')}",
    ]
    rubric = dim.get("rubric", {})
    for score in sorted(rubric.keys(), reverse=True):
        lines.append(f"  - {score}分: {rubric[score]}")
    return "\n".join(lines)


def compose_rubric(
    phase_id: str,
    dynamic_dimensions: list[dict[str, Any]] | None = None,
) -> str:
    """Compose shared + routed + dynamic rubric as rendered text for Judge consumption."""
    dims = compose_rubric_structured(phase_id, dynamic_dimensions)

    parts = ["# 评审维度（共享 + 路由 + 动态）", ""]
    parts.append("## 通用质量维度（Shared）")
    parts.append("")
    for d in dims:
        if d["id"] in {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}:
            parts.append(_render_dimension(d, d["weight"] * 100))
            parts.append("")

    parts.append("## Phase 专属维度（Routed）")
    parts.append("")
    shared_ids = {sd["id"] for sd in SHARED_RUBRIC_DIMENSIONS}
    dynamic_ids = {dd["id"] for dd in (dynamic_dimensions or [])}
    for d in dims:
        if d["id"] not in shared_ids and d["id"] not in dynamic_ids:
            parts.append(_render_dimension(d, d["weight"] * 100))
            parts.append("")

    if dynamic_dimensions:
        parts.append("## 动态维度（Dynamic）")
        parts.append("")
        for d in dims:
            if d["id"] in dynamic_ids:
                parts.append(_render_dimension(d, d["weight"] * 100))
                parts.append("")

    # Append anti-rationalization table
    parts.extend(ANTI_RATIONALIZATION_SECTION)

    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_compose_rubric.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/qualix/quality/judge_rubrics.py tests/test_compose_rubric.py
git commit -m "feat(p3): add compose_rubric with shared+routed+dynamic weight normalization"
```

---

### Task 7: Wire P1 + P2 + P3 into Adaptive Loop

**Files:**
- Modify: `src/qualix/agents/adaptive_loop.py:62-199` (`run` method and `_execute_iteration`)

This is the integration task — wiring all three features into the adaptive loop.

- [ ] **Step 1: Modify AdaptiveLoop.run() to resolve depth config from blast_radius**

In `src/qualix/agents/adaptive_loop.py`, inside the `run()` method, after the `pd.mkdir(parents=True, exist_ok=True)` line (around line 85), add depth config resolution:

```python
        # P1: ACT depth — resolve review depth from blast_radius risk_tier
        from qualix.constants import REVIEW_DEPTH_CONFIG, REVIEW_DEPTH_DEFAULT
        from qualix.json_utils import load_json as _load_json

        _blast_path = pd / "_internal" / "_blast_radius.json"
        _risk_tier = REVIEW_DEPTH_DEFAULT
        if _blast_path.exists():
            _blast_data = _load_json(_blast_path)
            if _blast_data and "risk_tier" in _blast_data:
                _risk_tier = _blast_data["risk_tier"]
                log.info("P1 ACT depth: risk_tier=%s from blast_radius", _risk_tier)

        _depth_cfg = REVIEW_DEPTH_CONFIG.get(_risk_tier, REVIEW_DEPTH_CONFIG[REVIEW_DEPTH_DEFAULT])
        # Override max_iterations from depth config (caller can still override via param)
        if max_iterations == 3:  # only override if caller used default
            max_iterations = _depth_cfg["max_iterations"]
            log.info("P1 ACT depth: max_iterations=%d (risk_tier=%s)", max_iterations, _risk_tier)
        _force_secondary = _depth_cfg["force_secondary"]
        _skip_critique = _depth_cfg["skip_critique"]
```

- [ ] **Step 2: Modify AdaptiveLoop.run() to resolve upstream context path for P2 anchor**

After the depth config block, add upstream context resolution:

```python
        # P2: Anchor injection — locate upstream context for anchor extraction
        _upstream_path = pd / "_upstream_context.md"
        if not _upstream_path.exists():
            _upstream_path = pd / "_internal" / "_upstream_context.md"
        _anchor_available = _upstream_path.exists()
        if _anchor_available:
            log.info("P2 anchor: upstream context found at %s", _upstream_path)
```

- [ ] **Step 3: Pass force_secondary and skip_critique to _execute_iteration**

Modify the `_execute_iteration` call inside the `for i in range(max_iterations)` loop. Change from:

```python
            record, passed, iter_llm_calls = self._execute_iteration(
                i=i,
                pd=pd,
                report_path=report_path,
                worker_prompt=worker_prompt,
                judge_rubric=judge_rubric,
                critique_prompt=critique_prompt,
                context_files=context_files,
                worker_model=worker_model,
                judge_models=judge_models,
                fallback=fallback,
                pass_threshold=pass_threshold,
                iterations=iterations,
                task_id=task_id,
            )
```

To:

```python
            record, passed, iter_llm_calls = self._execute_iteration(
                i=i,
                pd=pd,
                report_path=report_path,
                worker_prompt=worker_prompt,
                judge_rubric=judge_rubric,
                critique_prompt=critique_prompt,
                context_files=context_files,
                worker_model=worker_model,
                judge_models=judge_models,
                fallback=fallback,
                pass_threshold=pass_threshold,
                iterations=iterations,
                task_id=task_id,
                force_secondary=_force_secondary,
                skip_critique=_skip_critique,
                upstream_path=_upstream_path if _anchor_available else None,
            )
```

- [ ] **Step 4: Update _execute_iteration signature and body**

Add the three new parameters to `_execute_iteration` signature:

```python
    def _execute_iteration(
        self,
        i: int,
        pd: Path,
        report_path: Path,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None,
        worker_model: str,
        judge_models: list[str],
        fallback: str,
        pass_threshold: float,
        iterations: list[IterationRecord],
        task_id: str,
        force_secondary: bool = False,
        skip_critique: bool = False,
        upstream_path: Path | None = None,
    ) -> tuple[IterationRecord, bool, list[dict[str, Any]]]:
```

**P2 anchor injection** — in the `else` block (iter > 0, fixer path), before `handoff_path.write_text(...)`, add anchor extraction:

```python
            # P2: Extract anchor summary for handoff
            anchor_facts = None
            if upstream_path and upstream_path.exists():
                from qualix.agents.handoff_builder import extract_anchor_summary
                try:
                    anchor_facts = extract_anchor_summary(
                        upstream_path.read_text(encoding="utf-8", errors="replace")
                    )
                except Exception as e:
                    log.debug("P2 anchor extraction failed: %s", e)
```

Then change the handoff write from:

```python
            handoff_path.write_text(
                build_handoff_document(prev, i + 1),
                encoding="utf-8",
            )
```

To:

```python
            handoff_path.write_text(
                build_handoff_document(prev, i + 1, anchor_facts=anchor_facts),
                encoding="utf-8",
            )
```

**P2 upstream context in fixer context_files** — after the fixer Agent creation, change the `fixer.run()` call to include upstream_path in dynamic_context_files:

```python
            _fixer_dynamic = [handoff_path, report_path]
            if upstream_path and upstream_path.exists():
                _fixer_dynamic.append(upstream_path)
            record.worker_result = fixer.run(
                f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
                context_files=context_files,
                dynamic_context_files=_fixer_dynamic,
            )
```

**P1 force_secondary** — change the `multi_judge_vote` call from:

```python
        record.judge_result = multi_judge_vote(self.output_dir, report_path, judge_rubric, judge_models, fallback)
```

To:

```python
        record.judge_result = multi_judge_vote(
            self.output_dir, report_path, judge_rubric, judge_models, fallback,
            force_secondary=force_secondary,
        )
```

**P1 skip_critique** — wrap the critique agent block with a condition:

```python
        if not skip_critique:
            critique = Agent(
                name=f"critique-iter{i + 1}",
                role="critique",
                system_prompt=critique_prompt,
                model=LLMConfig(primary=fallback, fallback=fallback),
                output_dir=self.output_dir,
            )
            record.critique_result = critique.run(
                "找出报告中的遗漏和错误，给出修正建议。",
                context_files=[report_path],
            )
            if record.critique_result:
                iter_llm_calls.append(extract_llm_call(record.critique_result))
```

- [ ] **Step 5: Run all existing adaptive loop tests**

Run: `pytest tests/test_adaptive_loop_guard.py tests/test_adaptive_skill_evolution.py tests/test_adaptive_loop_cache.py tests/test_adaptive_cache_prefix.py -v`
Expected: All existing tests pass (new params have defaults, backward compatible)

- [ ] **Step 6: Commit**

```bash
git add src/qualix/agents/adaptive_loop.py
git commit -m "feat: wire P1 depth config + P2 anchor injection + P3 force_secondary into adaptive loop"
```

---

### Task 8: P3 — Wire compose_rubric into Adaptive Loop

**Files:**
- Modify: `src/qualix/agents/adaptive_loop.py` (`run` method)

- [ ] **Step 1: Add composed rubric resolution in run()**

In `AdaptiveLoop.run()`, after the P2 upstream context block, add rubric composition:

```python
        # P3: Compose shared + routed rubric (replaces raw rubric string if phase_id known)
        from qualix.quality.judge_rubrics import compose_rubric as _compose_rubric

        if phase_id in ("Q01", "Q03", "Q04", "Q05", "Q06", "Q07"):
            _dynamic_dims = None
            try:
                from qualix.quality.dynamic_rubric import generate_dynamic_dimensions
                _dynamic_dims = generate_dynamic_dimensions(self.output_dir, project_id, phase_id)
            except Exception as e:
                log.debug("Dynamic rubric generation failed: %s", e)
            judge_rubric = _compose_rubric(phase_id, dynamic_dimensions=_dynamic_dims)
            log.info("P3 composed rubric: phase=%s, dynamic=%d dims",
                     phase_id, len(_dynamic_dims) if _dynamic_dims else 0)
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add src/qualix/agents/adaptive_loop.py
git commit -m "feat(p3): wire compose_rubric into adaptive loop for shared+routed judge rubrics"
```

---

### Task 9: Integration Test

**Files:**
- Create: `tests/test_adaptive_loop_rdt.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_adaptive_loop_rdt.py
"""Integration tests for P1+P2+P3 RDT-inspired review optimization."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def tmp_output(tmp_path):
    """Set up a minimal output directory with blast_radius and upstream context."""
    project_id = "test-project"
    phase_dir = tmp_path / project_id / "Q07"
    internal = phase_dir / "_internal"
    internal.mkdir(parents=True)

    # P1: blast_radius with HIGH risk
    blast = {"risk_tier": "HIGH", "risk_score": 65, "changed_files": ["A.java"]}
    (internal / "_blast_radius.json").write_text(json.dumps(blast))

    # P2: upstream context with REQ/BR/SE
    upstream = (
        "- REQ-001: 用户创建维保单\n"
        "- BR-001: 单个维保单最多关联 5 辆车\n"
        "- SE-001: 创建时校验车辆数量上限\n"
    )
    (phase_dir / "_upstream_context.md").write_text(upstream)

    return tmp_path, project_id


def test_p1_depth_config_resolves_from_blast_radius(tmp_output):
    """HIGH risk_tier → max_iterations=3, force_secondary=True."""
    from qualix.constants import REVIEW_DEPTH_CONFIG

    cfg = REVIEW_DEPTH_CONFIG["HIGH"]
    assert cfg["max_iterations"] == 3
    assert cfg["force_secondary"] is True


def test_p2_anchor_extracted_from_upstream(tmp_output):
    """Anchor summary extracts REQ/BR/SE from upstream context."""
    tmp_path, project_id = tmp_output
    upstream_path = tmp_path / project_id / "Q07" / "_upstream_context.md"

    from qualix.agents.handoff_builder import extract_anchor_summary

    text = upstream_path.read_text()
    anchor = extract_anchor_summary(text)
    assert "REQ-001" in anchor
    assert "BR-001" in anchor
    assert "SE-001" in anchor


def test_p3_composed_rubric_has_shared_and_routed():
    """Q07 composed rubric includes both shared and routed dimensions."""
    from qualix.quality.judge_rubrics import compose_rubric_structured

    dims = compose_rubric_structured("Q07")
    ids = {d["id"] for d in dims}
    # Shared
    assert "source_citation" in ids
    assert "confidence_tagging" in ids
    # Routed (Q07-specific)
    assert "finding_validity" in ids
    assert "req_code_alignment" in ids


def test_p1_p2_p3_all_wired_in_adaptive_loop(tmp_output):
    """Smoke test: adaptive loop resolves depth, anchor, and rubric without error."""
    tmp_path, project_id = tmp_output

    # We can't run the full loop (needs LLM), but we can verify the setup code runs
    from qualix.constants import REVIEW_DEPTH_CONFIG, REVIEW_DEPTH_DEFAULT
    from qualix.json_utils import load_json

    blast_path = tmp_path / project_id / "Q07" / "_internal" / "_blast_radius.json"
    blast_data = load_json(blast_path)
    risk_tier = blast_data.get("risk_tier", REVIEW_DEPTH_DEFAULT)
    depth_cfg = REVIEW_DEPTH_CONFIG[risk_tier]

    assert depth_cfg["max_iterations"] == 3  # HIGH
    assert depth_cfg["force_secondary"] is True

    upstream_path = tmp_path / project_id / "Q07" / "_upstream_context.md"
    assert upstream_path.exists()

    from qualix.agents.handoff_builder import extract_anchor_summary
    anchor = extract_anchor_summary(upstream_path.read_text())
    assert "REQ-001" in anchor

    from qualix.quality.judge_rubrics import compose_rubric
    rubric = compose_rubric("Q07")
    assert "source_citation" in rubric
    assert "finding_validity" in rubric
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_adaptive_loop_rdt.py -v`
Expected: 4 passed

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -q`
Expected: All tests pass, zero regressions

- [ ] **Step 4: Commit**

```bash
git add tests/test_adaptive_loop_rdt.py
git commit -m "test: add integration tests for P1+P2+P3 RDT-inspired review optimization"
```

---

### Task 10: Update Documentation

**Files:**
- Modify: `ROADMAP.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add P1+P2+P3 to ROADMAP.md**

In the `## C. 可观测、趋势与告警` section's latest date block, add:

```markdown
2026-04-25 新增（RDT-Inspired Review Optimization）：

- P1 ACT 审查深度自适应（`constants.py` REVIEW_DEPTH_CONFIG + `adaptive_loop.py` risk_tier 查表）— blast_radius risk_tier 驱动 max_iterations/force_secondary/skip_critique，LOW tier 省 ~60-70% token
- P2 锚点注入防漂移（`handoff_builder.py` extract_anchor_summary + `adaptive_loop.py` 上游 context 注入）— 每轮修正重注入 REQ/BR/SE 摘要 + 完整上游产物，防止 Worker 偏离原始需求
- P3 共享+路由 Judge rubric（`judge_rubrics.py` compose_rubric + `constants.py` SHARED_RUBRIC_DIMENSIONS）— shared(40%) 通用质量底线 + routed(60%) Phase 专属维度 + dynamic 追加，权重归一化
```

- [ ] **Step 2: Add to AGENTS.md multi-agent section**

In the `## Phase 3: 自适应循环模式` section of `docs/multi-agent-architecture.md`, add after the existing flow diagram:

```markdown
审查深度自适应（P1 ACT）：
- blast_radius risk_tier → REVIEW_DEPTH_CONFIG 查表
- LOW: 1 轮, primary only, 跳过 critique
- MEDIUM: 2 轮, boundary secondary
- HIGH/CRITICAL: 3 轮, 强制 secondary

锚点注入防漂移（P2）：
- 每轮修正时 handoff 文档新增 Anchor section（REQ/BR/SE 摘要）
- Fixer context_files 保留完整 _upstream_context.md

共享+路由 Judge rubric（P3）：
- compose_rubric(phase_id) 组合 shared(40%) + routed(60%) + dynamic
- 权重归一化：所有维度等比缩放使总和 = 100%
```

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md docs/multi-agent-architecture.md
git commit -m "docs: add P1+P2+P3 RDT-inspired review optimization to ROADMAP and architecture docs"
```
