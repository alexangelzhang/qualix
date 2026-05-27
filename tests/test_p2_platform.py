"""P2 平台化三项功能测试：Bug Case compress / Evolution Store 时间衰减 / Skill Reflector 输入契约."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Item 1: Bug Case compress
# ---------------------------------------------------------------------------


def _insert_cases(output_dir: Path, cases: list[dict]) -> None:
    from dqg.store.bug_cases import upsert_bug_case

    for c in cases:
        upsert_bug_case(output_dir, c)


def _make_case(case_id: str, severity: str = "medium", status: str = "open", days_ago: int = 0) -> dict:
    created = (datetime.now(tz=UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return {"case_id": case_id, "phase": "Q01", "severity": severity, "status": status, "created_at": created}


class TestBugCaseCompress:
    def test_no_compress_below_threshold(self, tmp_path: Path) -> None:
        from dqg.store.bug_cases import COMPRESS_THRESHOLD, compress_bug_cases

        # 插入 3 条远少于阈值
        _insert_cases(tmp_path, [_make_case(f"C-{i}") for i in range(3)])
        result = compress_bug_cases(tmp_path, threshold=COMPRESS_THRESHOLD)
        assert result["deleted"] == 0
        assert result["total_after"] == 3

    def test_compress_triggers_above_threshold(self, tmp_path: Path) -> None:
        from dqg.store.bug_cases import compress_bug_cases

        # 插入 10 条，阈值设 5，保留 4
        cases = [_make_case(f"C-{i}", status="resolved", days_ago=i * 10) for i in range(10)]
        _insert_cases(tmp_path, cases)
        result = compress_bug_cases(tmp_path, threshold=5, keep=4)
        assert result["total_before"] == 10
        assert result["deleted"] == 6
        assert result["total_after"] == 4

    def test_open_cases_protected_from_first_deletion(self, tmp_path: Path) -> None:
        """open 案例应比 resolved 案例更晚被删除."""
        from dqg.store.bug_cases import compress_bug_cases, query_bug_cases

        cases = [_make_case(f"OPEN-{i}", status="open", days_ago=300) for i in range(3)] + [
            _make_case(f"RESOLVED-{i}", status="resolved", days_ago=5) for i in range(3)
        ]
        _insert_cases(tmp_path, cases)
        compress_bug_cases(tmp_path, threshold=5, keep=3)
        remaining = query_bug_cases(tmp_path, limit=100)
        remaining_ids = {r["case_id"] for r in remaining}
        # resolved 的应该先被删，open 的应该保留
        assert any("OPEN" in cid for cid in remaining_ids)

    def test_high_severity_scored_higher(self, tmp_path: Path) -> None:
        """同龄案例中，critical 应比 low 更晚被删."""
        from dqg.store.bug_cases import compress_bug_cases, query_bug_cases

        cases = [_make_case(f"CRIT-{i}", severity="critical", status="resolved", days_ago=100) for i in range(3)] + [
            _make_case(f"LOW-{i}", severity="low", status="resolved", days_ago=100) for i in range(3)
        ]
        _insert_cases(tmp_path, cases)
        compress_bug_cases(tmp_path, threshold=5, keep=3)
        remaining = {r["case_id"] for r in query_bug_cases(tmp_path, limit=100)}
        assert any("CRIT" in cid for cid in remaining)


# ---------------------------------------------------------------------------
# Item 2: Evolution Store 时间衰减
# ---------------------------------------------------------------------------


class TestEvolutionStoreDecay:
    def _write_evolution_file(self, lineage_dir: Path, name: str, timestamp: str) -> Path:
        lineage_dir.mkdir(parents=True, exist_ok=True)
        p = lineage_dir / f"evolution_{name}.json"
        p.write_text(json.dumps({"phase": "Q01", "timestamp": timestamp}), encoding="utf-8")
        return p

    def test_cleanup_removes_stale_files(self, tmp_path: Path) -> None:
        from dqg.tracking.skill_evolution import cleanup_stale_evolution

        lineage_dir = tmp_path / "proj" / "_skill_evolution"
        now = datetime.now(tz=UTC)
        # 旧文件（100天前）
        old_ts = (now - timedelta(days=100)).isoformat()
        self._write_evolution_file(lineage_dir, "Q01_old", old_ts)
        # 新文件（10天前）
        new_ts = (now - timedelta(days=10)).isoformat()
        self._write_evolution_file(lineage_dir, "Q01_new", new_ts)

        result = cleanup_stale_evolution(tmp_path, "proj", max_age_days=90)
        assert result["deleted"] == 1
        assert result["kept"] == 1
        assert not (lineage_dir / "evolution_Q01_old.json").exists()
        assert (lineage_dir / "evolution_Q01_new.json").exists()

    def test_cleanup_missing_dir_returns_zero(self, tmp_path: Path) -> None:
        from dqg.tracking.skill_evolution import cleanup_stale_evolution

        result = cleanup_stale_evolution(tmp_path, "nonexistent_project")
        assert result == {"scanned": 0, "deleted": 0, "kept": 0}

    def test_prune_stale_experiments_removes_old_rows(self, tmp_path: Path) -> None:
        from dqg.store.experiments import insert_experiment, prune_stale_experiments, query_experiments

        # 插入一条 100 天前的记录
        old_exp = {
            "experiment_id": "EXP-OLD",
            "skill_file": "skills/q01/SKILL.md",
            "phase_id": "Q01",
            "cycle": 1,
            "benchmark_case": "BC-001",
            "judge_score": 3.5,
            "baseline_score": 3.0,
            "delta": 0.5,
            "accepted": False,
        }
        insert_experiment(tmp_path, old_exp)
        # 手动把 created_at 改到 100 天前
        from dqg.store.core import get_connection

        with get_connection(tmp_path) as conn:
            conn.execute(
                "UPDATE experiments SET created_at = datetime('now', '-100 days') WHERE experiment_id = ?",
                ("EXP-OLD",),
            )
        deleted = prune_stale_experiments(tmp_path, max_age_days=90)
        assert deleted == 1
        remaining = query_experiments(tmp_path, limit=100)
        assert not any(e["experiment_id"] == "EXP-OLD" for e in remaining)

    def test_prune_keeps_recent_experiments(self, tmp_path: Path) -> None:
        from dqg.store.experiments import insert_experiment, prune_stale_experiments, query_experiments

        recent_exp = {
            "experiment_id": "EXP-RECENT",
            "skill_file": "skills/q01/SKILL.md",
            "phase_id": "Q01",
            "cycle": 1,
            "benchmark_case": "BC-002",
            "judge_score": 4.0,
            "baseline_score": 3.5,
            "delta": 0.5,
            "accepted": True,
        }
        insert_experiment(tmp_path, recent_exp)
        deleted = prune_stale_experiments(tmp_path, max_age_days=90)
        assert deleted == 0
        remaining = query_experiments(tmp_path, limit=100)
        assert any(e["experiment_id"] == "EXP-RECENT" for e in remaining)


# ---------------------------------------------------------------------------
# Item 3: Skill Reflector 输入契约
# ---------------------------------------------------------------------------


class TestSkillReflectorInputContract:
    def _make_jr(self, descriptions: list[str], with_excerpt: bool = False) -> list[dict]:
        issues = []
        for d in descriptions:
            issue: dict = {"severity": "high", "description": d}
            if with_excerpt:
                issue["source_excerpt"] = "原始报告片段：" + d[:30]
            issues.append(issue)
        return [{"verdict": "FAIL", "overall": 2.0, "issues": issues}]

    def test_contract_passes_with_long_descriptions(self) -> None:
        from dqg.tracking.skill_reflector import _check_evidence_quality

        jr = self._make_jr(["EUT 矩阵里 SE-001 没有对应的 Exception 路径测试用例，并发场景未覆盖"])
        with_ev, total, warning = _check_evidence_quality(jr)
        assert total == 1
        assert with_ev == 1
        assert warning == ""

    def test_contract_passes_with_source_excerpt(self) -> None:
        from dqg.tracking.skill_reflector import _check_evidence_quality

        jr = self._make_jr(["短描述"], with_excerpt=True)
        _, _, warning = _check_evidence_quality(jr)
        assert warning == ""

    def test_contract_warns_on_low_evidence_ratio(self) -> None:
        from dqg.tracking.skill_reflector import _check_evidence_quality

        # 1 条有效（长描述），3 条纯摘要（短描述）
        jr = self._make_jr(["EUT 矩阵缺少 SE-001 的异常路径覆盖，导致并发场景漏测"]) + self._make_jr(["差", "坏", "错"])
        _, _, warning = _check_evidence_quality(jr)
        assert "警告" in warning

    def test_contract_violation_blocks_reflect(self) -> None:
        """0 证据时 reflect 应返回 actionable=False."""
        from dqg.tracking.skill_reflector import SkillReflector

        reflector = SkillReflector(phase="Q01", project_id="test")
        jr = self._make_jr(["差", "坏"])  # 纯摘要，<30 chars
        result = reflector.reflect(jr)
        assert not result.actionable
        assert result.evidence_warning != ""
        assert "违反" in result.evidence_warning

    def test_contract_warning_preserved_in_result(self) -> None:
        """evidence_warning 应传递到最终 ReflectResult."""
        from unittest.mock import patch

        from dqg.tracking.skill_reflector import SkillReflector

        reflector = SkillReflector(phase="Q01", project_id="test")
        # 1 条长描述（有效） + 3 条短描述（摘要）→ 25% < 50% → warning 但不阻断
        jr = self._make_jr(["EUT 矩阵里 SE-001 缺少对应的异常路径测试，并发写入场景未覆盖"]) + self._make_jr(
            ["差", "坏", "错"]
        )

        with patch.object(reflector, "_classify_root_cause", return_value=("SKILL_RULE", "", "补充测试")):
            result = reflector.reflect(jr)
        assert result.evidence_warning != ""
        assert "警告" in result.evidence_warning
