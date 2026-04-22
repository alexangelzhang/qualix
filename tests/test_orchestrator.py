"""Tests for dqg.orchestrator."""

from pathlib import Path

from dqg.services.orchestrator import (
    PHASES,
    PhaseStatus,
    build_next_command,
    detect_phase_status,
    discover_projects,
    find_next_phase,
)


def _make_output(tmp_path: Path, project_id: str, phases: list[str]) -> Path:
    """Helper: create output dir with completed phase artifacts."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    suffix_map = {p["id"]: p for p in PHASES}
    key_file_map = {p["id"]: p["key_file"] for p in PHASES}

    for phase_id in phases:
        phase = suffix_map[phase_id]
        phase_dir = output_dir / project_id / phase['dir_suffix']
        phase_dir.mkdir(parents=True)
        (phase_dir / key_file_map[phase_id]).write_text("# report", encoding="utf-8")

    return output_dir


class TestDetectPhaseStatus:
    def test_completed_phase(self, tmp_path: Path):
        output_dir = _make_output(tmp_path, "PROJ1", ["Q01"])
        status = detect_phase_status(output_dir, "PROJ1", PHASES[0])
        assert status.completed is True
        assert status.phase_id == "Q01"
        assert status.key_file_path is not None

    def test_not_started_phase(self, tmp_path: Path):
        output_dir = _make_output(tmp_path, "PROJ1", [])
        status = detect_phase_status(output_dir, "PROJ1", PHASES[0])
        assert status.completed is False
        assert status.dir_path is None

    def test_in_progress_phase(self, tmp_path: Path):
        """Dir exists but key file missing."""
        output_dir = _make_output(tmp_path, "PROJ1", [])
        phase_dir = output_dir / "PROJ1" / "Q01"
        phase_dir.mkdir(parents=True, exist_ok=True)
        (phase_dir / "ingest.json").write_text("{}", encoding="utf-8")

        status = detect_phase_status(output_dir, "PROJ1", PHASES[0])
        assert status.completed is False
        assert status.dir_path is not None


class TestFindNextPhase:
    def test_first_phase_when_nothing_done(self):
        statuses = [
            PhaseStatus(phase_id=p["id"], name=p["name"], completed=False)
            for p in PHASES
        ]
        next_phase = find_next_phase(statuses, [])
        assert next_phase is not None
        assert next_phase["id"] == "Q01"

    def test_skip_to_b_after_a(self):
        statuses = []
        for p in PHASES:
            statuses.append(
                PhaseStatus(
                    phase_id=p["id"],
                    name=p["name"],
                    completed=(p["id"] == "Q01"),
                )
            )
        next_phase = find_next_phase(statuses, [])
        assert next_phase is not None
        # A.5, A.6, B all depend on A — first one in order is A.5
        assert next_phase["id"] == "Q04"

    def test_all_completed(self):
        statuses = [
            PhaseStatus(phase_id=p["id"], name=p["name"], completed=True)
            for p in PHASES
        ]
        assert find_next_phase(statuses, []) is None

    def test_skip_phase(self):
        statuses = [
            PhaseStatus(phase_id=p["id"], name=p["name"], completed=(p["id"] == "Q01"))
            for p in PHASES
        ]
        next_phase = find_next_phase(statuses, ["Q04"])
        assert next_phase is not None
        assert next_phase["id"] == "Q03"


class TestBuildNextCommand:
    def test_includes_input_files(self):
        statuses = [
            PhaseStatus(
                phase_id="Q01",
                name="需求结构化",
                completed=True,
                key_file_path="/output/PROJ1/Q01/phase_a_report.md",
            ),
        ]
        phase_b = PHASES[3]  # Phase B
        cmd = build_next_command(phase_b, statuses, "PROJ1")
        assert "/ut-generator" in cmd
        assert "phase_a_report.md" in cmd


class TestDiscoverProjects:
    def test_discovers_standard_naming(self, tmp_path: Path):
        output_dir = _make_output(tmp_path, "ABC", ["Q01", "Q05"])
        projects = discover_projects(output_dir)
        assert len(projects) == 1
        assert projects[0]["id"] == "ABC"
        assert projects[0]["naming"] == "standard"

    def test_empty_output(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        projects = discover_projects(output_dir)
        assert projects == []
