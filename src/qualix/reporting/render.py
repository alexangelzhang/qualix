"""JSON→Markdown 渲染器：从结构化产物自动生成人类可读报告.

Worker 输出以结构化 JSON 为主（Pydantic schema 校验），
md 报告从 JSON 自动渲染，确保 md 和 JSON 永远一致。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Final


def render_phase_a(data: dict[str, Any]) -> str:
    """渲染 Phase A 需求结构化报告."""
    lines = [f"# Phase A 需求结构化报告 — {data.get('project_id', '')}"]

    # REQ/BR
    reqs = data.get("requirements", [])
    if reqs:
        lines.append("\n## 需求清单")
        for r in reqs:
            rid = r.get("req_id", "")
            desc = r.get("description", "")
            parent = r.get("parent_id", "")
            prefix = f"  ↳ {rid}" if parent else f"- **{rid}**"
            lines.append(f"{prefix}: {desc}")
            if r.get("acceptance_criteria"):
                lines.append(f"  - 验收标准: {r['acceptance_criteria']}")

    # SE
    ses = data.get("semantic_expectations", [])
    if ses:
        lines.append("\n## 关键语义 (SE)")
        for se in ses:
            lines.append(f"- **{se.get('se_id', '')}**: {se.get('description', '')}")

    # GAP
    gaps = data.get("gaps", [])
    if gaps:
        lines.append("\n## 缺口 (GAP)")
        for g in gaps:
            related = ", ".join(g.get("related_ids", []))
            lines.append(f"- **{g.get('gap_id', '')}**: {g.get('description', '')}")
            if related:
                lines.append(f"  - 关联: {related}")
            if g.get("required_clarification"):
                lines.append(f"  - 需澄清: {g['required_clarification']}")

    # OPEN
    opens = data.get("open_items", [])
    if opens:
        lines.append("\n## 待确认 (OPEN)")
        for o in opens:
            lines.append(f"- **{o.get('open_id', '')}**: {o.get('question', '')}")

    # Conclusion
    conclusion = data.get("conclusion", "")
    if conclusion:
        lines.append(f"\n## 结论\n\n{conclusion}")

    return "\n".join(lines)


def render_phase_a6(data: dict[str, Any]) -> str:
    """渲染 Phase A.6 技术方案质量评审报告."""
    lines = [f"# Phase A.6 技术方案质量评审 — {data.get('project_id', '')}"]

    issues = data.get("issues", [])
    if issues:
        lines.append("\n## 质量问题")
        for issue in issues:
            severity = issue.get("severity", "")
            lines.append(f"- **[{severity}] {issue.get('issue_id', '')}**: {issue.get('description', '')}")
            if issue.get("suggestion"):
                lines.append(f"  - 建议: {issue['suggestion']}")

    fms = data.get("failure_modes", [])
    if fms:
        lines.append("\n## Failure Mode 分析")
        lines.append("| 业务路径 | 失败场景 | 异常处理 | 状态 |")
        lines.append("|---------|---------|---------|------|")
        for fm in fms:
            has_eh = "✓" if fm.get("has_exception_handling") else "✗"
            lines.append(
                f"| {fm.get('business_path', '')} | {fm.get('failure_scenario', '')} "
                f"| {has_eh} | {fm.get('status', '')} |"
            )

    conclusion = data.get("conclusion", "")
    if conclusion:
        lines.append(f"\n## 结论\n\n{conclusion}")

    return "\n".join(lines)


def render_phase_b(data: dict[str, Any]) -> str:
    """渲染 Phase B EUT 矩阵."""
    lines = [f"# Phase B EUT 矩阵 — {data.get('project_id', '')}"]

    euts = data.get("eut_items", [])
    if euts:
        lines.append("\n| EUT ID | 关联 SE | 路径类型 | Given | When | Then | 风险等级 |")
        lines.append("|--------|--------|---------|-------|------|------|---------|")
        for e in euts:
            lines.append(
                f"| {e.get('eut_id', '')} | {e.get('bound_se', '')} | {e.get('route_type', '')} "
                f"| {e.get('given', '')} | {e.get('when', '')} | {e.get('then', '')} "
                f"| {e.get('risk_tier', '')} |"
            )

    return "\n".join(lines)


def render_phase_d(data: dict[str, Any]) -> str:
    """渲染 Phase D 代码评审报告."""
    lines = [f"# Phase D 代码评审报告 — {data.get('project_id', '')}"]

    findings = data.get("findings", [])
    if findings:
        lines.append("\n## 评审发现")
        for f in findings:
            severity = f.get("severity", "")
            lines.append(f"- **[{severity}] {f.get('finding_id', '')}**: {f.get('description', '')}")
            if f.get("file_path"):
                lines.append(f"  - 文件: {f['file_path']}")
            if f.get("related_req"):
                lines.append(f"  - 关联需求: {f['related_req']}")
            if f.get("suggestion"):
                lines.append(f"  - 建议: {f['suggestion']}")

    conclusion = data.get("conclusion", "")
    if conclusion:
        lines.append(f"\n## 结论\n\n{conclusion}")

    return "\n".join(lines)


# Phase → 渲染函数
_RENDERERS: Final = MappingProxyType(
    {
        "Q01": render_phase_a,
        "Q03": render_phase_a6,
        "Q05a": render_phase_b,
        "Q07": render_phase_d,
    }
)


def render_report(phase_id: str, data: dict[str, Any]) -> str | None:
    """根据 Phase ID 渲染 md 报告. 无对应渲染器时返回 None."""
    renderer = _RENDERERS.get(phase_id)
    if not renderer:
        return None
    return renderer(data)
