from __future__ import annotations

import dqg.services.phase_service as phase_service


def test_write_phase_profile_manifest_writes_relevance_matched_bug_cases(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    phase_dir = output_dir / "demo" / "Q06"
    (phase_dir / "ingest").mkdir(parents=True, exist_ok=True)
    (phase_dir / "ingest" / "plain_text_summary.md").write_text("权限校验失败，需要补拦截", encoding="utf-8")

    captured: list[tuple[str, str, int]] = []

    def fake_render(phase: str, input_text: str, max_cases: int = 8) -> str:
        captured.append((phase, input_text, max_cases))
        return "## BUG_CASES\n\n### 反例 1: 权限缺失 [漏报]"

    monkeypatch.setattr(phase_service, "render_relevant_cases_for_prompt", fake_render)

    phase_service.write_phase_profile_manifest(
        output_dir,
        "demo",
        "Q06",
        "java-ddd-tmf",
        relevance_text="权限校验失败",
    )

    bug_cases_path = phase_dir / "_internal" / "_bug_cases.md"
    assert bug_cases_path.exists()
    assert "权限缺失" in bug_cases_path.read_text(encoding="utf-8")
    assert captured
    assert captured[0][0] == "Q06"
    assert "权限校验失败" in captured[0][1]


def test_write_phase_profile_manifest_removes_stale_bug_case_files_when_no_relevance(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    phase_dir = output_dir / "demo" / "Q05"
    internal_dir = phase_dir / "_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)
    (internal_dir / "_bug_cases.md").write_text("stale internal", encoding="utf-8")
    (phase_dir / "_bug_cases.md").write_text("stale legacy", encoding="utf-8")

    def fake_render(phase: str, input_text: str, max_cases: int = 8) -> str:
        raise AssertionError("renderer should not run without relevance input")

    monkeypatch.setattr(phase_service, "render_relevant_cases_for_prompt", fake_render)

    phase_service.write_phase_profile_manifest(output_dir, "demo", "Q05", "java-ddd-tmf")

    assert not (internal_dir / "_bug_cases.md").exists()
    assert not (phase_dir / "_bug_cases.md").exists()
