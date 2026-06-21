"""Q06 EUT-scoped evidence locator context.

This module turns deterministic locator hits into read-only sidecar files that
can be injected into the Q06 evidence pack.  The sidecar is explicitly candidate
evidence only: it must never decide the Q06 semantic verdict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qualix.constants import STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json
from qualix.locator import RipgrepLocator
from qualix.schemas.evidence import EvidenceCitation

SIDECAR_JSON = "_evidence_citations.json"
SIDECAR_MD = "_evidence_citations.md"
SIDECAR_CONTRACT = "candidate_evidence_only"


def write_q06_evidence_citation_context(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
    *,
    limit_per_eut: int = 5,
) -> tuple[Path, Path] | None:
    """Write Q06 locator sidecars for Q05a EUTs.

    Returns ``(json_path, md_path)`` when Q06/Q05a artifacts are available.  The
    function is read-only with respect to code repositories; it only writes
    Qualix internal sidecars under the current Q06 output directory.
    """

    if not code_repos:
        return None

    q05a_def = PHASE_DEFS.get("Q05a")
    q06_def = PHASE_DEFS.get("Q06")
    if not q05a_def or not q06_def:
        return None

    q05a_json_name = STRUCTURED_JSON_MAP.get("Q05a")
    if not q05a_json_name:
        return None

    q05a_path = _phase_dir(output_dir, project_id, q05a_def) / q05a_json_name
    q05a_data = load_json(q05a_path)
    if not isinstance(q05a_data, dict):
        return None

    eut_items = _extract_eut_items(q05a_data)
    if not eut_items:
        return None

    q06_internal_dir = _internal_dir(output_dir, project_id, q06_def)
    q06_internal_dir.mkdir(parents=True, exist_ok=True)
    locator = RipgrepLocator()

    items: list[dict[str, Any]] = []
    for eut in eut_items:
        eut_id = str(eut.get("eut_id", "") or "").strip()
        if not eut_id:
            continue
        se_id = _eut_se_id(eut)
        query = _locator_query(eut)
        citations = locator.locate(
            query=query,
            code_repos=code_repos,
            phase="Q06",
            se_id=se_id,
            eut_id=eut_id,
            limit=limit_per_eut,
            context_lines=2,
        )
        items.append(
            {
                "eut_id": eut_id,
                "se_id": se_id,
                "query": query,
                "citation_count": len(citations),
                "citations": [citation.model_dump(mode="json") for citation in citations],
            }
        )

    if not items:
        return None

    payload = {
        "contract": SIDECAR_CONTRACT,
        "locator": RipgrepLocator.name,
        "phase": "Q06",
        "project_id": project_id,
        "code_repos": code_repos,
        "items": items,
        "notes": [
            "Locator citations are read-only candidate evidence.",
            "Q06 audit logic and validators still decide COVERED/PARTIAL/MISSING/WRONG_TARGET.",
            "Do not copy SE-level evidence across EUTs; every citation is scoped to one eut_id.",
        ],
    }

    json_path = q06_internal_dir / SIDECAR_JSON
    md_path = q06_internal_dir / SIDECAR_MD
    save_json(json_path, payload)
    md_path.write_text(render_q06_evidence_citation_context(payload), encoding="utf-8")
    return json_path, md_path


def render_q06_evidence_citation_context(payload: dict[str, Any]) -> str:
    """Render locator sidecar payload for the Q06 evidence pack."""

    lines = [
        "# Q06 Evidence Citation Candidates",
        "",
        f"- Contract: `{payload.get('contract', SIDECAR_CONTRACT)}`",
        f"- Locator: `{payload.get('locator', RipgrepLocator.name)}`",
        "- Verdict isolation: locator hits are candidate evidence only; Q06 audit logic owns status.",
        "- EUT scope: never reuse a citation for a different `eut_id`.",
        "",
        "## Candidate citations by EUT",
    ]

    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        eut_id = item.get("eut_id", "?")
        se_id = item.get("se_id", "")
        lines.extend(
            [
                "",
                f"### {eut_id}" + (f" / {se_id}" if se_id else ""),
                f"- Query: `{item.get('query', '')}`",
                f"- Candidate count: {item.get('citation_count', 0)}",
            ]
        )
        citations = item.get("citations", [])
        if not citations:
            lines.append("- No locator candidate found. This does not decide the Q06 verdict.")
            continue
        for citation in citations[:8]:
            if not isinstance(citation, dict):
                continue
            ref = _citation_reference(citation)
            kind = citation.get("kind", "")
            confidence = citation.get("confidence", "")
            reason = citation.get("reason", "")
            lines.append(f"- `{ref}` kind={kind} confidence={confidence} reason={reason}")
    return "\n".join(lines) + "\n"


def load_q06_evidence_citation_sidecar(phase_root: Path) -> dict[str, Any] | None:
    """Load the Q06 evidence citation sidecar if it exists and is valid JSON."""

    sidecar_path = phase_root / "_internal" / SIDECAR_JSON
    payload = load_json(sidecar_path)
    return payload if isinstance(payload, dict) else None


def validate_evidence_citations_for_items(data: dict[str, Any]) -> list[str]:
    """Validate EUT-scoped citation consistency in Q06 audit items.

    This deliberately checks only citation contract consistency.  It does not
    promote or demote Q06 statuses based on locator presence.
    """

    errors: list[str] = []
    for item in data.get("audit_items", []):
        if not isinstance(item, dict):
            continue
        eut_id = str(item.get("eut_id", "") or "")
        citations = item.get("evidence_citations") or []
        if not citations:
            continue
        if not isinstance(citations, list):
            errors.append(f"BLOCKED: [evidence_citations] {eut_id} evidence_citations 必须是数组")
            continue
        for idx, citation in enumerate(citations, start=1):
            if isinstance(citation, EvidenceCitation):
                citation_data = citation.model_dump(mode="json")
            elif isinstance(citation, dict):
                citation_data = citation
            else:
                errors.append(
                    f"BLOCKED: [evidence_citations] {eut_id} citation #{idx} 必须是对象，不能是 {type(citation).__name__}"
                )
                continue
            cited_eut = str(citation_data.get("eut_id", "") or "")
            if cited_eut != eut_id:
                errors.append(
                    f"BLOCKED: [evidence_citations] audit_item {eut_id} citation #{idx} "
                    f"绑定到 {cited_eut or '<empty>'}，违反 EUT-per-item 证据隔离"
                )
            if str(citation_data.get("contract", "") or "") == "verdict":
                errors.append(
                    f"BLOCKED: [evidence_citations] audit_item {eut_id} citation #{idx} "
                    "把 locator 结果标成 verdict，违反 candidate_evidence_only 合同"
                )
    return errors


def _extract_eut_items(q05a_data: dict[str, Any]) -> list[dict[str, Any]]:
    items = q05a_data.get("eut_items")
    if not items:
        items = q05a_data.get("audit_items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _eut_se_id(eut: dict[str, Any]) -> str:
    bound = str(eut.get("bound_item") or eut.get("bound_se") or "").strip()
    if bound.startswith("SE-"):
        return bound
    se_refs = eut.get("se_refs")
    if isinstance(se_refs, list):
        for ref in se_refs:
            ref_text = str(ref).strip()
            if ref_text.startswith("SE-"):
                return ref_text
    return ""


def _locator_query(eut: dict[str, Any]) -> str:
    parts = [
        eut.get("eut_id", ""),
        eut.get("bound_item", ""),
        eut.get("bound_se", ""),
        eut.get("given", ""),
        eut.get("when", ""),
        eut.get("then", ""),
        eut.get("repo", ""),
    ]
    se_refs = eut.get("se_refs")
    if isinstance(se_refs, list):
        parts.extend(str(ref) for ref in se_refs)
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _citation_reference(citation: dict[str, Any]) -> str:
    path = str(citation.get("path", "") or "")
    line_start = citation.get("line_start")
    line_end = citation.get("line_end")
    if not path or not line_start:
        return path or "<unknown>"
    if line_end and line_end != line_start:
        return f"{path}:{line_start}-{line_end}"
    return f"{path}:{line_start}"
