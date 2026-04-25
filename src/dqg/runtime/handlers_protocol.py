"""Protocol compliance finalize handler.

Checks that Judge output covers all static checklist items from the
Phase's evaluation protocol. Missing items → BLOCKED (HARD gate).
Zero dynamic genes → WARNING (SOFT).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dqg.log import get_logger

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult

log = get_logger(__name__)


def handle_protocol_compliance(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Check Judge output covers Phase protocol checklist."""
    from dqg.quality.evaluation_protocols import get_protocol

    protocol = get_protocol(ctx.phase_id)
    if not protocol:
        return

    # Load judge result
    from dqg.constants import PHASE_DIR_MAP
    from dqg.json_utils import load_json

    phase_dir = ctx.output_dir / ctx.project_id / PHASE_DIR_MAP.get(ctx.phase_id, ctx.phase_id)
    judge_path = phase_dir / "_judge_result.json"
    if not judge_path.exists():
        return

    judge_data = load_json(judge_path)
    if not judge_data:
        return

    # Collect all text from judge issues for matching
    judge_text = ""
    for issue in judge_data.get("issues", []):
        judge_text += " " + issue.get("description", "")
    judge_text = judge_text.lower()

    # Check each checklist item — extract keywords for fuzzy match
    uncovered = []
    for item in protocol.judge.checklist:
        # Extract Chinese keywords (2+ chars)
        keywords = re.findall(r"[\u4e00-\u9fff]{2,6}", item)
        # Also extract English keywords (3+ chars)
        keywords += re.findall(r"[a-zA-Z_]{3,}", item)
        if not keywords:
            continue
        # At least one keyword must appear in judge output
        if not any(kw.lower() in judge_text for kw in keywords):
            uncovered.append(item)

    if uncovered:
        msg = (
            f"BLOCKED: required handler protocol_compliance failed — "
            f"{len(uncovered)}/{len(protocol.judge.checklist)} checklist items uncovered: " + "; ".join(uncovered[:3])
        )
        result.errors.append(msg)
        log.warning("Protocol compliance BLOCKED: %d uncovered items", len(uncovered))
    else:
        log.info("Protocol compliance PASS: all %d checklist items covered", len(protocol.judge.checklist))

    # SOFT warning: check dynamic gene injection
    from dqg.quality.gene_store import load_genes_for_phase

    base_dir = ctx.output_dir.parent if ctx.output_dir.parent.exists() else ctx.output_dir
    phase_genes = load_genes_for_phase(base_dir, ctx.phase_id, agent_role="judge")
    if not phase_genes:
        result.warnings.append(
            f"Protocol: zero dynamic genes for {ctx.phase_id} judge — "
            "experience accumulation not yet started for this Phase"
        )
