#!/usr/bin/env python3
"""Validate the public phase failure patterns benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST: Final = ROOT / "benchmarks" / "phase-failure-patterns" / "manifest.json"
FAILURE_LIBRARY_ROOT: Final = ROOT / "regression" / "failure-library" / "cases"
REQUIRED_PATTERN_FIELDS: Final = {
    "pattern_id",
    "phase",
    "case_id",
    "case_path",
    "failure_pattern",
    "benchmark_focus",
    "expected_signal",
    "actual_miss",
    "why_it_matters",
    "triage",
    "source_safety",
}
REQUIRED_CASE_FIELDS: Final = {
    "case_id",
    "phase",
    "error_type",
    "severity",
    "title",
    "root_cause",
    "fix_target",
    "expected",
    "actual",
    "lesson",
    "case_category",
}
ALLOWED_SOURCE_SAFETY: Final = {"synthetic", "sanitized"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _missing_string_fields(data: dict[str, Any], required: set[str]) -> list[str]:
    missing = []
    for field in sorted(required):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    return missing


def _missing_case_fields(data: dict[str, Any]) -> list[str]:
    missing = []
    for field in sorted(REQUIRED_CASE_FIELDS):
        value = data.get(field)
        if value is None or value == "" or value == {}:
            missing.append(field)
    return missing


def validate_manifest(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    issues: list[str] = []

    patterns = manifest.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        issues.append("manifest must contain a non-empty patterns list")
        return {"manifest": str(manifest_path), "patterns": 0, "issues": issues}

    pattern_ids: set[str] = set()
    case_ids: set[str] = set()
    phases: set[str] = set()

    for index, pattern in enumerate(patterns, start=1):
        if not isinstance(pattern, dict):
            issues.append(f"patterns[{index}] must be an object")
            continue
        label = pattern.get("pattern_id") or f"patterns[{index}]"
        missing = _missing_string_fields(pattern, REQUIRED_PATTERN_FIELDS)
        if missing:
            issues.append(f"{label}: missing required pattern fields: {', '.join(missing)}")
            continue

        pattern_id = pattern["pattern_id"]
        case_id = pattern["case_id"]
        phase = pattern["phase"]
        source_safety = pattern["source_safety"]
        case_path = ROOT / pattern["case_path"]

        if pattern_id in pattern_ids:
            issues.append(f"{label}: duplicate pattern_id")
        pattern_ids.add(pattern_id)
        if case_id in case_ids:
            issues.append(f"{label}: duplicate case_id")
        case_ids.add(case_id)
        phases.add(phase)

        if source_safety not in ALLOWED_SOURCE_SAFETY:
            issues.append(f"{label}: source_safety must be one of {sorted(ALLOWED_SOURCE_SAFETY)}")
        try:
            case_path.relative_to(FAILURE_LIBRARY_ROOT)
        except ValueError:
            issues.append(f"{label}: case_path must point under regression/failure-library/cases")
        if not case_path.is_file():
            issues.append(f"{label}: linked case file does not exist: {pattern['case_path']}")
            continue

        case = load_json(case_path)
        missing_case = _missing_case_fields(case)
        if missing_case:
            issues.append(f"{label}: linked case is missing fields: {', '.join(missing_case)}")
        if case.get("case_id") != case_id:
            issues.append(f"{label}: case_id mismatch with linked case")
        if case.get("phase") != phase:
            issues.append(f"{label}: phase mismatch with linked case")
        tags = {str(tag).lower() for tag in case.get("tags", [])}
        if source_safety not in tags and source_safety not in str(case.get("title", "")).lower():
            issues.append(f"{label}: linked case must be tagged or titled as {source_safety}")

    return {
        "manifest": str(manifest_path),
        "patterns": len(patterns),
        "phases": sorted(phases),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate phase failure patterns benchmark manifest")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    result = validate_manifest(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
