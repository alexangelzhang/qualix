"""EvidenceGraph：SE → EUT → Test → Coverage 链路健康度图.

统一查询 Qualix 全 Phase 的证据链完整度，回答：
- 哪些 SE 没有 EUT？
- 哪些 EUT 没有对应测试代码？
- 哪些 EUT 通过了 Q06 审计（COVERED）？
- 语义覆盖率 vs 行覆盖率的差距在哪？

复用现有检查组件，不重复检查逻辑：
- SE.source：evidence_contract.verify_se_sources()
- SE→EUT：cross_phase_check.validate_eut_id_subset() 数据
- EUT→test_class：phase_b_structured.json test_location 字段
- test_class→coverage：coverage_gate.parse_jacoco_xml()
- EUT→Q06 audit：phase_c_structured.json audit_items
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qualix.json_utils import load_json, save_json
from qualix.log import get_logger

log = get_logger(__name__)

EVIDENCE_GRAPH_FILENAME = "_evidence_graph.json"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class EvidenceClaim:
    """单条证据声明：subject -[claim_type]-> object。"""

    claim_id: str          # "SE-001::has_eut::EUT-003"
    subject_id: str        # "SE-001"
    claim_type: str        # has_source | has_eut | has_test | has_coverage | has_audit
    object_id: str         # "EUT-003" or "TestClass#method" or coverage%
    status: str            # verified | missing | stale | invalid | not_applicable
    evidence_path: str = ""  # 文件路径:行号（可选）
    message: str = ""
    verified_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "subject_id": self.subject_id,
            "claim_type": self.claim_type,
            "object_id": self.object_id,
            "status": self.status,
            "evidence_path": self.evidence_path,
            "message": self.message,
            "verified_at": self.verified_at,
        }


@dataclass
class EvidenceGraphSummary:
    total_se: int = 0
    se_with_source: int = 0
    se_with_eut: int = 0
    se_with_test: int = 0
    se_with_coverage: int = 0
    se_with_audit: int = 0
    semantic_coverage_rate: float = 0.0   # se_with_audit(COVERED) / total_se
    line_coverage_rate: float | None = None  # JaCoCo（若可用）
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_se": self.total_se,
            "se_with_source": self.se_with_source,
            "se_with_eut": self.se_with_eut,
            "se_with_test": self.se_with_test,
            "se_with_coverage": self.se_with_coverage,
            "se_with_audit": self.se_with_audit,
            "semantic_coverage_rate": round(self.semantic_coverage_rate, 4),
            "line_coverage_rate": round(self.line_coverage_rate, 4) if self.line_coverage_rate is not None else None,
            "generated_at": self.generated_at,
        }


class EvidenceGraph:
    """SE → EUT → Test → Coverage 链路图。"""

    def __init__(self) -> None:
        self._claims: list[EvidenceClaim] = []
        self.summary = EvidenceGraphSummary()

    # ---- 构建 ----

    @classmethod
    def build(cls, output_dir: Path, project_id: str) -> "EvidenceGraph":
        """从现有 Phase 产物构建 EvidenceGraph（只读，不重跑检查）。"""
        graph = cls()
        graph._build_from_artifacts(output_dir, project_id)
        return graph

    def _build_from_artifacts(self, output_dir: Path, project_id: str) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")

        # 加载各 Phase 产物
        q01_data = self._load_phase_json(output_dir, project_id, "Q01", "phase_a_structured.json")
        q05a_data = self._load_phase_json(output_dir, project_id, "Q05a", "phase_b_structured.json")
        q06_data = self._load_phase_json(output_dir, project_id, "Q06", "phase_c_structured.json")

        se_list: list[dict] = (q01_data or {}).get("semantic_expectations", [])
        eut_list: list[dict] = (q05a_data or {}).get("eut_items", [])
        audit_list: list[dict] = (q06_data or {}).get("audit_items", [])

        # 建立反向索引
        eut_by_se: dict[str, list[dict]] = {}
        for eut in eut_list:
            bound = eut.get("bound_se") or eut.get("bound_item", "")
            if bound:
                eut_by_se.setdefault(bound, []).append(eut)

        audit_by_eut: dict[str, dict] = {}
        for item in audit_list:
            raw_eut_id = item.get("eut_id", "")
            for eid in (raw_eut_id.split(",") if raw_eut_id else []):
                audit_by_eut[eid.strip()] = item

        # SE.source 验证（复用 evidence_contract）
        se_source_map: dict[str, str] = {}
        try:
            from qualix.quality.checks.evidence_contract import verify_se_sources
            source_results = verify_se_sources(output_dir, project_id)
            for r in source_results:
                se_id = r.get("se_id", "")
                se_source_map[se_id] = r.get("status", "ok")
        except Exception:
            pass

        # JaCoCo 行覆盖率
        line_coverage = self._load_line_coverage(output_dir, project_id)

        # 统计
        self.summary.total_se = len(se_list)
        self.summary.generated_at = now
        self.summary.line_coverage_rate = line_coverage

        se_with_audit_covered = 0

        for se in se_list:
            se_id = se.get("se_id", "")
            if not se_id:
                continue

            # 1. has_source
            src_status = se_source_map.get(se_id, "ok")
            src_claim_status = "verified" if src_status == "ok" else ("missing" if src_status == "empty_source" else "invalid")
            self._add_claim(se_id, "has_source", se.get("source", ""), src_claim_status,
                            evidence_path=se.get("source", ""))
            if src_claim_status == "verified":
                self.summary.se_with_source += 1

            # 2. has_eut
            euts = eut_by_se.get(se_id, [])
            if euts:
                self.summary.se_with_eut += 1
                for eut in euts:
                    eut_id = eut.get("eut_id", "")
                    self._add_claim(se_id, "has_eut", eut_id, "verified", now=now)

                    # 3. has_test（test_location 存在即视为有测试代码）
                    test_loc = eut.get("test_location", {})
                    test_class = test_loc.get("class_name") or eut.get("test_class", "")
                    if test_class:
                        self._add_claim(eut_id, "has_test", test_class, "verified",
                                        evidence_path=f"{test_loc.get('file', '')}:{test_loc.get('line_start', '')}")

                    # 4. has_audit（Q06 audit 状态）
                    audit_item = audit_by_eut.get(eut_id)
                    if audit_item:
                        audit_status = audit_item.get("status", "MISSING")
                        claim_status = "verified" if audit_status == "COVERED" else (
                            "invalid" if audit_status in ("WRONG_TARGET",) else "missing"
                        )
                        self._add_claim(
                            eut_id, "has_audit", audit_status, claim_status,
                            message=audit_item.get("recommendation", "")[:100],
                        )
                        if audit_status == "COVERED":
                            se_with_audit_covered += 1
                    else:
                        self._add_claim(eut_id, "has_audit", "NOT_AUDITED", "missing",
                                        message="EUT 未被 Q06 审计")
            else:
                self._add_claim(se_id, "has_eut", "", "missing", message="SE 没有对应 EUT")

        # 统计有 test / coverage / audit 的 SE 数
        se_with_test_set: set[str] = set()
        se_with_audit_set: set[str] = set()
        for c in self._claims:
            if c.claim_type == "has_test" and c.status == "verified":
                # 追溯回 SE
                for se_id2, euts in eut_by_se.items():
                    if any(e.get("eut_id") == c.subject_id for e in euts):
                        se_with_test_set.add(se_id2)
            if c.claim_type == "has_audit" and c.status == "verified":
                for se_id2, euts in eut_by_se.items():
                    if any(e.get("eut_id") == c.subject_id for e in euts):
                        se_with_audit_set.add(se_id2)

        self.summary.se_with_test = len(se_with_test_set)
        self.summary.se_with_audit = len(se_with_audit_set)
        self.summary.se_with_coverage = self.summary.se_with_audit  # coverage = 有审计通过
        total = self.summary.total_se
        self.summary.semantic_coverage_rate = (
            self.summary.se_with_audit / total if total > 0 else 0.0
        )

    def _add_claim(
        self, subject_id: str, claim_type: str, object_id: str, status: str,
        evidence_path: str = "", message: str = "", now: str = ""
    ) -> None:
        claim_id = f"{subject_id}::{claim_type}::{object_id}"
        self._claims.append(EvidenceClaim(
            claim_id=claim_id,
            subject_id=subject_id,
            claim_type=claim_type,
            object_id=object_id,
            status=status,
            evidence_path=evidence_path,
            message=message,
            verified_at=now or datetime.now(UTC).isoformat(timespec="seconds"),
        ))

    @staticmethod
    def _load_phase_json(output_dir: Path, project_id: str, phase_id: str, filename: str) -> dict | None:
        from qualix.constants import PHASE_DIR_MAP
        dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_id)
        path = output_dir / project_id / dir_suffix / filename
        if path.exists():
            return load_json(path)
        return None

    @staticmethod
    def _load_line_coverage(output_dir: Path, project_id: str) -> float | None:
        """从 _semantic_coverage_report.json 或 _gate_verdict.json 提取行覆盖率。"""
        from qualix.constants import PHASE_DIR_MAP
        q06_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q06", "Q06")

        # 优先读语义覆盖率报告
        sem_report = load_json(q06_dir / "_semantic_coverage_report.json")
        if sem_report and sem_report.get("line_coverage_rate") is not None:
            return float(sem_report["line_coverage_rate"])

        # fallback: gate_verdict 中的 coverage_gate 检查
        verdict = load_json(q06_dir / "_gate_verdict.json")
        if verdict:
            for check in verdict.get("checks", []):
                if "coverage" in check.get("name", "").lower():
                    details = check.get("details", {})
                    if "line_rate" in details:
                        return float(details["line_rate"])
        return None

    # ---- 查询 ----

    def query_chain(self, subject_id: str) -> list[EvidenceClaim]:
        """返回以 subject_id 为起点的所有声明链。"""
        direct = [c for c in self._claims if c.subject_id == subject_id]
        # 继续追踪 object_id 作为下一跳的 subject
        result = list(direct)
        visited = {subject_id}
        queue = [c.object_id for c in direct if c.object_id and c.object_id not in visited]
        while queue:
            next_id = queue.pop(0)
            if next_id in visited:
                continue
            visited.add(next_id)
            children = [c for c in self._claims if c.subject_id == next_id]
            result.extend(children)
            queue.extend(c.object_id for c in children if c.object_id and c.object_id not in visited)
        return result

    def missing_links(self, claim_type: str) -> list[str]:
        """返回 claim_type 为 missing 状态的 subject_id 列表。"""
        return [c.subject_id for c in self._claims if c.claim_type == claim_type and c.status == "missing"]

    def coverage_score(self) -> dict[str, float]:
        """返回各链路环节的覆盖率。"""
        total = self.summary.total_se
        if total == 0:
            return {}
        return {
            "source": self.summary.se_with_source / total,
            "eut": self.summary.se_with_eut / total,
            "test": self.summary.se_with_test / total,
            "audit": self.summary.se_with_audit / total,
            "semantic": self.summary.semantic_coverage_rate,
        }

    # ---- 序列化 ----

    def to_report(self) -> dict[str, Any]:
        """生成可供 evidence-audit 命令使用的报告字典。"""
        # SE 维度聚合：每个 SE 的链路状态
        se_rows: dict[str, dict[str, Any]] = {}
        for c in self._claims:
            if c.claim_type == "has_source":
                se_rows.setdefault(c.subject_id, {})["source"] = c.status
            elif c.claim_type == "has_eut":
                row = se_rows.setdefault(c.subject_id, {})
                row.setdefault("euts", []).append(c.object_id)
                row["has_eut"] = c.status == "verified"
            elif c.claim_type == "has_audit":
                # subject_id 是 eut_id，需要反查 SE
                pass

        details = [
            {"se_id": se_id, **row}
            for se_id, row in sorted(se_rows.items())
        ]

        return {
            "summary": self.summary.to_dict(),
            "coverage_scores": self.coverage_score(),
            "details": details,
            "missing_eut": self.missing_links("has_eut"),
            "missing_test": self.missing_links("has_test"),
            "missing_audit": self.missing_links("has_audit"),
        }

    def save(self, output_dir: Path, project_id: str) -> Path:
        """持久化到 output/<pid>/Q06/_evidence_graph.json。"""
        from qualix.constants import PHASE_DIR_MAP
        q06_dir = output_dir / project_id / PHASE_DIR_MAP.get("Q06", "Q06")
        q06_dir.mkdir(parents=True, exist_ok=True)
        path = q06_dir / EVIDENCE_GRAPH_FILENAME
        save_json(path, {
            "summary": self.summary.to_dict(),
            "claims": [c.to_dict() for c in self._claims],
        })
        return path
