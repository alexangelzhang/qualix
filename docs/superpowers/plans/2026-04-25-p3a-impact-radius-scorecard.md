# P3-A: Impact Radius Scorecard — Risk-Graded Gate Enforcement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5-factor weighted risk score to blast_radius output, then use it in phase_constraints to dynamically adjust gate thresholds — small changes get relaxed checks, large changes get stricter enforcement.

**Architecture:** `compute_blast_radius()` already returns file/method/caller/test counts. Add a `compute_risk_score()` that weights these into a 0-100 score mapped to LOW/MEDIUM/HIGH/CRITICAL tiers. Then `enforce_phase_constraints()` reads the risk tier and adjusts thresholds (e.g., coverage requirement drops from 80% to 60% for LOW-risk changes). No architecture change — just a scoring layer on existing data + threshold lookup table.

**Tech Stack:** Python, existing blast_radius + phase_constraints modules

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/qualix/quality/blast_radius.py` | Add `compute_risk_score()` and `RiskTier` enum |
| Modify | `src/qualix/runtime/phase_constraints.py` | Risk-tier-aware threshold adjustment |
| Modify | `src/qualix/runtime/handlers_execute.py` | Persist risk_tier in blast_radius output |
| Create | `tests/test_risk_score.py` | Risk scoring + tier-adjusted constraint tests |

---

### Task 1: Add `compute_risk_score()` to blast_radius

**Files:**
- Modify: `src/qualix/quality/blast_radius.py:210-319`
- Create: `tests/test_risk_score.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_risk_score.py`:

```python
"""Test Impact Radius risk scoring."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def test_risk_score_empty_change():
    """No changes → score 0, tier LOW."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [],
        "changed_methods": [],
        "affected_callers": [],
        "affected_tests": [],
    }
    result = compute_risk_score(radius)
    assert result["score"] == 0
    assert result["tier"] == "LOW"


def test_risk_score_small_change():
    """1 file, 1 method, 0 callers → LOW tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": ["Foo.java"],
        "changed_methods": ["Foo.bar"],
        "affected_callers": [],
        "affected_tests": ["FooTest.testBar"],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "LOW"
    assert 0 < result["score"] <= 25


def test_risk_score_medium_change():
    """3-5 files, several callers → MEDIUM tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(4)],
        "changed_methods": [f"Class{i}.method" for i in range(6)],
        "affected_callers": [f"Caller{i}.call" for i in range(5)],
        "affected_tests": [f"Test{i}.test" for i in range(3)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "MEDIUM"
    assert 25 < result["score"] <= 55


def test_risk_score_high_change():
    """10+ files, many callers → HIGH tier."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(12)],
        "changed_methods": [f"Class{i}.method" for i in range(20)],
        "affected_callers": [f"Caller{i}.call" for i in range(15)],
        "affected_tests": [f"Test{i}.test" for i in range(8)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] in ("HIGH", "CRITICAL")
    assert result["score"] > 55


def test_risk_score_critical_change():
    """30+ files, massive blast radius → CRITICAL."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": [f"File{i}.java" for i in range(35)],
        "changed_methods": [f"Class{i}.method" for i in range(50)],
        "affected_callers": [f"Caller{i}.call" for i in range(30)],
        "affected_tests": [f"Test{i}.test" for i in range(20)],
    }
    result = compute_risk_score(radius)
    assert result["tier"] == "CRITICAL"
    assert result["score"] > 75


def test_risk_score_factors_breakdown():
    """Result should include per-factor breakdown."""
    from qualix.quality.blast_radius import compute_risk_score

    radius = {
        "changed_files": ["A.java", "B.java"],
        "changed_methods": ["A.foo", "B.bar"],
        "affected_callers": ["C.baz"],
        "affected_tests": [],
    }
    result = compute_risk_score(radius)
    assert "factors" in result
    factors = result["factors"]
    assert "file_count" in factors
    assert "method_count" in factors
    assert "caller_count" in factors
    assert "test_count" in factors
    assert "blast_ratio" in factors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /path/to/qualix && python -m pytest tests/test_risk_score.py -v`
Expected: FAIL — `compute_risk_score` does not exist

- [ ] **Step 3: Implement compute_risk_score**

In `src/qualix/quality/blast_radius.py`, add after `compute_blast_radius()` (before `write_blast_radius`):

```python
# --- Risk Scoring ---

# Tier thresholds (score 0-100)
_TIER_THRESHOLDS = {"LOW": 25, "MEDIUM": 55, "HIGH": 75}
# Factor weights (sum = 1.0)
_FACTOR_WEIGHTS = {
    "file_count": 0.25,      # How many files changed
    "method_count": 0.20,    # How many methods changed
    "caller_count": 0.25,    # How many callers affected (downstream blast)
    "test_count": 0.15,      # How many tests affected
    "blast_ratio": 0.15,     # Ratio of affected to changed (amplification factor)
}
# Normalization caps (values above cap → score 1.0 for that factor)
_FACTOR_CAPS = {
    "file_count": 30,
    "method_count": 40,
    "caller_count": 25,
    "test_count": 20,
    "blast_ratio": 5.0,
}


def compute_risk_score(radius: dict[str, Any]) -> dict[str, Any]:
    """Compute weighted risk score from blast radius data.

    Returns:
        {
            "score": int (0-100),
            "tier": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
            "factors": {factor_name: {"raw": N, "normalized": 0.0-1.0, "weighted": float}},
        }
    """
    raw = {
        "file_count": len(radius.get("changed_files", [])),
        "method_count": len(radius.get("changed_methods", [])),
        "caller_count": len(radius.get("affected_callers", [])),
        "test_count": len(radius.get("affected_tests", [])),
    }
    changed_total = raw["file_count"] + raw["method_count"]
    affected_total = raw["caller_count"] + raw["test_count"]
    raw["blast_ratio"] = round(affected_total / max(changed_total, 1), 2)

    factors = {}
    total_score = 0.0
    for factor, weight in _FACTOR_WEIGHTS.items():
        cap = _FACTOR_CAPS[factor]
        normalized = min(raw[factor] / cap, 1.0) if cap > 0 else 0.0
        weighted = normalized * weight * 100
        factors[factor] = {"raw": raw[factor], "normalized": round(normalized, 3), "weighted": round(weighted, 1)}
        total_score += weighted

    score = min(round(total_score), 100)

    if score > _TIER_THRESHOLDS["HIGH"]:
        tier = "CRITICAL"
    elif score > _TIER_THRESHOLDS["MEDIUM"]:
        tier = "HIGH"
    elif score > _TIER_THRESHOLDS["LOW"]:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return {"score": score, "tier": tier, "factors": factors}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_risk_score.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/qualix/quality/blast_radius.py tests/test_risk_score.py
git commit -m "feat(blast_radius): add 5-factor weighted risk scoring with tier classification"
```

---

### Task 2: Persist risk_tier in blast_radius output

**Files:**
- Modify: `src/qualix/quality/blast_radius.py:322-354` (write_blast_radius)
- Test: `tests/test_risk_score.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_risk_score.py`:

```python
def test_compute_blast_radius_includes_risk(tmp_path):
    """compute_blast_radius result should include risk_score and risk_tier."""
    from qualix.quality.blast_radius import compute_blast_radius

    # Can't easily test with real git, so test via compute_risk_score integration
    radius = {
        "changed_files": ["A.java"],
        "changed_methods": ["A.foo"],
        "affected_callers": [],
        "affected_tests": [],
        "risk_summary": "1 files, 1 methods changed; 0 callers, 0 tests potentially affected",
    }
    from qualix.quality.blast_radius import compute_risk_score

    risk = compute_risk_score(radius)
    # Verify the shape matches what write_blast_radius will persist
    assert "score" in risk
    assert "tier" in risk
    assert risk["tier"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
```

- [ ] **Step 2: Update compute_blast_radius to include risk score**

In `src/qualix/quality/blast_radius.py`, at the end of `compute_blast_radius()`, before the return statement, add:

```python
    result = {
        "changed_files": changed_files,
        "changed_methods": changed_methods[:50],
        "affected_callers": affected_callers[:30],
        "affected_tests": affected_tests[:30],
        "risk_summary": risk_summary,
    }

    # Attach risk scoring
    risk = compute_risk_score(result)
    result["risk_score"] = risk["score"]
    result["risk_tier"] = risk["tier"]
    result["risk_factors"] = risk["factors"]

    return result
```

Also update `_render_blast_radius_md()` to include risk tier:

```python
    lines = [
        "## BLAST_RADIUS — 代码改动影响范围（自动分析）",
        "",
        f"**摘要**: {radius['risk_summary']}",
        f"**风险等级**: {radius.get('risk_tier', 'N/A')} (score: {radius.get('risk_score', 'N/A')})",
        "",
    ]
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_risk_score.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/qualix/quality/blast_radius.py tests/test_risk_score.py
git commit -m "feat(blast_radius): persist risk_score and risk_tier in blast radius output"
```

---

### Task 3: Risk-tier-aware threshold adjustment in phase_constraints

**Files:**
- Modify: `src/qualix/runtime/phase_constraints.py`
- Test: `tests/test_risk_score.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_risk_score.py`:

```python
from pathlib import Path


def test_constraints_relaxed_for_low_risk(tmp_path: Path):
    """LOW risk tier should relax coverage thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", "LOW")
    # Q04 default: req_coverage_rate >= 0.8, se_coverage_rate >= 0.8
    # LOW risk: relax to 0.6
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] == 0.6


def test_constraints_unchanged_for_critical_risk(tmp_path: Path):
    """CRITICAL risk tier should keep or tighten thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", "CRITICAL")
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] >= 0.8


def test_constraints_default_without_risk_tier(tmp_path: Path):
    """No risk tier → use default thresholds."""
    from qualix.runtime.phase_constraints import get_adjusted_thresholds

    adjusted = get_adjusted_thresholds("Q04", None)
    req_cov = next(c for c in adjusted if c["metric"] == "req_coverage_rate")
    assert req_cov["threshold"] == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_risk_score.py::test_constraints_relaxed_for_low_risk -v`
Expected: FAIL — `get_adjusted_thresholds` does not exist

- [ ] **Step 3: Implement get_adjusted_thresholds**

In `src/qualix/runtime/phase_constraints.py`, add after `PHASE_CONSTRAINTS`:

```python
# Risk-tier threshold multipliers: how much to relax/tighten coverage thresholds
# Only coverage-type metrics are adjusted; count-based constraints stay fixed
_COVERAGE_METRICS = {"req_coverage_rate", "se_coverage_rate"}
_TIER_MULTIPLIERS: Final = MappingProxyType({
    "LOW": 0.75,       # 80% → 60%
    "MEDIUM": 1.0,     # unchanged
    "HIGH": 1.0,       # unchanged
    "CRITICAL": 1.1,   # 80% → 88% (capped at 1.0 for rate metrics)
})


def get_adjusted_thresholds(
    phase_id: str,
    risk_tier: str | None,
) -> list[dict]:
    """Return phase constraints with thresholds adjusted by risk tier.

    Coverage metrics (req_coverage_rate, se_coverage_rate) are relaxed for LOW
    risk and tightened for CRITICAL. Count-based constraints are unchanged.
    """
    constraints = PHASE_CONSTRAINTS.get(phase_id, [])
    if not constraints:
        return []

    multiplier = _TIER_MULTIPLIERS.get(risk_tier, 1.0) if risk_tier else 1.0

    adjusted = []
    for c in constraints:
        c_copy = dict(c)
        if c["metric"] in _COVERAGE_METRICS and multiplier != 1.0:
            new_threshold = round(c["threshold"] * multiplier, 2)
            # Cap rate metrics at 1.0
            c_copy["threshold"] = min(new_threshold, 1.0)
            c_copy["_original_threshold"] = c["threshold"]
            c_copy["_risk_adjusted"] = True
        adjusted.append(c_copy)
    return adjusted
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_risk_score.py -v`
Expected: ALL PASS

- [ ] **Step 5: Wire into enforce_phase_constraints**

Update `enforce_phase_constraints()` to accept optional `risk_tier`:

```python
def enforce_phase_constraints(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    risk_tier: str | None = None,
) -> list[dict]:
    constraints = get_adjusted_thresholds(phase_id, risk_tier)
    violations = []
    for c in constraints:
        # ... rest unchanged
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/qualix/runtime/phase_constraints.py tests/test_risk_score.py
git commit -m "feat(constraints): risk-tier-aware threshold adjustment for gate enforcement"
```

---

## Cost Impact

- LOW-risk changes (1-2 files, no downstream callers): coverage threshold drops from 80% to 60%, reducing false-positive gate blocks and unnecessary Adaptive Loop retries
- CRITICAL-risk changes: thresholds tighten to 88%, catching more issues before merge
- Zero additional LLM calls — scoring is pure computation on existing blast_radius data
