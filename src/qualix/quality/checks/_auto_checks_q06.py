"""Q06 专属 auto_check 函数（auto_checks.py 内部实现模块，不直接被外部调用）."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json
from qualix.log import get_logger
from qualix.text_utils import STRUCTURED_JSON_MAP

log = get_logger(__name__)

_SOURCE_LINE_RE = re.compile(r":(\d+)$")


def _check_coverage_gate_consistency(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """Change 3: coverage_gate.line_coverage（LLM 自报）与 JaCoCo 实际结果交叉验证，升级为 BLOCKED.

    Summary 是派生字段——从数组重算，自报与实际不一致 → BLOCKED（原为 WARNING）。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return ["NOT_APPLICABLE: Q06 phase_def not found"]
    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return ["NOT_APPLICABLE: Q06 structured JSON not configured"]
    data = load_json(pd / json_file)
    if not data:
        return ["NOT_APPLICABLE: Q06 structured JSON not found"]

    gate = data.get("coverage_gate", {}) or {}
    reported_line = gate.get("line_coverage")
    if reported_line is None:
        return ["NOT_APPLICABLE: coverage_gate.line_coverage not set (LLM did not report a number)"]

    # 读 JaCoCo 实际结果（finalize 写入 _internal）
    for candidate in ["_incremental_coverage.json", "_coverage.json"]:
        cov = load_json(int_dir / candidate)
        if cov:
            actual_line = cov.get("line_coverage") or cov.get("overall_line_rate")
            if actual_line is not None:
                if actual_line <= 1.0:
                    actual_line *= 100
                diff = abs(float(reported_line) - float(actual_line))
                if diff > 15:
                    return [
                        f"BLOCKED: Q06 coverage_gate_mismatch — phase_c_structured.json 自报覆盖率"
                        f" {reported_line:.1f}% 与 JaCoCo 实际 {actual_line:.1f}% 偏差 {diff:.1f}%（阈值 15%）。"
                        "coverage_gate 是派生字段，必须从 JaCoCo 报告派生，禁止手动填写。"
                    ]
                return []
    return ["NOT_APPLICABLE: JaCoCo coverage data not yet available in _internal/"]


def _check_audit_items_count(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """G7: Q06 audit_items 数量应 ≥ Q05a eut_items 数量（允许 ≤10% 的漏审）.

    防止 LLM 只审计部分 EUT，跳过质量最差的测试使覆盖率数字虚高。
    """
    from qualix.constants import PHASE_DIR_MAP
    from qualix.core.state_machine import phase_dir as _pd

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    q06_count = len(data.get("audit_items", []))

    # 读 Q05a EUT 数量
    q05_json = STRUCTURED_JSON_MAP.get("Q05a")
    q05_dir = PHASE_DIR_MAP.get("Q05a")
    if not q05_json or not q05_dir:
        return []
    phase_b = load_json(output_dir / project_id / q05_dir / q05_json)
    if not phase_b:
        return []
    q05_count = len(phase_b.get("eut_items", []))
    if q05_count == 0:
        return []

    if q06_count < q05_count * 0.9:
        return [
            f"FAIL: Q06 audit_items_insufficient — Q06 审计了 {q06_count} 条 EUT，"
            f"但 Q05a 共有 {q05_count} 条（覆盖率 {q06_count * 100 // q05_count}%，要求 ≥90%）。"
            "Q06 必须覆盖 Q05a 绝大多数 EUT，不能跳过质量差的测试。"
        ]
    return []


def _check_evidence_line_reality(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """G5: audit_items.evidence 行号内容验证（对标 Q01-1 SE.source 验证）.

    COVERED 条目的 evidence = "[file:line]" → 验证该行附近确有断言关键词。
    """
    from qualix.core.state_machine import phase_dir as _pd

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    # 读 code_repos
    from qualix.core.state_machine import internal_dir as _internal_dir

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs = load_json(int_dir / "_inputs.json") or {}
    code_repos: list[str] = inputs.get("code_repos") or []
    if not code_repos and inputs.get("code_repo"):
        code_repos = [inputs["code_repo"]]

    _ASSERT_KW = re.compile(r"\bassert\w+\s*\(|\bverify\s*\(", re.IGNORECASE)
    _EV_RE = re.compile(r"\[?([^:\[\]]+\.java):(\d+)\]?")

    suspicious: list[str] = []
    for item in data.get("audit_items", []):
        if not isinstance(item, dict) or str(item.get("status", "")).upper() != "COVERED":
            continue
        evidence = str(item.get("evidence", "") or "")
        m = _EV_RE.search(evidence)
        if not m:
            continue
        fname, lineno = m.group(1), int(m.group(2))

        found = False
        for repo_str in code_repos:
            repo = Path(repo_str).expanduser().resolve()
            # 在 src/test/ 下递归找该文件
            for candidate in repo.rglob(f"*{Path(fname).name}"):
                try:
                    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                    ctx = "\n".join(lines[max(0, lineno - 4) : lineno + 3])
                    if _ASSERT_KW.search(ctx):
                        found = True
                except OSError:
                    pass
                if found:
                    break
            if found:
                break

        if not found:
            eut_id = item.get("eut_id", "?")
            suspicious.append(f"{eut_id}({fname}:{lineno})")

    if suspicious:
        return [
            f"WARNING: Q06 evidence_line_no_assert — {len(suspicious)} 个 COVERED 条目的"
            f" evidence 行号附近无断言关键词，疑似虚报来源: {', '.join(suspicious[:4])}。"
        ]
    return []


def _check_findings_severity_distribution(validated: Any, phase_id: str) -> list[str]:
    """G8: Q06 findings.severity 分布合理性检查.

    防止 LLM 系统性低报问题（全标 LOW）让审计看起来"几乎无问题"。
    """
    if phase_id != "Q06":
        return []
    findings = getattr(validated, "findings", [])
    if len(findings) < 3:
        return []

    severities = [str(f.severity).upper() for f in findings if hasattr(f, "severity")]
    if not severities:
        return []

    low_count = sum(1 for s in severities if s in ("LOW", "INFO", "MINOR"))
    if low_count / len(severities) >= 0.9:
        return [
            f"WARNING: Q06 severity_all_low — {low_count}/{len(severities)} 个 finding 均为 LOW/INFO，"
            "疑似系统性低报问题严重性。如果存在 MISSING/WRONG_TARGET 条目，至少应有 MEDIUM 以上 finding。"
        ]
    return []
