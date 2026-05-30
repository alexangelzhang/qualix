"""Tests for Phase C weak assert sidecar generation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from qualix.commands.phase import cmd_execute
from qualix.context.context_loader import LoadedContext
from qualix.context.diff_context import DiffContext
from qualix.core.model_registry import get_model_profile
from qualix.core.state_machine import PhaseStatus, ProjectState, save_state

if TYPE_CHECKING:
    from pathlib import Path


def _prepare_state(output_dir: Path, project_id: str = "demo") -> None:
    state = ProjectState(project_id=project_id)
    state.phases["Q01"].status = PhaseStatus.APPROVED
    state.phases["Q05"].status = PhaseStatus.APPROVED
    state.phases["Q05a"].status = PhaseStatus.APPROVED
    state.phases["Q05b"].status = PhaseStatus.APPROVED
    save_state(output_dir, state)


def _empty_context() -> LoadedContext:
    return LoadedContext(
        phase_id="Q06",
        model=get_model_profile(None),
        budget_tokens=8_000,
    )


def _build_args(code_repo: str) -> SimpleNamespace:
    return SimpleNamespace(
        project_id="demo",
        phase="Q06",
        profile=None,
        model=None,
        code_repo=code_repo,
        base_branch="master",
        feature_branch="HEAD",
    )


def _stub_common_dependencies(monkeypatch) -> None:
    monkeypatch.setattr("qualix.context.context_loader.load_context", lambda *args, **kwargs: _empty_context())
    monkeypatch.setattr("qualix.reporting.telemetry.append_record", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.services.phase_service.write_phase_profile_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr("qualix.context.doc_summary.generate_summary_file", lambda *args, **kwargs: None)


def test_phase_c_execute_writes_weak_assert_sidecar_for_diff_test_files(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    repo_dir = tmp_path / "repo"
    test_dir = repo_dir / "src/test/java/demo"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "OrderServiceTest.java"
    test_file.write_text(
        """
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    @Test
    void shouldOnlyVerifyInvocation() {
        service.createOrder();
        verify(repository).save(order);
    }
}
""".strip(),
        encoding="utf-8",
    )

    _prepare_state(output_dir)
    _stub_common_dependencies(monkeypatch)

    diff_ctx = DiffContext(
        repo_path=str(repo_dir),
        changed_files=["src/test/java/demo/OrderServiceTest.java"],
        modified_files=["src/test/java/demo/OrderServiceTest.java"],
    )
    monkeypatch.setattr("qualix.context.diff_context.collect_diff_context", lambda *args, **kwargs: diff_ctx)

    exit_code = cmd_execute(_build_args(str(repo_dir)), output_dir)

    assert exit_code == 0

    internal_dir = output_dir / "demo" / "Q06" / "_internal"
    json_path = internal_dir / "_weak_assert_context.json"
    md_path = internal_dir / "_weak_assert_context.md"
    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["requested_test_file_count"] == 1
    assert payload["summary"]["scanned_test_file_count"] == 1
    assert payload["summary"]["weak_method_count"] == 1
    assert payload["files"][0]["methods"][0]["signals"][0]["code"] == "VERIFY_ONLY_NO_BUSINESS_ASSERT"
    assert "OrderServiceTest.java" in md_path.read_text(encoding="utf-8")


def test_phase_c_execute_writes_explanatory_notes_when_diff_has_no_test_files(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    _prepare_state(output_dir)
    _stub_common_dependencies(monkeypatch)

    diff_ctx = DiffContext(
        repo_path=str(repo_dir),
        changed_files=["src/main/java/demo/OrderService.java"],
        modified_files=["src/main/java/demo/OrderService.java"],
    )
    monkeypatch.setattr("qualix.context.diff_context.collect_diff_context", lambda *args, **kwargs: diff_ctx)

    exit_code = cmd_execute(_build_args(str(repo_dir)), output_dir)

    assert exit_code == 0

    internal_dir = output_dir / "demo" / "Q06" / "_internal"
    payload = json.loads((internal_dir / "_weak_assert_context.json").read_text(encoding="utf-8"))
    md_text = (internal_dir / "_weak_assert_context.md").read_text(encoding="utf-8")

    assert payload["summary"]["requested_test_file_count"] == 0
    assert payload["summary"]["scanned_test_file_count"] == 0
    assert payload["notes"] == ["diff 中未检测到测试文件，未执行弱断言扫描。"]
    assert "## Notes" in md_text
    assert "diff 中未检测到测试文件" in md_text
