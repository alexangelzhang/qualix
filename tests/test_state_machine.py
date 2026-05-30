"""Tests for qualix.state_machine — Phase 状态机."""

from pathlib import Path

from qualix.core.state_machine import (
    PHASE_ORDER,
    PhaseStatus,
    ProjectState,
    approve_phase,
    check_gate,
    execute_phase,
    finalize_phase,
    get_available_phases,
    get_parallel_groups,
    load_state,
    save_state,
    skip_phase,
)


class TestProjectState:
    def test_initializes_all_phases(self):
        state = ProjectState(project_id="TEST")
        assert len(state.phases) == len(PHASE_ORDER)
        for phase_id in PHASE_ORDER:
            assert state.phases[phase_id].status == PhaseStatus.NOT_STARTED

    def test_save_and_load(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = ProjectState(project_id="TEST")
        save_state(output_dir, state)

        loaded = load_state(output_dir, "TEST")
        assert loaded.project_id == "TEST"
        assert len(loaded.phases) == len(PHASE_ORDER)

    def test_load_nonexistent_creates_new(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = load_state(output_dir, "NEW")
        assert state.project_id == "NEW"
        assert state.phases["Q01"].status == PhaseStatus.NOT_STARTED


class TestCheckGate:
    def test_phase_a_no_deps(self):
        state = ProjectState(project_id="TEST")
        assert check_gate(state, "Q01") == []

    def test_phase_b_needs_a(self):
        state = ProjectState(project_id="TEST")
        errors = check_gate(state, "Q05")
        assert len(errors) == 1
        assert "Q01" in errors[0]

    def test_phase_b_passes_after_a_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        assert check_gate(state, "Q05") == []

    def test_already_approved_blocked(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        errors = check_gate(state, "Q01")
        assert any("已经 approved" in e for e in errors)

    def test_unknown_phase(self):
        state = ProjectState(project_id="TEST")
        errors = check_gate(state, "Z")
        assert any("未知" in e for e in errors)


class TestExecutePhase:
    def test_execute_a(self):
        state = ProjectState(project_id="TEST")
        errors = execute_phase(state, "Q01")
        assert errors == []
        assert state.phases["Q01"].status == PhaseStatus.IN_PROGRESS
        assert state.phases["Q01"].started_at is not None

    def test_execute_b_without_a(self):
        state = ProjectState(project_id="TEST")
        errors = execute_phase(state, "Q05")
        assert len(errors) > 0

    def test_execute_already_in_progress(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "Q01")
        errors = execute_phase(state, "Q01")
        assert len(errors) > 0


class TestFinalizePhase:
    def test_finalize_success(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "Q01")
        errors = finalize_phase(state, "Q01")
        assert errors == []
        assert state.phases["Q01"].status == PhaseStatus.PENDING_REVIEW
        assert state.phases["Q01"].finished_at is not None
        assert state.phases["Q01"].duration_seconds is not None

    def test_finalize_with_validation_errors(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "Q01")
        errors = finalize_phase(state, "Q01", ["missing REQ-001"])
        assert errors == []
        assert state.phases["Q01"].validation_errors == ["missing REQ-001"]

    def test_finalize_not_in_progress(self):
        state = ProjectState(project_id="TEST")
        errors = finalize_phase(state, "Q01")
        assert len(errors) > 0


class TestApprovePhase:
    def test_approve_success(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "Q01")
        finalize_phase(state, "Q01")
        errors = approve_phase(state, "Q01", "LGTM")
        assert errors == []
        assert state.phases["Q01"].status == PhaseStatus.APPROVED
        assert state.phases["Q01"].comment == "LGTM"

    def test_approve_not_pending(self):
        state = ProjectState(project_id="TEST")
        errors = approve_phase(state, "Q01")
        assert len(errors) > 0


class TestSkipPhase:
    def test_skip_success(self):
        state = ProjectState(project_id="TEST")
        errors = skip_phase(state, "Q03", "not needed")
        assert errors == []
        assert state.phases["Q03"].status == PhaseStatus.SKIPPED

    def test_skip_approved_fails(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        errors = skip_phase(state, "Q01")
        assert len(errors) > 0


class TestGetAvailablePhases:
    def test_initial_only_a(self):
        state = ProjectState(project_id="TEST")
        available = get_available_phases(state)
        assert available == ["Q01"]

    def test_after_a_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        available = get_available_phases(state)
        # Q01 approved unlocks Q02 (depends Q01) and Q05 (depends Q01)
        # Q03 depends on Q02 — not yet available
        # Q04 depends on Q03 — not yet available
        # Q06 depends on Q05 — not yet available
        # Q07 depends on Q04+Q03 — not yet available
        assert "Q02" in available
        assert "Q03" not in available
        assert "Q05" in available
        assert "Q04" not in available
        assert "Q06" not in available
        assert "Q07" not in available

    def test_after_a3_skipped(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        state.phases["Q02"].status = PhaseStatus.SKIPPED
        available = get_available_phases(state)
        # Q03 and Q04 both unlocked when Q02 is skipped (parallel_with each other)
        assert "Q03" in available
        assert "Q04" in available

    def test_after_a6_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        state.phases["Q02"].status = PhaseStatus.SKIPPED
        state.phases["Q03"].status = PhaseStatus.APPROVED
        available = get_available_phases(state)
        assert "Q04" in available

    def test_all_done(self):
        state = ProjectState(project_id="TEST")
        for pid in PHASE_ORDER:
            state.phases[pid].status = PhaseStatus.APPROVED
        assert get_available_phases(state) == []


class TestGetParallelGroups:
    def test_q03_q04_parallel_after_q02_skipped(self):
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.APPROVED
        state.phases["Q02"].status = PhaseStatus.SKIPPED
        groups = get_parallel_groups(state)
        # Q03 and Q04 should be in the same parallel group
        parallel_group = next((g for g in groups if len(g) > 1), None)
        assert parallel_group is not None
        assert set(parallel_group) == {"Q03", "Q04"}

    def test_initial_no_parallel(self):
        state = ProjectState(project_id="TEST")
        groups = get_parallel_groups(state)
        assert groups == [["Q01"]]


class TestResetPhase:
    def test_reset_from_approved_clears_all_fields(self):
        """reset 必须清所有执行/评审/审批字段，否则会残留污染下轮 execute."""
        from qualix.core.state_machine import reset_phase

        state = ProjectState(project_id="TEST")
        ps = state.phases["Q06"]
        ps.status = PhaseStatus.APPROVED
        ps.run_status = "ok"
        ps.started_at = "2026-01-01T00:00:00"
        ps.finished_at = "2026-01-01T00:05:00"
        ps.approved_at = "2026-01-01T00:10:00"
        ps.duration_seconds = 300.0
        ps.comment = "审批通过"
        ps.validation_errors = ["legacy error"]
        ps.judge_score = 4.5
        ps.judge_dimensions = {"overall_quality": 4.0}
        ps.judge_passed = True
        ps.judged_at = "2026-01-01T00:08:00"

        errors = reset_phase(state, "Q06")

        assert errors == []
        ps = state.phases["Q06"]
        assert ps.status == PhaseStatus.NOT_STARTED
        assert ps.run_status is None
        assert ps.started_at is None
        assert ps.finished_at is None
        assert ps.approved_at is None
        assert ps.duration_seconds is None
        assert ps.comment is None
        assert ps.validation_errors == []
        assert ps.judge_score is None
        assert ps.judge_dimensions == {}
        assert ps.judge_passed is None
        assert ps.judged_at is None

    def test_reset_already_clean_returns_info(self):
        """真正的 not_started（字段全默认）应返回 info，且不改动 state."""
        from qualix.core.state_machine import reset_phase

        state = ProjectState(project_id="TEST")
        errors = reset_phase(state, "Q06")
        assert errors == ["Phase Q06 已经是 not_started 状态"]

    def test_reset_not_started_but_dirty_fields_still_resets(self):
        """status 是 not_started 但残留了其他字段（比如部分 reset 过）仍需真正 reset."""
        from qualix.core.state_machine import reset_phase

        state = ProjectState(project_id="TEST")
        ps = state.phases["Q06"]
        # status 是 not_started 但 approved_at 残留 —— 这是老 bug 的典型场景
        ps.status = PhaseStatus.NOT_STARTED
        ps.approved_at = "2026-01-01T00:10:00"
        ps.judge_score = 4.5

        errors = reset_phase(state, "Q06")

        assert errors == []
        assert state.phases["Q06"].approved_at is None
        assert state.phases["Q06"].judge_score is None

    def test_reset_unknown_phase(self):
        from qualix.core.state_machine import reset_phase

        state = ProjectState(project_id="TEST")
        errors = reset_phase(state, "QXX")
        assert errors == ["未知的 Phase: QXX"]
