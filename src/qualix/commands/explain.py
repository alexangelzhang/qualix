"""qualix-run <project> explain <se-id> — show evidence chain for a SE."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_STATUS_ICON = {
    "COVERED": "✓",
    "PARTIAL": "~",
    "MISSING": "●",
    "WRONG_TARGET": "✗",
    "NOT_AUDITED": "?",
}

_STATUS_ORDER = ["MISSING", "WRONG_TARGET", "PARTIAL", "COVERED", "NOT_AUDITED"]


def cmd_explain(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
    from qualix.json_utils import load_json

    project_id: str = args.project_id
    se_id: str = args.se_id.upper()
    json_mode = cli_json_mode(args)

    phase_base = output_dir / project_id
    q01_data = load_json(phase_base / "Q01" / "phase_a_structured.json") or {}
    q05a_data = load_json(phase_base / "Q05a" / "phase_b_structured.json") or {}
    q06_data = load_json(phase_base / "Q06" / "phase_c_structured.json") or {}

    # ── locate SE ────────────────────────────────────────────────────────────
    se_list: list[dict[str, Any]] = q01_data.get("semantic_expectations", [])
    se = next((s for s in se_list if s.get("se_id", "").upper() == se_id), None)

    if se is None:
        available = [s.get("se_id", "") for s in se_list]
        msg = f"{se_id} not found in Q01 output. Available: {', '.join(available) or 'none'}"
        if json_mode:
            print_cli_json(cli_envelope(
                command="explain", project_id=project_id,
                success=False, exit_code=1, errors=[msg],
            ))
        else:
            print(f"  ERROR: {msg}", file=sys.stderr)
        return 1

    # ── find EUTs bound to this SE ───────────────────────────────────────────
    eut_list: list[dict[str, Any]] = q05a_data.get("eut_items", [])
    bound_euts = [
        e for e in eut_list
        if (e.get("bound_se") or e.get("bound_item", "")).upper() == se_id
    ]

    # ── find Q06 audit items for those EUTs ──────────────────────────────────
    audit_list: list[dict[str, Any]] = q06_data.get("audit_items", [])
    eut_ids = {e.get("eut_id", "").upper() for e in bound_euts}

    def _matches_eut(item: dict[str, Any]) -> bool:
        raw = item.get("eut_id", "")
        return any(eid.strip().upper() in eut_ids for eid in raw.split(","))

    audit_items = [a for a in audit_list if _matches_eut(a)]

    if json_mode:
        print_cli_json(cli_envelope(
            command="explain", project_id=project_id,
            success=True, exit_code=0,
            extra={
                "se": se,
                "euts": bound_euts,
                "audit_items": audit_items,
            },
        ))
        return 0

    # ── text output ──────────────────────────────────────────────────────────
    bar = "═" * 60
    thin = "─" * 60

    print(f"\n{bar}")
    print(f"  {se_id}  {se.get('description', '')}")
    source = se.get("source", "")
    bound = ", ".join(se.get("bound_reqs", []))
    conf = se.get("confidence", "")
    meta_parts = [p for p in [f"Source: {source}", f"Bound: {bound}", f"Confidence: {conf}"] if p.split(": ", 1)[1]]
    if meta_parts:
        print(f"  {' | '.join(meta_parts)}")
    print(bar)

    if not bound_euts:
        print("\n  No EUTs found for this SE in Q05a output.")
        print("  Run Q05a to generate test targets for this SE.")
    else:
        print(f"\nEUT Coverage ({len(bound_euts)} item{'s' if len(bound_euts) != 1 else ''}):")
        audit_by_eut: dict[str, dict[str, Any]] = {}
        for a in audit_items:
            for eid in a.get("eut_id", "").split(","):
                audit_by_eut[eid.strip().upper()] = a

        for eut in bound_euts:
            eid = eut.get("eut_id", "")
            audit = audit_by_eut.get(eid.upper())
            status = audit.get("status", "NOT_AUDITED") if audit else "NOT_AUDITED"
            icon = _STATUS_ICON.get(status, "?")
            desc = eut.get("description") or eut.get("scenario", "") or ""
            print(f"  {icon}  {eid:<10} [{status:<12}]  {desc[:60]}")

    non_covered = [a for a in audit_items if a.get("status") not in ("COVERED",)]
    if non_covered:
        print(f"\n{thin}")
        print("Q06 Findings:")
        for a in sorted(non_covered, key=lambda x: _STATUS_ORDER.index(x.get("status", "NOT_AUDITED"))):
            status = a.get("status", "")
            icon = _STATUS_ICON.get(status, "?")
            eid = a.get("eut_id", "")
            finding = a.get("finding") or a.get("summary", "")
            rec = a.get("recommendation", "")
            print(f"  {icon} {status:<14} {eid}")
            if finding:
                print(f"    {finding[:80]}")
            if rec:
                print(f"    → {rec[:80]}")

    print()
    return 0
