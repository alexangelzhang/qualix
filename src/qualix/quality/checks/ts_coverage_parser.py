"""TypeScript coverage-summary.json parser for Jest/Vitest."""

from __future__ import annotations

import json
from pathlib import Path

from qualix.log import get_logger

log = get_logger(__name__)


def parse_coverage_summary(coverage_json_path: Path) -> dict | None:
    """Parse Jest/Vitest coverage-summary.json.

    Returns dict with keys ``lines_pct`` and ``branches_pct``, or ``None``
    if the file is not found or cannot be parsed.
    """
    if not coverage_json_path.exists():
        return None
    try:
        data = json.loads(coverage_json_path.read_text(encoding="utf-8"))
        total = data.get("total", {})
        lines_pct = total.get("lines", {}).get("pct")
        branches_pct = total.get("branches", {}).get("pct")
        if lines_pct is None or branches_pct is None:
            log.debug("coverage-summary.json missing pct fields: %s", coverage_json_path)
            return None
        return {"lines_pct": float(lines_pct), "branches_pct": float(branches_pct)}
    except Exception as exc:
        log.debug("Failed to parse coverage-summary.json at %s: %s", coverage_json_path, exc)
        return None
