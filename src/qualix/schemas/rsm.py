"""RSM (Requirement Semantic Model): 全局需求语义模型.

跨 Phase 追踪每条需求的生命周期，计算覆盖率矩阵。

ID 生命周期：
  Phase A  → REQ/BR/SE/GAP/OPEN 创建
  Phase A.5 → REQ/BR/SE 覆盖度标注，GAP/OPEN 闭环状态
  Phase B  → EUT 通过 bound_se 关联 SE
  Phase D  → ReviewFinding 通过 related_req 关联 REQ

用法：
    from qualix.schemas.rsm import build_lifecycle, compute_coverage
    lifecycle = build_lifecycle(output_dir, project_id)
    coverage = compute_coverage(lifecycle)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json
from qualix.text_utils import STRUCTURED_JSON_MAP

# ---------------------------------------------------------------------------
# 生命周期状态
# ---------------------------------------------------------------------------


class LifecycleStage(StrEnum):
    IDENTIFIED = "IDENTIFIED"  # Phase A 创建
    COVERED = "COVERED"  # Phase A.5 标注为覆盖
    PARTIAL = "PARTIAL"  # Phase A.5 标注为部分覆盖
    NOT_COVERED = "NOT_COVERED"  # Phase A.5 标注为未覆盖
    HAS_EUT = "HAS_EUT"  # Phase B 有对应 EUT
    NO_EUT = "NO_EUT"  # Phase B 无对应 EUT
    REVIEWED = "REVIEWED"  # Phase D 有对应 finding
    NOT_REVIEWED = "NOT_REVIEWED"  # Phase D 无对应 finding
    CLOSED = "CLOSED"  # GAP/OPEN 已闭环
    UNCLOSED = "UNCLOSED"  # GAP/OPEN 未闭环


@dataclass
class RequirementLifecycle:
    """一条需求在整个 pipeline 中的追踪状态."""

    req_id: str
    id_type: str  # REQ / BR / SE / GAP / OPEN
    description: str = ""

    # Phase A.5 覆盖度
    coverage_status: str = ""  # COVERED / PARTIAL / MISSING / IMPLICIT / ""

    # Phase B 测试
    eut_ids: list[str] = field(default_factory=list)  # 关联的 EUT ID

    # Phase D 评审
    finding_ids: list[str] = field(default_factory=list)  # 关联的 finding ID

    # GAP/OPEN 闭环
    closure_status: str = ""  # 已闭环 / 部分闭环 / 未闭环 / ""


@dataclass
class CoverageReport:
    """跨 Phase 覆盖率报告."""

    project_id: str
    total_reqs: int = 0
    total_brs: int = 0
    total_ses: int = 0
    total_gaps: int = 0
    total_opens: int = 0

    # A.5 覆盖率
    reqs_covered: int = 0
    ses_covered: int = 0

    # B 测试覆盖率
    ses_with_eut: int = 0

    # D 评审覆盖率
    reqs_with_finding: int = 0

    # GAP/OPEN 闭环率
    gaps_closed: int = 0
    opens_closed: int = 0

    @property
    def req_coverage_rate(self) -> float:
        return self.reqs_covered / self.total_reqs if self.total_reqs else 0

    @property
    def se_coverage_rate(self) -> float:
        return self.ses_covered / self.total_ses if self.total_ses else 0

    @property
    def test_coverage_rate(self) -> float:
        return self.ses_with_eut / self.total_ses if self.total_ses else 0

    @property
    def review_coverage_rate(self) -> float:
        return self.reqs_with_finding / self.total_reqs if self.total_reqs else 0

    @property
    def gap_closure_rate(self) -> float:
        return self.gaps_closed / self.total_gaps if self.total_gaps else 1.0

    @property
    def open_closure_rate(self) -> float:
        return self.opens_closed / self.total_opens if self.total_opens else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "total_reqs": self.total_reqs,
            "total_ses": self.total_ses,
            "total_gaps": self.total_gaps,
            "total_opens": self.total_opens,
            "req_coverage_rate": round(self.req_coverage_rate, 3),
            "se_coverage_rate": round(self.se_coverage_rate, 3),
            "test_coverage_rate": round(self.test_coverage_rate, 3),
            "review_coverage_rate": round(self.review_coverage_rate, 3),
            "gap_closure_rate": round(self.gap_closure_rate, 3),
            "open_closure_rate": round(self.open_closure_rate, 3),
        }

    def summary(self) -> str:
        lines = [
            f"## 覆盖率报告 — {self.project_id}",
            f"- REQ: {self.total_reqs} 条, A.5 覆盖率 {self.req_coverage_rate:.0%}",
            f"- SE: {self.total_ses} 条, A.5 覆盖率 {self.se_coverage_rate:.0%}, 测试覆盖率 {self.test_coverage_rate:.0%}",
            f"- GAP: {self.total_gaps} 条, 闭环率 {self.gap_closure_rate:.0%}",
            f"- OPEN: {self.total_opens} 条, 闭环率 {self.open_closure_rate:.0%}",
            f"- 评审覆盖率: {self.review_coverage_rate:.0%}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 构建生命周期
# ---------------------------------------------------------------------------


def _load_phase_json(output_dir: Path, project_id: str, phase_id: str) -> dict | None:
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return None
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None
    path = _phase_dir(output_dir, project_id, phase_def) / json_file
    if not path.exists():
        return None
    return load_json(path)


def build_lifecycle(
    output_dir: Path,
    project_id: str,
) -> dict[str, RequirementLifecycle]:
    """从各 Phase 的 structured JSON 构建全局 ID 生命周期."""
    from concurrent.futures import ThreadPoolExecutor

    lifecycle: dict[str, RequirementLifecycle] = {}

    # 并行加载各 Phase 的 JSON
    phase_ids = ("Q01", "Q04", "Q05a", "Q07")
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pid: pool.submit(_load_phase_json, output_dir, project_id, pid) for pid in phase_ids}
        phase_data = {pid: f.result() for pid, f in futures.items()}

    # Phase A: 创建 REQ/BR/SE/GAP/OPEN
    data_a = phase_data.get("Q01")
    if data_a:
        for req in data_a.get("requirements", []):
            rid = req.get("req_id", "")
            if rid:
                id_type = "REQ" if rid.startswith("REQ") else "BR"
                lifecycle[rid] = RequirementLifecycle(
                    req_id=rid,
                    id_type=id_type,
                    description=req.get("description", ""),
                )
        for se in data_a.get("semantic_expectations", []):
            sid = se.get("se_id", "")
            if sid:
                lifecycle[sid] = RequirementLifecycle(
                    req_id=sid,
                    id_type="SE",
                    description=se.get("description", ""),
                )
        for gap in data_a.get("gaps", []):
            gid = gap.get("gap_id", "")
            if gid:
                lifecycle[gid] = RequirementLifecycle(
                    req_id=gid,
                    id_type="GAP",
                    description=gap.get("description", ""),
                )
        for op in data_a.get("open_items", []):
            oid = op.get("open_id", "")
            if oid:
                lifecycle[oid] = RequirementLifecycle(
                    req_id=oid,
                    id_type="OPEN",
                    description=op.get("question", ""),
                )

    # Phase A.5: 覆盖度标注 + 闭环状态
    data_a5 = phase_data.get("Q04")
    if data_a5:
        for item in data_a5.get("req_coverage", []):
            rid = item.get("req_id", "")
            if rid and rid in lifecycle:
                lifecycle[rid].coverage_status = item.get("status", "")
        for item in data_a5.get("se_coverage", []):
            sid = item.get("se_id", "")
            if sid and sid in lifecycle:
                lifecycle[sid].coverage_status = item.get("status", "")
        for item in data_a5.get("gap_closure", []):
            gid = item.get("gap_id", "")
            if gid and gid in lifecycle:
                lifecycle[gid].closure_status = item.get("status", "")
        for item in data_a5.get("open_closure", []):
            oid = item.get("open_id", "")
            if oid and oid in lifecycle:
                lifecycle[oid].closure_status = item.get("status", "")

    # Phase Q05a: EUT 关联
    data_b = phase_data.get("Q05a")
    if data_b:
        eut_list = data_b.get("eut_items", []) or data_b.get("test_cases", [])
        for eut in eut_list:
            eut_id = eut.get("eut_id", "") or eut.get("id", "")
            bound_ses = eut.get("bound_se", "")
            if not bound_ses:
                bound_ses = eut.get("se_refs", [])
            if isinstance(bound_ses, str):
                bound_ses = [bound_ses] if bound_ses else []
            for bound_se in bound_ses:
                if bound_se and bound_se in lifecycle:
                    lifecycle[bound_se].eut_ids.append(eut_id)

    # Phase D: Finding 关联
    data_d = phase_data.get("Q07")
    if data_d:
        for finding in data_d.get("findings", []):
            related = finding.get("related_req", "")
            fid = finding.get("finding_id", "")
            if related and related in lifecycle:
                lifecycle[related].finding_ids.append(fid)

    return lifecycle


def compute_coverage(
    lifecycle: dict[str, RequirementLifecycle],
    project_id: str = "",
) -> CoverageReport:
    """从生命周期数据计算覆盖率."""
    report = CoverageReport(project_id=project_id)

    for item in lifecycle.values():
        if item.id_type == "REQ":
            report.total_reqs += 1
            # PARTIAL 也算已覆盖（与 SKILL 定义一致：无 MISSING 即通过）
            if item.coverage_status in ("COVERED", "IMPLICIT", "PARTIAL"):
                report.reqs_covered += 1
            if item.finding_ids:
                report.reqs_with_finding += 1
        elif item.id_type == "BR":
            report.total_brs += 1
        elif item.id_type == "SE":
            report.total_ses += 1
            if item.coverage_status in ("COVERED", "IMPLICIT"):
                report.ses_covered += 1
            if item.eut_ids:
                report.ses_with_eut += 1
        elif item.id_type == "GAP":
            report.total_gaps += 1
            if item.closure_status == "已闭环":
                report.gaps_closed += 1
        elif item.id_type == "OPEN":
            report.total_opens += 1
            if item.closure_status == "已闭环":
                report.opens_closed += 1

    return report


# ---------------------------------------------------------------------------
# RSM 持久化 + Mutation（从只读聚合升级为可写数据总线）
# ---------------------------------------------------------------------------

_RSM_FILENAME = "_rsm.json"


def _rsm_path(output_dir: Path, project_id: str) -> Path:
    """RSM 持久化路径: output/<project_id>/_rsm.json."""
    return output_dir / project_id / _RSM_FILENAME


def save_rsm(
    output_dir: Path,
    project_id: str,
    lifecycle: dict[str, RequirementLifecycle],
) -> Path:
    """持久化 RSM 到 JSON 文件."""
    from qualix.json_utils import save_json

    path = _rsm_path(output_dir, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        rid: {
            "req_id": item.req_id,
            "id_type": item.id_type,
            "description": item.description,
            "coverage_status": item.coverage_status,
            "eut_ids": item.eut_ids,
            "finding_ids": item.finding_ids,
            "closure_status": item.closure_status,
        }
        for rid, item in lifecycle.items()
    }
    save_json(path, data)
    return path


def _is_rsm_stale(output_dir: Path, project_id: str, rsm_path: Path) -> bool:
    """检查 RSM 缓存是否过期：任一 Phase JSON 比 _rsm.json 更新则过期."""
    try:
        rsm_mtime = rsm_path.stat().st_mtime
    except OSError:
        return True

    phase_ids = ("Q01", "Q04", "Q05a", "Q07")
    for pid in phase_ids:
        json_file = STRUCTURED_JSON_MAP.get(pid)
        phase_def = PHASE_DEFS.get(pid)
        if not json_file or not phase_def:
            continue
        phase_json = _phase_dir(output_dir, project_id, phase_def) / json_file
        try:
            if phase_json.stat().st_mtime > rsm_mtime:
                return True
        except OSError:
            continue  # Phase JSON 不存在，不影响判断
    return False


def load_rsm(output_dir: Path, project_id: str) -> dict[str, RequirementLifecycle]:
    """从持久化文件加载 RSM。不存在或过期则从 Phase JSON 重建."""
    path = _rsm_path(output_dir, project_id)
    if path.exists() and not _is_rsm_stale(output_dir, project_id, path):
        data = load_json(path)
        if data and isinstance(data, dict):
            lifecycle = {}
            for rid, item_data in data.items():
                lifecycle[rid] = RequirementLifecycle(
                    req_id=item_data.get("req_id", rid),
                    id_type=item_data.get("id_type", ""),
                    description=item_data.get("description", ""),
                    coverage_status=item_data.get("coverage_status", ""),
                    eut_ids=item_data.get("eut_ids", []),
                    finding_ids=item_data.get("finding_ids", []),
                    closure_status=item_data.get("closure_status", ""),
                )
            return lifecycle
    # 缓存不存在或已过期：从 Phase JSON 全量重建并持久化
    lifecycle = build_lifecycle(output_dir, project_id)
    if lifecycle:
        save_rsm(output_dir, project_id, lifecycle)
    return lifecycle


# ---------------------------------------------------------------------------
# Backward-compat re-export: mutations moved to rsm_mutations.py
# Lazy import to break rsm ↔ rsm_mutations circular dependency
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    _reexports = {"RSMMutation", "apply_mutations", "mutations_from_critique"}
    if name in _reexports:
        from qualix.schemas import rsm_mutations

        return getattr(rsm_mutations, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
