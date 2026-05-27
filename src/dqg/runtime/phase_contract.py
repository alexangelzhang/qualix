"""Phase Contract：执行合同.

在 execute 时自动生成 phase_contract.json，包含：
- done_definition：从 approve_checklist 提取的完成标准
- verification_targets：从 SE 列表提取的验证目标
- evidence_refs：输入证据清单
- hard_checks：finalize gate 列表

Judge 评审时读取 contract 逐条打分，而非自由文本评审。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger
from dqg.runtime.phase_constraints import enforce_phase_constraints

__all__ = [
    "check_report_structure",
    "enforce_phase_constraints",
    "extract_priority_ids",
    "generate_phase_contract",
    "load_phase_contract",
    "render_contract_for_judge",
]

log = get_logger(__name__)


def generate_phase_contract(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """生成 Phase 执行合同.

    Returns:
        contract 文件路径
    """
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    # 1. Done Definition（从 approve_checklist 提取）
    done_definition = phase_def.get("approve_checklist", [])

    # 2. Verification Targets（从上游 Phase A 的 SE 列表提取）
    verification_targets = _extract_verification_targets(output_dir, project_id, phase_id)

    # 3. Evidence Refs（输入证据清单）
    evidence_refs = _collect_evidence_refs(output_dir, project_id, phase_id)

    # 4. Hard Checks（finalize gate 列表）
    hard_checks = _get_hard_checks(phase_id)

    contract = {
        "project_id": project_id,
        "phase_id": phase_id,
        "done_definition": done_definition,
        "verification_targets": verification_targets,
        "evidence_refs": evidence_refs,
        "hard_checks": hard_checks,
        "status": "active",
    }

    contract_path = int_dir / "_phase_contract.json"
    save_json(contract_path, contract)

    # 额外生成人类可读的 schema 字段指南，让 AI 在写 JSON 前就能看到必填字段
    schema_guide = _render_schema_fields_guide(phase_id, hard_checks)
    if schema_guide:
        schema_path = int_dir / "_schema_fields.md"
        schema_path.write_text(schema_guide, encoding="utf-8")

    log.info(
        "Phase contract: %s — %d done criteria, %d verification targets, %d hard checks",
        phase_id,
        len(done_definition),
        len(verification_targets),
        len(hard_checks),
    )
    return contract_path


def load_phase_contract(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """加载 Phase 执行合同."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    contract_path = output_dir / project_id / dir_suffix / "_internal" / "_phase_contract.json"
    return load_json(contract_path)


def render_contract_for_judge(contract: dict[str, Any]) -> str:
    """渲染 contract 为 Judge 可消费的 prompt 片段.

    来源权重（从高到低）：
    1. Profile Baseline（人类定义，不可篡改，Judge 必须全部验证）
    2. Bug Case Library（历史教训，不可篡改，Judge 必须全部验证）
    3. Phase A SE（Worker 生成，可质疑，Judge 应尽力验证但允许标注"证据不足"）
    """
    lines = [
        "## PHASE_CONTRACT — 执行合同（Judge 必须逐条验证）",
        "",
        "### Done Definition（完成标准）",
    ]
    for i, item in enumerate(contract.get("done_definition", []), 1):
        lines.append(f"{i}. [ ] {item}")

    lines.append("")
    lines.append("### Verification Targets（验证目标）")
    lines.append("")
    lines.append("> **权重说明**：Profile Baseline ≥ Bug Case Library > Phase Q01 SE")
    lines.append("> - 🔴 HARD（不可篡改）：Profile Baseline + Bug Case Library，Judge 必须全部给出 PASS/FAIL")
    lines.append("> - 🟡 SOFT（可质疑）：Phase Q01 SE，Judge 应验证，证据不足时标注 INSUFFICIENT_EVIDENCE")

    se_targets = [vt for vt in contract.get("verification_targets", []) if vt.get("source") == "phase_a"]
    profile_targets = [vt for vt in contract.get("verification_targets", []) if vt.get("source") == "profile"]
    regression_targets = [vt for vt in contract.get("verification_targets", []) if vt.get("source") == "regression"]
    legacy_targets = [vt for vt in contract.get("verification_targets", []) if "source" not in vt]

    if profile_targets:
        lines.append("")
        lines.append("#### 🔴 [HARD] Profile Baseline（人类定义，不可篡改）")
        for vt in profile_targets:
            lines.append(f"- {vt['se_id']}: {vt['description']}")

    if regression_targets:
        lines.append("")
        lines.append("#### 🔴 [HARD] Bug Case Library（历史教训，不可篡改）")
        for vt in regression_targets:
            lines.append(f"- {vt.get('se_id', '?')}: {vt.get('description', '')}")

    if se_targets or legacy_targets:
        lines.append("")
        lines.append("#### 🟡 [SOFT] Phase A SE（Worker 生成，可质疑）")
        for vt in se_targets or legacy_targets:
            lines.append(f"- {vt.get('se_id', '?')}: {vt.get('description', '')}")

    lines.append("")
    lines.append("### Hard Checks（硬性门禁）")
    for hc in contract.get("hard_checks", []):
        lines.append(f"- [{hc['level']}] {hc['name']}")

    lines.append("")
    lines.append("> Judge 规则：")
    lines.append("> 1. 对每条 Done Definition 给出 PASS/FAIL，不能笼统评价")
    lines.append("> 2. 对所有 🔴 HARD 目标必须给出 PASS/FAIL")
    lines.append("> 3. 对 🟡 SOFT 目标，证据不足时可标注 INSUFFICIENT_EVIDENCE（不算 FAIL）")
    lines.append("> 4. 不得以「整体质量尚可」为由跳过任何 HARD 目标的验证")
    lines.append("> 5. **FAIL 判定必须附带 evidence_lines**：至少一条 `{file}:{line}` 引用 + 功能性影响说明")
    lines.append(">    缺少具体代码行号的 FAIL 将被降级为 INSUFFICIENT_EVIDENCE")
    lines.append("> 6. 风格/命名/注释问题不得标记为 FAIL/BLOCKER，应标记为 SUGGESTION 或 INFO")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------


def _extract_verification_targets(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, str]]:
    """从多个来源提取验证目标，防止 Worker 自设标准.

    来源：
    1. Phase A 的 SE 列表（Worker 生成，可能偏软）
    2. Profile baseline 硬性约束（人类定义，不可篡改）
    3. Bug case library 回归检查点（历史教训，不可篡改）
    """
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    targets: list[dict[str, str]] = []

    # 来源 1：Phase A SE 列表
    phase_a_dir = PHASE_DIR_MAP.get("Q01", "phaseA")
    phase_a_json = STRUCTURED_JSON_MAP.get("Q01", "phase_a_structured.json")
    phase_a_path = output_dir / project_id / phase_a_dir / phase_a_json

    data = load_json(phase_a_path)
    if data:
        for se in data.get("semantic_expectations", []):
            targets.append(
                {
                    "se_id": se.get("se_id", se.get("id", "")),
                    "description": se.get("description", ""),
                    "mapping_target": se.get("mapping_target", ""),
                    "source": "phase_a",
                }
            )

    # 来源 2：Profile baseline 硬性约束（人类定义，Worker 无法影响）
    targets.extend(_extract_profile_constraints(output_dir, project_id, phase_id))

    # 来源 3：Bug case library 回归检查点（历史教训，Worker 无法影响）
    targets.extend(_extract_regression_checkpoints(phase_id))

    return targets


def _extract_profile_constraints(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, str]]:
    """从 profile baseline 提取硬性约束作为验证目标."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    profile_path = output_dir / project_id / dir_suffix / "_internal" / "_profile_context.md"

    if not profile_path.exists():
        return []

    try:
        content = profile_path.read_text(encoding="utf-8")
    except OSError:
        return []

    # 从 profile 中提取风险目录条目作为硬性检查点
    constraints: list[dict[str, str]] = []
    in_risk_section = False
    for line in content.split("\n"):
        stripped = line.strip()
        if "风险" in stripped and stripped.startswith("#"):
            in_risk_section = True
            continue
        if in_risk_section and stripped.startswith("#"):
            in_risk_section = False
            continue
        if in_risk_section and stripped.startswith("- "):
            risk_item = stripped[2:].strip()
            if risk_item and len(risk_item) > 5:
                constraints.append(
                    {
                        "se_id": f"PROFILE-RISK-{len(constraints) + 1:03d}",
                        "description": risk_item,
                        "mapping_target": "profile_baseline",
                        "source": "profile",
                    }
                )

    return constraints


def _extract_regression_checkpoints(phase_id: str) -> list[dict[str, str]]:
    """从 bug case library 提取回归检查点.

    选取 severity=critical 且 status=fixed 的 cases 作为回归检查点，
    确保已修复的关键问题不会在新的 Phase 执行中复现。
    """
    from dqg.tracking.bug_cases import load_cases_by_phase

    cases = load_cases_by_phase(phase_id, exclude_holdout=True)
    checkpoints: list[dict[str, str]] = []

    for c in cases:
        if c.get("severity") != "critical":
            continue
        if c.get("status") not in ("fixed", "open"):
            continue
        lesson = c.get("lesson", "").strip()
        if not lesson:
            continue
        checkpoints.append(
            {
                "se_id": f"REGRESSION-{c.get('case_id', 'unknown')}",
                "description": f"[回归检查] {lesson[:120]}",
                "mapping_target": c.get("case_id", ""),
                "source": "regression",
            }
        )

    return checkpoints


def _collect_evidence_refs(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[dict[str, str]]:
    """收集输入证据清单."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id, {})
    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    int_dir = output_dir / project_id / dir_suffix / "_internal"

    refs: list[dict[str, str]] = []

    # 上游上下文
    upstream = int_dir / "_upstream_context.md"
    if upstream.exists():
        refs.append({"type": "upstream_context", "path": str(upstream)})

    # Profile manifest
    profile = int_dir / "_profile_context.md"
    if profile.exists():
        refs.append({"type": "profile_manifest", "path": str(profile)})

    # Bug cases
    bug_cases = int_dir / "_bug_cases.md"
    if bug_cases.exists():
        refs.append({"type": "bug_cases", "path": str(bug_cases)})

    # Data patterns
    data_patterns = int_dir / "_data_patterns.md"
    if data_patterns.exists():
        refs.append({"type": "data_patterns", "path": str(data_patterns)})

    # SE→Code mapping
    se_code = int_dir / "_se_code_mapping.md"
    if se_code.exists():
        refs.append({"type": "se_code_mapping", "path": str(se_code)})

    return refs


def _get_hard_checks(phase_id: str) -> list[dict[str, str]]:
    """获取 Phase 的硬性门禁列表."""
    common = [
        {"name": "推理日志存在", "level": "BLOCKED"},
        {"name": "产物数量不回退", "level": "REGRESSION"},
    ]

    phase_specific: dict[str, list[dict[str, str]]] = {
        "Q05": [{"name": "编译验证通过", "level": "BLOCKED"}],
        "Q05b": [{"name": "编译验证通过", "level": "BLOCKED"}],
        "Q06": [{"name": "覆盖率 >= 80%", "level": "BLOCKED"}],
    }

    return common + phase_specific.get(phase_id, [])


def extract_priority_ids(targets: list[dict[str, str]] | None) -> set[str]:
    """Extract flat set of requirement IDs from verification_targets.

    Collects se_id and mapping_target from each target.
    Used by evidence renderer to prioritize relevant quotes.
    """
    if not targets:
        return set()
    ids: set[str] = set()
    for t in targets:
        se_id = t.get("se_id", "")
        if se_id:
            ids.add(se_id)
        mapping = t.get("mapping_target", "")
        if mapping and mapping != "profile_baseline":
            ids.add(mapping)
    return ids


def check_report_structure(report_content: str, phase: str) -> dict[str, Any]:
    """Check report against required_report_sections from phase_registry.

    Uses fuzzy matching: section header must contain canonical name or any alias.

    Returns:
        {"passed": bool, "missing": [str], "found": [str]}
    """
    from dqg.runtime.phase_constraints import check_report_structure as _check

    return _check(report_content, phase)


def _render_schema_fields_guide(phase_id: str, hard_checks: list[dict]) -> str | None:
    """从 Pydantic schema 生成人类可读的字段约束指南，写入 _schema_fields.md。

    解决"先写产物再查 spec"问题：execute 阶段自动生成此文件，bootstrap context
    引用它，让 AI 在写 structured JSON 之前就能看到必填字段和枚举约束。
    """
    try:
        from dqg.schemas.schema_export import json_schema_for_phase
        from dqg.text_utils import STRUCTURED_JSON_MAP
    except ImportError:
        return None

    schema = json_schema_for_phase(phase_id)
    if not schema:
        return None

    filename = STRUCTURED_JSON_MAP.get(phase_id, "structured.json")
    lines: list[str] = [
        f"# 结构化产物字段约束 — {phase_id}",
        "",
        f"> 产物文件：`{filename}`  |  自动从 Pydantic schema 生成，以代码为准",
        "",
    ]

    defs = schema.get("$defs", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    # 必填字段
    if required:
        lines += ["## ✅ 必填字段", ""]
        for field in sorted(required):
            info = props.get(field, {})
            ftype = info.get("type", "object")
            desc = info.get("description", "")
            pattern = info.get("pattern", "")
            line = f"- **`{field}`** (`{ftype}`)"
            if desc:
                line += f" — {desc}"
            if pattern:
                line += f"  ⚠️ 格式约束：`{pattern}`"
            lines.append(line)
        lines.append("")

    # 可选字段（含枚举/格式约束）
    constrained = {
        k: v for k, v in props.items() if k not in required and ("pattern" in v or "enum" in v or "$ref" in v)
    }
    if constrained:
        lines += ["## ⚙️ 可选字段（含枚举/格式约束）", ""]
        for field, info in constrained.items():
            ftype = info.get("type", "")
            pattern = info.get("pattern", "")
            enum = info.get("enum", [])
            ref = info.get("$ref", "")
            line = f"- `{field}`"
            if pattern:
                line += f" — 格式：`{pattern}`"
            if enum:
                line += f" — 枚举：{enum}"
            if ref:
                ref_name = ref.split("/")[-1]
                ref_schema = defs.get(ref_name, {})
                ref_req = ref_schema.get("required", [])
                if ref_req:
                    line += f" → `{ref_name}` 必填子字段：{ref_req}"
            lines.append(line)
        lines.append("")

    # $defs 中的子模型必填字段
    if defs:
        lines += ["## 📦 子模型必填字段", ""]
        for model_name, model_schema in defs.items():
            sub_required = model_schema.get("required", [])
            if sub_required:
                lines.append(f"**`{model_name}`**：必填 {sub_required}")
                # 枚举约束
                for field in sub_required:
                    field_info = model_schema.get("properties", {}).get(field, {})
                    pattern = field_info.get("pattern", "")
                    if pattern:
                        lines.append(f"  - `{field}` 格式：`{pattern}`")
        lines.append("")

    # 硬性门禁
    if hard_checks:
        lines += ["## 🚫 硬性门禁（违反则 finalize BLOCKED）", ""]
        for check in hard_checks:
            lines.append(f"- [{check.get('level', '?')}] {check.get('name', '')}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compat re-export: DSL constraints moved to phase_constraints.py
# ---------------------------------------------------------------------------
