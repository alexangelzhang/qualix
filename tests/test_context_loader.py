"""Tests for qualix.model_registry and qualix.context_loader."""

import json
from pathlib import Path

from qualix.context.context_loader import load_context
from qualix.core.model_registry import estimate_tokens, get_model_profile
from qualix.core.state_machine import PhaseStatus, ProjectState, load_state, save_state


class TestModelRegistry:
    def test_exact_match(self):
        p = get_model_profile("claude-opus-4")
        assert p.name == "claude-opus-4"
        assert p.context_window == 200_000

    def test_fuzzy_opus_1m(self):
        p = get_model_profile("claude-opus-4-6[1m]")
        assert p.name == "claude-opus-4-1m"
        assert p.context_window == 1_000_000

    def test_fuzzy_sonnet(self):
        p = get_model_profile("claude-sonnet-4-6")
        assert p.name == "claude-sonnet-4"

    def test_fuzzy_gpt(self):
        p = get_model_profile("gpt-4o-2024-05")
        assert p.name == "gpt-4o"

    def test_fuzzy_qwen(self):
        p = get_model_profile("qwen-max-latest")
        assert p.name == "qwen-max"

    def test_unknown_fallback(self):
        p = get_model_profile("some-random-model")
        assert p.name == "unknown"
        assert p.context_window == 128_000

    def test_none_fallback(self):
        p = get_model_profile(None)
        assert p.name == "unknown"

    def test_available_for_context(self):
        p = get_model_profile("claude-opus-4")
        assert p.available_for_context == 200_000 - 32_000 - 15_000


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_english(self):
        tokens = estimate_tokens("hello world this is a test")
        assert tokens > 0

    def test_chinese(self):
        tokens = estimate_tokens("这是一个中文测试")
        assert tokens > 0

    def test_mixed(self):
        tokens = estimate_tokens("Phase A 需求结构化 REQ-001")
        assert tokens > 0


def _setup_phase_a(output_dir: Path, project_id: str) -> None:
    """Helper: create Phase A artifacts and approved state."""
    # State
    state = ProjectState(project_id=project_id)
    state.phases["Q01"].status = PhaseStatus.APPROVED
    save_state(output_dir, state)

    # Structured JSON
    phase_dir = output_dir / project_id / "Q01"
    phase_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "project_id": project_id,
        "requirements": [
            {"req_id": "REQ-001", "description": "用户登录"},
        ],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "登录后跳转首页"},
        ],
        "gaps": [],
        "open_items": [],
    }
    (phase_dir / "phase_a_structured.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    # Markdown report
    (phase_dir / "phase_a_report.md").write_text(
        "# Phase A Report\n\n| REQ-001 | 用户登录 |\n", encoding="utf-8"
    )


class TestContextLoader:
    def test_no_upstream(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = ProjectState(project_id="TEST")
        save_state(output_dir, state)

        ctx = load_context(output_dir, "TEST", "Q01")
        assert ctx.chunks == []
        assert not ctx.truncated

    def test_loads_phase_a_for_b(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a")
        assert len(ctx.chunks) > 0
        assert any("结构化产物" in c.source for c in ctx.chunks)
        assert ctx.total_tokens > 0

    def test_full_text_concatenation(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a")
        text = ctx.full_text
        assert text.startswith("# Evidence Pack")
        assert "## 证据摘要" in text
        assert "## 关键引用" in text
        assert "REQ-001" in text

    def test_write_full_text_streams_to_file(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a")
        out_path = tmp_path / "streamed.md"

        ctx.write_full_text(out_path)

        written = out_path.read_text(encoding="utf-8")
        assert written.startswith("# Evidence Pack")
        assert "REQ-001" in written
        assert written == ctx.full_text

    def test_phase_a_uses_current_inputs_for_evidence_pack(self, tmp_path: Path, monkeypatch):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = ProjectState(project_id="TEST")
        save_state(output_dir, state)

        phase_dir = output_dir / "TEST" / "Q01" / "ingest"
        phase_dir.mkdir(parents=True, exist_ok=True)
        (phase_dir / "plain_text_summary.md").write_text(
            "# PRD 摘要\n\nREQ-001 用户登录成功后跳转首页\n",
            encoding="utf-8",
        )

        captured: list[str] = []

        def fake_render(phase: str, input_text: str, max_cases: int = 8) -> str:
            captured.append(input_text)
            return "## BUG_CASES\n\n### 反例 1: 登录后未跳首页 [漏报]"

        monkeypatch.setattr(
            "qualix.context.upstream_collector.render_relevant_cases_for_prompt",
            fake_render,
        )

        ctx = load_context(output_dir, "TEST", "Q01")

        assert any("Current Phase Q01 文档摘要" in chunk.source for chunk in ctx.chunks)
        assert any("Bug cases for Phase Q01" in chunk.source for chunk in ctx.chunks)
        assert captured and "REQ-001 用户登录成功后跳转首页" in captured[0]
        assert ctx.full_text.startswith("# Evidence Pack")
        assert "登录后未跳首页" in ctx.full_text

    def test_relevance_seed_is_lightweight(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a")
        seed = ctx.relevance_seed

        assert "REQ-001" in seed
        assert len(seed) <= 12_000

    def test_model_aware_budget(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a", model_name="claude-opus-4-1m")
        assert ctx.model.name == "claude-opus-4-1m"
        # Phase B execution=standard → budget 缩减到 60%（Reasoning Sandwich）
        assert ctx.budget_tokens > 500_000

    def test_summary(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        ctx = load_context(output_dir, "TEST", "Q05a")
        summary = ctx.summary
        assert "Phase Q05a" in summary
        assert "chunks" in summary

    def test_phase_a_no_upstream(self, tmp_path: Path):
        """Phase A has no dependencies, should load nothing."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = ProjectState(project_id="TEST")
        save_state(output_dir, state)

        ctx = load_context(output_dir, "TEST", "Q01")
        assert ctx.chunks == []

    def test_unapproved_upstream_skipped(self, tmp_path: Path):
        """Upstream Phase not approved should not be loaded."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        state = ProjectState(project_id="TEST")
        state.phases["Q01"].status = PhaseStatus.IN_PROGRESS
        save_state(output_dir, state)

        # Create artifacts anyway
        phase_dir = output_dir / "TEST" / "Q01"
        phase_dir.mkdir(parents=True)
        (phase_dir / "phase_a_structured.json").write_text('{"project_id": "TEST", "requirements": []}')

        ctx = load_context(output_dir, "TEST", "Q05a")
        assert len(ctx.chunks) == 1
        assert "Profile java-ddd-tmf" in ctx.chunks[0].source
        assert ctx.relevance_seed == ""

    def test_includes_profile_context(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        _setup_phase_a(output_dir, "TEST")

        state = load_state(output_dir, "TEST")
        state.profile_id = "go-service"
        save_state(output_dir, state)

        ctx = load_context(output_dir, "TEST", "Q05a")
        assert any("Profile go-service" in chunk.source for chunk in ctx.chunks)
