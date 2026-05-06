"""Tests for dqg.schemas.rsm."""

import json
import tempfile
from pathlib import Path

from dqg.schemas.rsm import (
    RSMMutation,
    apply_mutations,
    build_lifecycle,
    compute_coverage,
    load_rsm,
    mutations_from_critique,
    save_rsm,
)


def _write_phase_json(tmpdir: Path, project_id: str, phase_dir: str, filename: str, data: dict):
    pd = tmpdir / project_id / phase_dir
    pd.mkdir(parents=True, exist_ok=True)
    (pd / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _setup_full_project(tmpdir: Path) -> Path:
    pid = "test-proj"

    # Phase A
    _write_phase_json(
        tmpdir,
        pid,
        "Q01",
        "phase_a_structured.json",
        {
            "project_id": pid,
            "requirements": [
                {"req_id": "REQ-001", "description": "创建工单"},
                {"req_id": "REQ-002", "description": "查询工单"},
                {"req_id": "BR-001", "parent_id": "REQ-001", "description": "幂等性校验"},
            ],
            "semantic_expectations": [
                {"se_id": "SE-001", "description": "幂等性"},
                {"se_id": "SE-002", "description": "并发控制"},
            ],
            "gaps": [
                {"gap_id": "GAP-001", "description": "超时未定义", "related_ids": ["REQ-001"]},
            ],
            "open_items": [
                {"open_id": "OPEN-001", "question": "超时时间？", "related_ids": ["REQ-001"]},
            ],
        },
    )

    # Phase A.5
    _write_phase_json(
        tmpdir,
        pid,
        "Q04",
        "phase_a5_structured.json",
        {
            "project_id": pid,
            "req_coverage": [
                {"req_id": "REQ-001", "status": "COVERED"},
                {"req_id": "REQ-002", "status": "MISSING"},
            ],
            "se_coverage": [
                {"se_id": "SE-001", "status": "COVERED"},
                {"se_id": "SE-002", "status": "PARTIAL"},
            ],
            "gap_closure": [
                {"gap_id": "GAP-001", "status": "已闭环"},
            ],
            "open_closure": [
                {"open_id": "OPEN-001", "status": "未闭环"},
            ],
        },
    )

    # Phase B
    _write_phase_json(
        tmpdir,
        pid,
        "Q05",
        "phase_b_structured.json",
        {
            "project_id": pid,
            "eut_items": [
                {
                    "eut_id": "EUT-001",
                    "bound_se": "SE-001",
                    "route_type": "Happy Path",
                    "given": "g",
                    "when": "w",
                    "then": "t",
                },
            ],
        },
    )

    # Phase D
    _write_phase_json(
        tmpdir,
        pid,
        "Q07",
        "phase_d_structured.json",
        {
            "project_id": pid,
            "findings": [
                {"finding_id": "F-001", "description": "缺少异常处理", "severity": "MAJOR", "related_req": "REQ-001"},
            ],
        },
    )

    return tmpdir


class TestBuildLifecycle:
    def test_builds_from_phase_a(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            _write_phase_json(
                output_dir,
                "p",
                "Q01",
                "phase_a_structured.json",
                {
                    "project_id": "p",
                    "requirements": [{"req_id": "REQ-001", "description": "test"}],
                    "semantic_expectations": [{"se_id": "SE-001", "description": "test"}],
                    "gaps": [{"gap_id": "GAP-001", "description": "test"}],
                    "open_items": [{"open_id": "OPEN-001", "question": "test"}],
                },
            )
            lc = build_lifecycle(output_dir, "p")
            assert "REQ-001" in lc
            assert "SE-001" in lc
            assert "GAP-001" in lc
            assert "OPEN-001" in lc
            assert lc["REQ-001"].id_type == "REQ"
            assert lc["GAP-001"].id_type == "GAP"

    def test_full_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_full_project(Path(tmpdir))
            lc = build_lifecycle(output_dir, "test-proj")

            # Phase A.5 覆盖度
            assert lc["REQ-001"].coverage_status == "COVERED"
            assert lc["REQ-002"].coverage_status == "MISSING"

            # Phase B EUT 关联
            assert lc["SE-001"].eut_ids == ["EUT-001"]
            assert lc["SE-002"].eut_ids == []

            # Phase D Finding 关联
            assert lc["REQ-001"].finding_ids == ["F-001"]
            assert lc["REQ-002"].finding_ids == []

            # GAP/OPEN 闭环
            assert lc["GAP-001"].closure_status == "已闭环"
            assert lc["OPEN-001"].closure_status == "未闭环"

    def test_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lc = build_lifecycle(Path(tmpdir), "nonexistent")
            assert lc == {}


class TestComputeCoverage:
    def test_full_coverage_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_full_project(Path(tmpdir))
            lc = build_lifecycle(output_dir, "test-proj")
            report = compute_coverage(lc, "test-proj")

            assert report.total_reqs == 2
            assert report.total_ses == 2
            assert report.total_gaps == 1
            assert report.total_opens == 1

            # REQ-001 COVERED, REQ-002 MISSING → 50%
            assert report.req_coverage_rate == 0.5

            # SE-001 COVERED, SE-002 PARTIAL → 50%
            assert report.se_coverage_rate == 0.5

            # SE-001 has EUT, SE-002 no → 50%
            assert report.test_coverage_rate == 0.5

            # REQ-001 has finding, REQ-002 no → 50%
            assert report.review_coverage_rate == 0.5

            # GAP-001 已闭环 → 100%
            assert report.gap_closure_rate == 1.0

            # OPEN-001 未闭环 → 0%
            assert report.open_closure_rate == 0.0

    def test_summary_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_full_project(Path(tmpdir))
            lc = build_lifecycle(output_dir, "test-proj")
            report = compute_coverage(lc, "test-proj")
            summary = report.summary()
            assert "覆盖率报告" in summary
            assert "REQ" in summary

    def test_empty_lifecycle(self):
        report = compute_coverage({}, "empty")
        assert report.total_reqs == 0
        assert report.req_coverage_rate == 0
        assert report.gap_closure_rate == 1.0  # 无 GAP 视为 100%


class TestRSMMutations:
    def test_add_mutation(self):
        lc = {"REQ-001": build_lifecycle.__wrapped__} if False else {}
        # 从空 lifecycle 开始
        lc = {}
        mut = RSMMutation(target_id="GAP-002", action="add", value="并发场景遗漏", reason="Critique 发现")
        lc, applied = apply_mutations(lc, [mut])
        assert "GAP-002" in lc
        assert lc["GAP-002"].id_type == "GAP"
        assert lc["GAP-002"].description == "并发场景遗漏"
        assert len(applied) == 1

    def test_modify_mutation(self):
        from dqg.schemas.rsm import RequirementLifecycle

        lc = {"REQ-001": RequirementLifecycle(req_id="REQ-001", id_type="REQ", description="旧描述")}
        mut = RSMMutation(target_id="REQ-001", action="modify", value="新描述", reason="不完整")
        lc, applied = apply_mutations(lc, [mut])
        assert lc["REQ-001"].description == "新描述"
        assert len(applied) == 1

    def test_delete_mutation(self):
        from dqg.schemas.rsm import RequirementLifecycle

        lc = {"REQ-001": RequirementLifecycle(req_id="REQ-001", id_type="REQ", description="误报")}
        mut = RSMMutation(target_id="REQ-001", action="delete", reason="误报")
        lc, applied = apply_mutations(lc, [mut])
        assert "REQ-001" not in lc
        assert len(applied) == 1

    def test_escalate_gap(self):
        from dqg.schemas.rsm import RequirementLifecycle

        lc = {"GAP-001": RequirementLifecycle(req_id="GAP-001", id_type="GAP", closure_status="已闭环")}
        mut = RSMMutation(target_id="GAP-001", action="escalate", reason="实际未解决")
        lc, _applied = apply_mutations(lc, [mut])
        assert lc["GAP-001"].closure_status == "未闭环"

    def test_skip_nonexistent_modify(self):
        lc = {}
        mut = RSMMutation(target_id="REQ-999", action="modify", value="x", reason="不存在")
        lc, applied = apply_mutations(lc, [mut])
        assert len(applied) == 0


class TestMutationsFromCritique:
    def test_extracts_rsm_mutations(self):
        critique_data = {
            "phase_id": "Q01",
            "items": [
                {"target_id": "REQ-001", "action": "modify", "reason": "不完整", "patch": "新描述", "confidence": 0.9},
                {"target_id": "GAP-002", "action": "add", "reason": "遗漏", "patch": "并发", "confidence": 0.8},
                {"target_id": "REQ-003", "action": "delete", "reason": "误报", "confidence": 0.3},  # 低置信度
                {"target_id": "F-001", "action": "modify", "reason": "非RSM ID", "confidence": 0.9},  # 非 RSM ID
            ],
        }
        mutations = mutations_from_critique(critique_data)
        assert len(mutations) == 2  # 只有 REQ-001 和 GAP-002（过滤低置信度和非 RSM ID）
        assert mutations[0].target_id == "REQ-001"
        assert mutations[1].target_id == "GAP-002"


class TestRSMPersistence:
    def test_save_and_load(self):
        from dqg.schemas.rsm import RequirementLifecycle

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            lc = {
                "REQ-001": RequirementLifecycle(req_id="REQ-001", id_type="REQ", description="创建工单"),
                "GAP-001": RequirementLifecycle(req_id="GAP-001", id_type="GAP", description="并发未定义"),
            }
            save_rsm(output_dir, "test-proj", lc)
            loaded = load_rsm(output_dir, "test-proj")
            assert "REQ-001" in loaded
            assert "GAP-001" in loaded
            assert loaded["REQ-001"].description == "创建工单"

    def test_load_fallback_to_build(self):
        """无持久化文件时 fallback 到从 Phase JSON 构建."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = _setup_full_project(Path(tmpdir))
            # 不调用 save_rsm，直接 load
            loaded = load_rsm(output_dir, "test-proj")
            assert "REQ-001" in loaded  # 从 Phase A JSON 构建
