"""Tests for dqg.state_machine — Phase 状态机."""

from pathlib import Path

from dqg.core.state_machine import (
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
        assert state.phases["A"].status == PhaseStatus.NOT_STARTED


class TestCheckGate:
    def test_phase_a_no_deps(self):
        state = ProjectState(project_id="TEST")
        assert check_gate(state, "A") == []

    def test_phase_b_needs_a(self):
        state = ProjectState(project_id="TEST")
        errors = check_gate(state, "B")
        assert len(errors) == 1
        assert "Phase A" in errors[0]

    def test_phase_b_passes_after_a_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        assert check_gate(state, "B") == []

    def test_already_approved_blocked(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        errors = check_gate(state, "A")
        assert any("已经 approved" in e for e in errors)

    def test_unknown_phase(self):
        state = ProjectState(project_id="TEST")
        errors = check_gate(state, "Z")
        assert any("未知" in e for e in errors)


class TestExecutePhase:
    def test_execute_a(self):
        state = ProjectState(project_id="TEST")
        errors = execute_phase(state, "A")
        assert errors == []
        assert state.phases["A"].status == PhaseStatus.IN_PROGRESS
        assert state.phases["A"].started_at is not None

    def test_execute_b_without_a(self):
        state = ProjectState(project_id="TEST")
        errors = execute_phase(state, "B")
        assert len(errors) > 0

    def test_execute_already_in_progress(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "A")
        errors = execute_phase(state, "A")
        assert len(errors) > 0


class TestFinalizePhase:
    def test_finalize_success(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "A")
        errors = finalize_phase(state, "A")
        assert errors == []
        assert state.phases["A"].status == PhaseStatus.PENDING_REVIEW
        assert state.phases["A"].finished_at is not None
        assert state.phases["A"].duration_seconds is not None

    def test_finalize_with_validation_errors(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "A")
        errors = finalize_phase(state, "A", ["missing REQ-001"])
        assert errors == []
        assert state.phases["A"].validation_errors == ["missing REQ-001"]

    def test_finalize_not_in_progress(self):
        state = ProjectState(project_id="TEST")
        errors = finalize_phase(state, "A")
        assert len(errors) > 0


class TestApprovePhase:
    def test_approve_success(self):
        state = ProjectState(project_id="TEST")
        execute_phase(state, "A")
        finalize_phase(state, "A")
        errors = approve_phase(state, "A", "LGTM")
        assert errors == []
        assert state.phases["A"].status == PhaseStatus.APPROVED
        assert state.phases["A"].comment == "LGTM"

    def test_approve_not_pending(self):
        state = ProjectState(project_id="TEST")
        errors = approve_phase(state, "A")
        assert len(errors) > 0


class TestSkipPhase:
    def test_skip_success(self):
        state = ProjectState(project_id="TEST")
        errors = skip_phase(state, "A.6", "not needed")
        assert errors == []
        assert state.phases["A.6"].status == PhaseStatus.SKIPPED

    def test_skip_approved_fails(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        errors = skip_phase(state, "A")
        assert len(errors) > 0


class TestGetAvailablePhases:
    def test_initial_only_a(self):
        state = ProjectState(project_id="TEST")
        available = get_available_phases(state)
        assert available == ["A"]

    def test_after_a_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        available = get_available_phases(state)
        # A.3 unlocked after A; A.5/A.6 still locked (depend on A.3)
        assert "A.3" in available
        assert "A.5" not in available
        assert "A.6" not in available
        assert "B" in available
        assert "C" in available
        assert "D" in available

    def test_after_a3_skipped(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        state.phases["A.3"].status = PhaseStatus.SKIPPED
        available = get_available_phases(state)
        # A.6 unlocked when A.3 is skipped
        assert "A.6" in available
        assert "A.5" not in available

    def test_after_a6_approved(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        state.phases["A.3"].status = PhaseStatus.SKIPPED
        state.phases["A.6"].status = PhaseStatus.APPROVED
        available = get_available_phases(state)
        assert "A.5" in available

    def test_all_done(self):
        state = ProjectState(project_id="TEST")
        for pid in PHASE_ORDER:
            state.phases[pid].status = PhaseStatus.APPROVED
        assert get_available_phases(state) == []


class TestGetParallelGroups:
    def test_a6_before_a5_sequential(self):
        state = ProjectState(project_id="TEST")
        state.phases["A"].status = PhaseStatus.APPROVED
        state.phases["A.3"].status = PhaseStatus.SKIPPED
        groups = get_parallel_groups(state)
        # A.6 should appear before A.5 (sequential, not parallel)
        phase_ids_in_order = [g[0] for g in groups if len(g) == 1]
        assert "A.6" in phase_ids_in_order
        assert "A.5" not in phase_ids_in_order  # A.5 locked until A.6 done

    def test_initial_no_parallel(self):
        state = ProjectState(project_id="TEST")
        groups = get_parallel_groups(state)
        assert groups == [["A"]]
