"""Q01 evidence and ambiguity sidecars."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json
from qualix.text_utils import STRUCTURED_JSON_MAP

_AMBIGUITY_WORDS = ("待确认", "不明确", "缺少", "未定义", "未说明", "不清楚", "确认", "clarify", "unknown")


def build_q01_analysis_sidecars(output_dir: Path, project_id: str, phase_id: str = "Q01") -> list[str]:
    if phase_id != "Q01":
        return []
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _phase_dir(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    structured = load_json(pd / json_file)
    if not isinstance(structured, dict):
        return []

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_ingest_manifest(pd)
    evidence_pack = _build_evidence_pack(structured, manifest, pd)
    ambiguity_queue = _build_ambiguity_queue(structured)
    save_json(int_dir / "_q01_evidence_pack.json", evidence_pack)
    save_json(int_dir / "_q01_ambiguity_queue.json", ambiguity_queue)
    return _check_sidecars(evidence_pack, ambiguity_queue)


def _load_ingest_manifest(phase_dir: Path) -> dict[str, Any]:
    for candidate in [phase_dir / "ingest" / "manifest.json", phase_dir / "ingest" / "ingest" / "manifest.json"]:
        data = load_json(candidate)
        if isinstance(data, dict):
            return data
    return {}


def _build_evidence_pack(structured: dict[str, Any], manifest: dict[str, Any], phase_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat()
    source_map_path = str(manifest.get("source_map_path", "") or "")
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "project_id": structured.get("project_id", ""),
        "ingest": {
            "provider_id": manifest.get("provider_id", ""),
            "source": manifest.get("source", ""),
            "plain_text_path": manifest.get("plain_text_path", str(phase_dir / "plain_text.txt")),
            "source_map_path": source_map_path,
            "asset_count": len(manifest.get("assets", []) or []),
        },
        "items": _evidence_items(structured),
    }


def _evidence_items(structured: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for req in structured.get("requirements", []) or []:
        if not isinstance(req, dict):
            continue
        items.append(
            {
                "item_id": req.get("req_id", ""),
                "kind": "requirement",
                "description": req.get("description", ""),
                "source": req.get("source", ""),
                "bound_ids": [req.get("parent_id", "")] if req.get("parent_id") else [],
            }
        )
    for se in structured.get("semantic_expectations", []) or []:
        if not isinstance(se, dict):
            continue
        items.append(
            {
                "item_id": se.get("se_id", ""),
                "kind": "semantic_expectation",
                "description": se.get("description", ""),
                "source": se.get("source", ""),
                "bound_ids": se.get("bound_reqs", []) or [],
                "verification": se.get("verification", ""),
            }
        )
    return items


def _build_ambiguity_queue(structured: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for gap in structured.get("gaps", []) or []:
        if isinstance(gap, dict):
            items.append(
                {
                    "item_id": gap.get("gap_id", ""),
                    "kind": "gap",
                    "related_ids": gap.get("related_ids", []) or [],
                    "question": gap.get("required_clarification", "") or gap.get("description", ""),
                    "risk_level": gap.get("risk_level", ""),
                    "decision_owner": gap.get("decision_owner", ""),
                    "source": gap.get("source", ""),
                }
            )
    for open_item in structured.get("open_items", []) or []:
        if isinstance(open_item, dict):
            items.append(
                {
                    "item_id": open_item.get("open_id", ""),
                    "kind": "open_item",
                    "related_ids": open_item.get("related_ids", []) or [],
                    "question": open_item.get("question", ""),
                    "risk_level": open_item.get("risk_level", ""),
                    "decision_owner": open_item.get("decision_owner", ""),
                    "source": open_item.get("source", ""),
                }
            )
    for item in _evidence_items(structured):
        text = f"{item.get('description', '')} {item.get('verification', '')}"
        if any(word.lower() in text.lower() for word in _AMBIGUITY_WORDS):
            items.append(
                {
                    "item_id": item.get("item_id", ""),
                    "kind": "suspected_ambiguity",
                    "related_ids": item.get("bound_ids", []) or [],
                    "question": f"请确认 {item.get('item_id', '')} 的模糊表述是否已澄清",
                    "risk_level": "P2",
                    "decision_owner": "",
                    "source": item.get("source", ""),
                }
            )
    return {"schema_version": 1, "generated_at": datetime.now().isoformat(), "items": items}


def _check_sidecars(evidence_pack: dict[str, Any], ambiguity_queue: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not evidence_pack.get("items"):
        errors.append("WARNING: Q01 evidence_pack_empty — 未生成 REQ/BR/SE 证据索引")
    for item in ambiguity_queue.get("items", []) or []:
        if not item.get("question"):
            errors.append(f"WARNING: Q01 ambiguity_question_empty — {item.get('item_id', '?')} 缺少待澄清问题")
    return errors
