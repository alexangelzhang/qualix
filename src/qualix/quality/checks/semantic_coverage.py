"""语义覆盖率 vs 行覆盖率对比报告.

语义覆盖率：有 Q06 COVERED 状态的 EUT / Q05a 总 EUT 数（业务语义层）
行覆盖率：JaCoCo 报告的行/分支覆盖率（代码层）

两者差距揭示：有代码行被执行，但对应业务语义（EUT）未被充分验证。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qualix.json_utils import load_json, save_json
from qualix.log import get_logger

log = get_logger(__name__)

SEMANTIC_COVERAGE_REPORT_FILENAME = "_semantic_coverage_report.json"


@dataclass
class SemanticCoverageReport:
    total_eut: int = 0
    covered_eut: int = 0
    partial_eut: int = 0
    missing_eut: int = 0
    wrong_target_eut: int = 0
    not_audited_eut: int = 0
    semantic_coverage_rate: float = 0.0    # covered / total（EUT 粒度）
    line_coverage_rate: float | None = None  # JaCoCo（若可用）
    branch_coverage_rate: float | None = None
    gap_analysis: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_eut": self.total_eut,
            "covered_eut": self.covered_eut,
            "partial_eut": self.partial_eut,
            "missing_eut": self.missing_eut,
            "wrong_target_eut": self.wrong_target_eut,
            "not_audited_eut": self.not_audited_eut,
            "semantic_coverage_rate": round(self.semantic_coverage_rate, 4),
            "line_coverage_rate": round(self.line_coverage_rate, 4) if self.line_coverage_rate is not None else None,
            "branch_coverage_rate": round(self.branch_coverage_rate, 4) if self.branch_coverage_rate is not None else None,
            "gap_analysis": self.gap_analysis,
            "generated_at": self.generated_at,
        }


def compute_semantic_coverage(output_dir: Path, project_id: str) -> SemanticCoverageReport:
    """计算语义覆盖率和行覆盖率，生成对比报告."""
    from qualix.constants import PHASE_DIR_MAP

    report = SemanticCoverageReport(generated_at=datetime.now(UTC).isoformat(timespec="seconds"))

    # 加载 Q05a EUT 矩阵
    q05a_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q05a")
    q05a_data = load_json(q05a_dir / "phase_b_structured.json") or {}
    eut_list: list[dict] = q05a_data.get("eut_items", [])
    report.total_eut = len(eut_list)

    if report.total_eut == 0:
        report.gap_analysis = "Q05a 产物不存在或无 EUT 条目"
        return report

    # 加载 Q06 审计结果
    q06_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q06", "Q06")
    q06_data = load_json(q06_dir / "phase_c_structured.json") or {}
    audit_list: list[dict] = q06_data.get("audit_items", [])

    # 按 EUT ID 建立审计状态索引
    audit_by_eut: dict[str, str] = {}
    for item in audit_list:
        raw = item.get("eut_id", "")
        status = item.get("status", "MISSING")
        for eid in (raw.split(",") if raw else []):
            audit_by_eut[eid.strip()] = status

    # 统计各状态
    for eut in eut_list:
        eut_id = eut.get("eut_id", "")
        status = audit_by_eut.get(eut_id, "NOT_AUDITED") if eut_id else "NOT_AUDITED"
        if status == "COVERED":
            report.covered_eut += 1
        elif status == "PARTIAL":
            report.partial_eut += 1
        elif status == "MISSING":
            report.missing_eut += 1
        elif status in ("WRONG_TARGET", "CONFLICT"):
            report.wrong_target_eut += 1
        else:
            report.not_audited_eut += 1

    report.semantic_coverage_rate = (
        report.covered_eut / report.total_eut if report.total_eut > 0 else 0.0
    )

    # JaCoCo 行覆盖率
    report.line_coverage_rate, report.branch_coverage_rate = _load_jacoco_rates(output_dir, project_id)

    # 差距分析
    report.gap_analysis = _build_gap_analysis(report)

    return report


def _load_jacoco_rates(output_dir: Path, project_id: str) -> tuple[float | None, float | None]:
    """从 coverage gate 结果文件提取 JaCoCo 行/分支覆盖率。"""
    from qualix.constants import PHASE_DIR_MAP

    q06_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q06", "Q06")

    # 优先读 _internal/_coverage_gate_result.json（如果存在）
    cov_result = load_json(q06_dir / "_internal" / "_coverage_gate_result.json")
    if cov_result:
        line = cov_result.get("line", {}).get("rate")
        branch = cov_result.get("branch", {}).get("rate")
        if line is not None:
            return float(line), float(branch) if branch is not None else None

    # fallback：从 gate_verdict.json 的 coverage_gate check 提取
    verdict = load_json(q06_dir / "_gate_verdict.json")
    if verdict:
        for check in verdict.get("checks", []):
            details = check.get("details", {})
            if "line_rate" in details:
                return float(details["line_rate"]), details.get("branch_rate")

    return None, None


def _build_gap_analysis(r: SemanticCoverageReport) -> str:
    parts: list[str] = []
    sem_pct = f"{r.semantic_coverage_rate * 100:.1f}%"

    if r.line_coverage_rate is not None:
        line_pct = f"{r.line_coverage_rate * 100:.1f}%"
        gap = r.line_coverage_rate - r.semantic_coverage_rate
        if gap > 0.05:
            parts.append(
                f"语义覆盖率 {sem_pct} < 行覆盖率 {line_pct}，"
                f"差距 {gap * 100:.1f}%：有代码行被执行但对应业务语义未被充分验证"
            )
        elif gap < -0.05:
            parts.append(
                f"语义覆盖率 {sem_pct} > 行覆盖率 {line_pct}：部分 EUT 可能未实际执行代码"
            )
        else:
            parts.append(f"语义覆盖率 {sem_pct} ≈ 行覆盖率 {line_pct}，两者基本一致")
    else:
        parts.append(f"语义覆盖率 {sem_pct}（行覆盖率不可用，需提供 JaCoCo 报告）")

    if r.wrong_target_eut > 0:
        parts.append(f"{r.wrong_target_eut} 条 EUT 标记为 WRONG_TARGET（测试存在但断言错误）")
    if r.partial_eut > 0:
        parts.append(f"{r.partial_eut} 条 EUT 标记为 PARTIAL（断言不充分）")
    if r.missing_eut > 0:
        parts.append(f"{r.missing_eut} 条 EUT 完全没有覆盖")

    return "；".join(parts)


def compute_and_save_semantic_coverage(output_dir: Path, project_id: str) -> Path:
    """计算并持久化到 output/<pid>/Q06/_semantic_coverage_report.json。"""
    from qualix.constants import PHASE_DIR_MAP

    report = compute_semantic_coverage(output_dir, project_id)
    q06_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q06", "Q06")
    q06_dir.mkdir(parents=True, exist_ok=True)
    path = q06_dir / SEMANTIC_COVERAGE_REPORT_FILENAME
    save_json(path, report.to_dict())
    log.info(
        "semantic_coverage: %d EUT total, %.1f%% semantic, %s line",
        report.total_eut,
        report.semantic_coverage_rate * 100,
        f"{report.line_coverage_rate * 100:.1f}%" if report.line_coverage_rate else "N/A",
    )
    return path
