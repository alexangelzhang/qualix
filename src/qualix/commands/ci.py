"""qualix-run <pid> ci-gate — CI/CD 质量门禁命令.

读取已有的 _gate_verdict.json，输出结构化结果并决定 exit code。
零额外 LLM 调用，速度极快（纯文件读取）。

用法：
  qualix-run mrs ci-gate Q06                    # 标准输出 + HARD block 时 exit 1
  qualix-run mrs ci-gate Q06 --fail-on soft     # SOFT 也算 fail
  qualix-run mrs ci-gate --all-phases           # 检查所有 Phase
  qualix-run mrs ci-gate Q06 --pr-comment       # 输出 GitHub PR Comment Markdown
  qualix-run mrs ci-gate Q06 --json             # JSON 输出（供 CI 脚本解析）

与 qualix-run finalize 的区别：
  finalize = 执行所有检查并生成 verdict（有 LLM 调用）
  ci-gate  = 读取已有 verdict 并裁决（零 LLM，速度快，适合 CI 重复调用）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

_PASS_ICON = "✅"
_FAIL_ICON = "❌"
_WARN_ICON = "⚠️"
_SKIP_ICON = "—"


def _load_verdict(output_dir: Path, project_id: str, phase_id: str) -> dict[str, Any] | None:
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_id)
    verdict_path = output_dir / project_id / dir_suffix / "_gate_verdict.json"
    if not verdict_path.exists():
        return None
    return load_json(verdict_path) or None


def _collect_all_verdicts(output_dir: Path, project_id: str) -> dict[str, dict[str, Any]]:
    from qualix.constants import PHASE_DIR_MAP

    results: dict[str, dict[str, Any]] = {}
    for phase_id, dir_suffix in PHASE_DIR_MAP.items():
        verdict_path = output_dir / project_id / dir_suffix / "_gate_verdict.json"
        if verdict_path.exists():
            from qualix.json_utils import load_json
            data = load_json(verdict_path)
            if data:
                results[phase_id] = data
    return results


def _determine_exit_code(verdict: dict[str, Any], fail_on: str) -> int:
    if fail_on == "any":
        return 0 if verdict.get("passed", False) else 1
    if fail_on == "soft":
        return 0 if (not verdict.get("hard_blocked") and not verdict.get("soft_blocked")) else 1
    # default: hard only
    return 0 if not verdict.get("hard_blocked") else 1


def _render_pr_comment(
    verdicts: dict[str, dict[str, Any]],
    semantic_coverage: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = ["## Qualix Quality Gate\n"]

    for phase_id, verdict in sorted(verdicts.items()):
        hard_blocked = verdict.get("hard_blocked", False)
        soft_blocked = verdict.get("soft_blocked", False)

        if hard_blocked:
            phase_icon = _FAIL_ICON
        elif soft_blocked:
            phase_icon = _WARN_ICON
        else:
            phase_icon = _PASS_ICON

        summary = verdict.get("summary", {})
        lines.append(f"### {phase_icon} Phase {phase_id}")
        lines.append("")
        lines.append(f"通过: {summary.get('passed', 0)} / {summary.get('total', 0)}  "
                     f"HARD失败: {summary.get('hard_failures', 0)}  "
                     f"SOFT失败: {summary.get('soft_failures', 0)}")
        lines.append("")

        checks = verdict.get("checks", [])
        failures = [c for c in checks if not c.get("passed", True)]
        if failures:
            lines.append("| 级别 | 检查项 | 说明 |")
            lines.append("|------|--------|------|")
            for check in failures:
                level = check.get("level", "SOFT")
                icon = _FAIL_ICON if level == "HARD" else _WARN_ICON
                name = check.get("name", "")
                msg = check.get("message", "")[:120]
                lines.append(f"| {icon} {level} | `{name}` | {msg} |")
            lines.append("")

    # 语义覆盖率对比
    if semantic_coverage:
        sem_rate = semantic_coverage.get("semantic_coverage_rate")
        line_rate = semantic_coverage.get("line_coverage_rate")
        if sem_rate is not None:
            lines.append("---")
            lines.append("### 覆盖率对比")
            sem_pct = f"{sem_rate * 100:.1f}%"
            if line_rate is not None:
                line_pct = f"{line_rate * 100:.1f}%"
                lines.append(f"**语义覆盖率（EUT）**: {sem_pct}  ←→  **行覆盖率（JaCoCo）**: {line_pct}")
                if sem_rate < line_rate - 0.05:
                    lines.append(f"> 差距 {(line_rate - sem_rate) * 100:.1f}%：部分代码行被执行，但对应业务语义未被充分验证")
            else:
                lines.append(f"**语义覆盖率（EUT）**: {sem_pct}（行覆盖率不可用）")
            lines.append("")

    return "\n".join(lines)


def _render_human_readable(verdicts: dict[str, dict[str, Any]]) -> str:
    lines: list[str] = ["\n[Qualix CI Gate]\n"]

    overall_hard = False
    overall_soft = False

    for phase_id, verdict in sorted(verdicts.items()):
        hard_blocked = verdict.get("hard_blocked", False)
        soft_blocked = verdict.get("soft_blocked", False)
        summary = verdict.get("summary", {})

        if hard_blocked:
            overall_hard = True
            status_label = "HARD BLOCK"
            icon = _FAIL_ICON
        elif soft_blocked:
            overall_soft = True
            status_label = "SOFT WARN"
            icon = _WARN_ICON
        else:
            status_label = "PASS"
            icon = _PASS_ICON

        lines.append(
            f"  {icon} Phase {phase_id}: {status_label}  "
            f"({summary.get('passed', 0)}/{summary.get('total', 0)} checks)"
        )

        checks = verdict.get("checks", [])
        for check in checks:
            if check.get("passed", True):
                continue
            level = check.get("level", "SOFT")
            mark = "  ✗" if level == "HARD" else "  ⚠"
            msg = check.get("message", "")[:100]
            lines.append(f"  {mark} [{level}] {check.get('name', '')} — {msg}")

    lines.append("")
    if overall_hard:
        lines.append("  结论: HARD BLOCK — exit 1 (有强制失败项，需修复后重新 finalize)")
    elif overall_soft:
        lines.append("  结论: SOFT WARN — exit 0 (有警告项，建议处理)")
    else:
        lines.append("  结论: PASS — exit 0")

    return "\n".join(lines)


def _load_semantic_coverage(output_dir: Path, project_id: str, phase_id: str) -> dict[str, Any] | None:
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_id)
    path = output_dir / project_id / dir_suffix / "_semantic_coverage_report.json"
    if not path.exists():
        return None
    return load_json(path) or None


def cmd_ci_gate(args: argparse.Namespace, output_dir: Path) -> int:
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    phase_arg: str | None = getattr(args, "phase", None)
    all_phases: bool = getattr(args, "all_phases", False)
    fail_on: str = getattr(args, "fail_on", "hard")
    pr_comment: bool = getattr(args, "pr_comment", False)
    json_mode = cli_json_mode(args)

    # 收集 verdict(s)
    if all_phases:
        verdicts = _collect_all_verdicts(output_dir, args.project_id)
        if not verdicts:
            msg = f"未找到任何 Phase 的 _gate_verdict.json（output/{args.project_id}/<phase>/）"
            if json_mode:
                print_cli_json(cli_envelope(command="ci-gate", project_id=args.project_id,
                                            success=False, exit_code=1,
                                            errors=[msg]))
            else:
                print(f"  ERROR: {msg}", file=sys.stderr)
            return 1
        target_phases = list(verdicts.keys())
    else:
        if not phase_arg:
            msg = "必须指定 --phase 或 --all-phases"
            if json_mode:
                print_cli_json(cli_envelope(command="ci-gate", project_id=args.project_id,
                                            success=False, exit_code=1,
                                            errors=[msg]))
            else:
                print(f"  ERROR: {msg}", file=sys.stderr)
            return 1
        verdict = _load_verdict(output_dir, args.project_id, phase_arg)
        if verdict is None:
            msg = (f"未找到 _gate_verdict.json（output/{args.project_id}/{phase_arg}/）。"
                   f"请先执行 qualix-run {args.project_id} finalize {phase_arg}")
            if json_mode:
                print_cli_json(cli_envelope(command="ci-gate", project_id=args.project_id,
                                            success=False, exit_code=1,
                                            phase_id=phase_arg, errors=[msg]))
            else:
                print(f"  ERROR: {msg}", file=sys.stderr)
            return 1
        verdicts = {phase_arg: verdict}
        target_phases = [phase_arg]

    # 计算整体 exit code
    exit_code = 0
    for v in verdicts.values():
        if _determine_exit_code(v, fail_on) != 0:
            exit_code = 1
            break

    overall_passed = exit_code == 0

    # 语义覆盖率（仅 Q06 有，按需加载）
    semantic_coverage = None
    if "Q06" in verdicts:
        semantic_coverage = _load_semantic_coverage(output_dir, args.project_id, "Q06")

    if json_mode:
        extra: dict[str, Any] = {
            "fail_on": fail_on,
            "phases": target_phases,
            "verdicts": {pid: v for pid, v in verdicts.items()},
        }
        if semantic_coverage:
            extra["semantic_coverage"] = semantic_coverage
        print_cli_json(cli_envelope(
            command="ci-gate",
            project_id=args.project_id,
            success=overall_passed,
            exit_code=exit_code,
            phase_id=phase_arg,
            extra=extra,
        ))
    elif pr_comment:
        print(_render_pr_comment(verdicts, semantic_coverage))
    else:
        print(_render_human_readable(verdicts))

    return exit_code


def cmd_evidence_audit(args: argparse.Namespace, output_dir: Path) -> int:
    """evidence-audit：展示 SE → EUT → Test → Coverage 链路健康度."""
    from qualix.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    phase_arg: str | None = getattr(args, "phase", None) or "Q06"
    json_mode = cli_json_mode(args)

    # 尝试加载 EvidenceGraph（如果已实现）
    try:
        from qualix.quality.evidence_graph import EvidenceGraph
        graph = EvidenceGraph.build(output_dir, args.project_id)
        report = graph.to_report()
    except (ImportError, Exception) as e:
        # Evidence Graph 尚未实现时，降级到基本摘要
        report = _basic_evidence_summary(output_dir, args.project_id, phase_arg)
        if report is None:
            msg = f"无法生成 evidence audit（{e}）。请先完成 Q01/Q05/Q06 的 finalize。"
            if json_mode:
                print_cli_json(cli_envelope(command="evidence-audit", project_id=args.project_id,
                                            success=False, exit_code=1, errors=[msg]))
            else:
                print(f"  ERROR: {msg}", file=sys.stderr)
            return 1

    if json_mode:
        print_cli_json(cli_envelope(command="evidence-audit", project_id=args.project_id,
                                    success=True, exit_code=0, phase_id=phase_arg,
                                    extra={"report": report}))
    else:
        _print_evidence_report(report)

    return 0


def _basic_evidence_summary(
    output_dir: Path, project_id: str, phase_id: str
) -> dict[str, Any] | None:
    """在 EvidenceGraph 未实现时提供基本摘要（从现有 JSON 文件聚合）."""
    from qualix.json_utils import load_json

    q01_dir = output_dir / project_id / "Q01"
    q05a_dir = output_dir / project_id / "Q05a"
    q06_dir = output_dir / project_id / "Q06"

    q01_data = load_json(q01_dir / "phase_a_structured.json") or {}
    q05a_data = load_json(q05a_dir / "phase_b_structured.json") or {}
    q06_data = load_json(q06_dir / "phase_c_structured.json") or {}

    se_list = q01_data.get("semantic_expectations", [])
    eut_list = q05a_data.get("eut_items", [])
    audit_list = q06_data.get("audit_items", [])

    if not se_list and not eut_list:
        return None

    # SE → EUT 映射
    eut_by_se: dict[str, list[str]] = {}
    for eut in eut_list:
        bound = eut.get("bound_se") or eut.get("bound_item", "")
        if bound:
            eut_by_se.setdefault(bound, []).append(eut.get("eut_id", ""))

    # EUT → Q06 audit 状态
    audit_by_eut: dict[str, str] = {}
    for item in audit_list:
        eut_id = item.get("eut_id", "")
        if eut_id:
            for eid in eut_id.split(","):
                audit_by_eut[eid.strip()] = item.get("status", "MISSING")

    rows: list[dict[str, Any]] = []
    for se in se_list:
        se_id = se.get("se_id", "")
        euts = eut_by_se.get(se_id, [])
        audit_statuses = [audit_by_eut.get(e, "NOT_AUDITED") for e in euts] if euts else []
        covered = sum(1 for s in audit_statuses if s == "COVERED")
        rows.append({
            "se_id": se_id,
            "has_eut": len(euts) > 0,
            "eut_count": len(euts),
            "eut_ids": euts,
            "audit_covered": covered,
            "audit_total": len(audit_statuses),
        })

    total_se = len(rows)
    se_with_eut = sum(1 for r in rows if r["has_eut"])
    se_with_coverage = sum(1 for r in rows if r["audit_covered"] > 0)

    return {
        "summary": {
            "total_se": total_se,
            "se_with_eut": se_with_eut,
            "se_without_eut": total_se - se_with_eut,
            "se_with_coverage": se_with_coverage,
            "eut_coverage_rate": round(se_with_eut / total_se, 3) if total_se else 0,
            "semantic_coverage_rate": round(se_with_coverage / total_se, 3) if total_se else 0,
        },
        "details": rows,
    }


def _print_evidence_report(report: dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("\n[evidence-audit] SE → EUT → Coverage 链路健康度\n")
    print(f"  总 SE: {summary.get('total_se', 0)}")
    print(f"  有 EUT: {summary.get('se_with_eut', 0)}  "
          f"({summary.get('eut_coverage_rate', 0) * 100:.1f}%)")
    print(f"  有 Coverage: {summary.get('se_with_coverage', 0)}  "
          f"({summary.get('semantic_coverage_rate', 0) * 100:.1f}%)")
    print(f"  无 EUT: {summary.get('se_without_eut', 0)}")
    print()

    details = report.get("details", [])
    for row in details:
        se_id = row.get("se_id", "")
        eut_icon = _PASS_ICON if row.get("has_eut") else _FAIL_ICON
        eut_count = row.get("eut_count", 0)
        covered = row.get("audit_covered", 0)
        total = row.get("audit_total", 0)
        if total > 0:
            cov_icon = _PASS_ICON if covered == total else (_WARN_ICON if covered > 0 else _FAIL_ICON)
            cov_str = f"{cov_icon} coverage({covered}/{total})"
        else:
            cov_str = f"{_SKIP_ICON} coverage"
        print(f"  {se_id:<12} {eut_icon} EUT({eut_count}条)  {cov_str}")
