"""dqg-run spec：以代码/registry 为单一事实源输出 Phase 规范（JSON）."""

from __future__ import annotations

from typing import Any

from dqg.commands.cli_json import cli_envelope, print_cli_json
from dqg.constants import REPORT_MAP, SKILL_FILE_MAP, STRUCTURED_JSON_MAP
from dqg.core.phase_registry import PHASE_DEFS
from dqg.runtime.phase_contract import load_phase_contract
from dqg.runtime.phase_contract_builder import build_phase_contract
from dqg.schemas.schema_export import json_schema_for_phase


def _phase_def_public(phase_id: str) -> dict[str, Any] | None:
    raw = PHASE_DEFS.get(phase_id)
    if not raw:
        return None
    # MappingProxyType / 只读映射 → 可 JSON 序列化的浅拷贝
    return {
        "phase_id": phase_id,
        "name": raw.get("name"),
        "dir_suffix": raw.get("dir_suffix"),
        "skill": raw.get("skill"),
        "recommended_model": raw.get("recommended_model"),
        "reasoning_profile": dict(raw["reasoning_profile"]) if raw.get("reasoning_profile") is not None else {},
        "depends_on": list(raw.get("depends_on", [])),
        "parallel_with": list(raw.get("parallel_with", [])),
        "skippable": bool(raw.get("skippable", False)),
        "skip_condition": raw.get("skip_condition"),
        "required_inputs": list(raw.get("required_inputs", [])),
        "optional_inputs": list(raw.get("optional_inputs", [])),
        "deliverables": list(raw.get("deliverables", [])),
        "approve_checklist": list(raw.get("approve_checklist", [])),
        "required_report_sections": list(raw.get("required_report_sections", [])),
    }


def _parse_skill_frontmatter(skill_path: str) -> dict | None:
    """解析 SKILL.md 的 YAML frontmatter，返回 metadata 段（applies_to/hard_checks/evidence 等）."""
    from pathlib import Path

    p = Path(skill_path)
    if not p.exists():
        return None
    try:
        content = p.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        end = content.find("\n---", 3)
        if end == -1:
            return None
        frontmatter_text = content[3:end].strip()

        result: dict = {}
        current_key = ""
        in_metadata = False
        for line in frontmatter_text.splitlines():
            stripped = line.strip()
            if stripped == "metadata:":
                in_metadata = True
                continue
            if in_metadata:
                if line and not line[0].isspace():
                    in_metadata = False
                    continue
                if stripped.startswith("- "):
                    value = stripped[2:].strip().strip("'\"")
                    if current_key:
                        result.setdefault(current_key, []).append(value)
                elif ":" in stripped:
                    k, _, v = stripped.partition(":")
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    current_key = k
                    if v:
                        if v.startswith("[") and v.endswith("]"):
                            result[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",")]
                        else:
                            result[k] = v
        return result if result else None
    except Exception:
        return None


def cmd_spec(args: Any, output_dir: Any) -> int:
    """输出单 Phase 规范：registry + contract + JSON Schema（纯只读，不写盘）。"""
    from pathlib import Path

    output_dir = Path(output_dir)
    phase_id = getattr(args, "phase", None) or getattr(args, "spec_phase", None)
    proj = args.project_id

    if not phase_id:
        print_cli_json(
            cli_envelope(
                command="spec",
                project_id=proj,
                success=False,
                exit_code=2,
                errors=["missing --phase"],
            )
        )
        return 2

    phase_def = _phase_def_public(phase_id)
    if not phase_def:
        print_cli_json(
            cli_envelope(
                command="spec",
                project_id=proj,
                success=False,
                exit_code=1,
                phase_id=phase_id,
                errors=[f"unknown phase: {phase_id}"],
            )
        )
        return 1

    structured_name = STRUCTURED_JSON_MAP.get(phase_id)
    report_name = REPORT_MAP.get(phase_id)
    skill_path = SKILL_FILE_MAP.get(phase_id)

    # 纯只读构造 contract（build_phase_contract 不写盘）。
    # 若项目已在 execute 流程中落过盘，优先读取以保留运行时信息。
    contract = load_phase_contract(output_dir, proj, phase_id)
    if contract is None:
        contract = build_phase_contract(output_dir, proj, phase_id)

    schema = json_schema_for_phase(phase_id)

    skill_metadata = _parse_skill_frontmatter(skill_path) if skill_path else None

    print_cli_json(
        cli_envelope(
            command="spec",
            project_id=proj,
            success=True,
            exit_code=0,
            phase_id=phase_id,
            extra={
                "structured_json_filename": structured_name,
                "report_filename": report_name,
                "skill_file": skill_path,
                "skill_metadata": skill_metadata,
                "phase_registry": phase_def,
                "json_schema": schema,
                "contract": contract,
            },
        )
    )
    return 0
