"""Blast radius risk scoring: weighted 5-factor score → LOW/MEDIUM/HIGH/CRITICAL tier."""

from __future__ import annotations

from typing import Any

# --- Risk Scoring ---

_TIER_THRESHOLDS = {"LOW": 25, "MEDIUM": 55, "HIGH": 75}
_FACTOR_WEIGHTS = {
    "file_count": 0.25,
    "method_count": 0.20,
    "caller_count": 0.25,
    "test_count": 0.15,
    "blast_ratio": 0.15,
}
_FACTOR_CAPS = {
    "file_count": 10,
    "method_count": 15,
    "caller_count": 10,
    "test_count": 10,
    "blast_ratio": 3.0,
}


def compute_risk_score(radius: dict[str, Any]) -> dict[str, Any]:
    """Compute weighted risk score from blast radius data.

    Returns:
        {"score": int (0-100), "tier": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL", "factors": {...}}
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
