from __future__ import annotations

import json
from pathlib import Path

import pytest

import dqg.reporting.perf_tracker as perf_tracker
from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS
from dqg.path_utils import resolve_context_files, resolve_effective_context_files


@pytest.fixture(autouse=True)
def _clear_perf_token_cache() -> None:
    perf_tracker._FILE_TOKEN_CACHE.clear()
    yield
    perf_tracker._FILE_TOKEN_CACHE.clear()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _phase_root(output_dir: Path, project_id: str, phase_id: str) -> Path:
    return output_dir / project_id / PHASE_DEFS[phase_id]["dir_suffix"]


def test_resolve_context_files_supports_legacy_layout(tmp_path: Path) -> None:
    phase_root = tmp_path / "output" / "demo" / "phaseB"
    expected = [
        _write(phase_root / "_upstream_context.md", "upstream"),
        _write(phase_root / "_profile_context.md", "profile"),
        _write(phase_root / "_bug_cases.md", "bug"),
        _write(phase_root / "_diff_context.md", "diff"),
        _write(phase_root / "image_semantics.md", "image"),
        _write(phase_root / "plain_text_summary.md", "summary"),
        _write(phase_root / "plain_text.txt", "plain"),
    ]

    resolved = resolve_context_files(phase_root)

    assert resolved == expected


def test_resolve_context_files_supports_new_layout(tmp_path: Path) -> None:
    phase_root = tmp_path / "output" / "demo" / "phaseB"
    expected = [
        _write(phase_root / "_internal" / "_upstream_context.md", "upstream"),
        _write(phase_root / "_internal" / "_profile_context.md", "profile"),
        _write(phase_root / "_internal" / "_bug_cases.md", "bug"),
        _write(phase_root / "_internal" / "_diff_context.md", "diff"),
        _write(phase_root / "image_semantics.md", "image"),
        _write(phase_root / "ingest" / "plain_text_summary.md", "summary"),
        _write(phase_root / "ingest" / "plain_text.txt", "plain"),
    ]

    resolved = resolve_context_files(phase_root)

    assert resolved == expected


def test_resolve_effective_context_files_keeps_legacy_layout_without_upstream(tmp_path: Path) -> None:
    phase_root = tmp_path / "output" / "demo" / "phaseB"
    expected = [
        _write(phase_root / "_profile_context.md", "profile"),
        _write(phase_root / "_bug_cases.md", "bug"),
        _write(phase_root / "_diff_context.md", "diff"),
        _write(phase_root / "image_semantics.md", "image"),
        _write(phase_root / "plain_text_summary.md", "summary"),
        _write(phase_root / "plain_text.txt", "plain"),
    ]

    resolved = resolve_effective_context_files(phase_root)

    assert resolved == expected


def test_resolve_effective_context_files_deduplicates_new_layout_with_upstream(tmp_path: Path) -> None:
    phase_root = tmp_path / "output" / "demo" / "phaseB"
    expected = [
        _write(phase_root / "_internal" / "_upstream_context.md", "upstream"),
        _write(phase_root / "image_semantics.md", "image"),
        _write(phase_root / "ingest" / "plain_text_summary.md", "summary"),
        _write(phase_root / "ingest" / "plain_text.txt", "plain"),
    ]
    _write(phase_root / "_internal" / "_profile_context.md", "profile")
    _write(phase_root / "_internal" / "_bug_cases.md", "bug")
    _write(phase_root / "_internal" / "_diff_context.md", "diff")

    resolved = resolve_effective_context_files(phase_root)

    assert resolved == expected


def test_collect_phase_metrics_counts_tokens_sizes_and_reuses_cache(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    project_id = "demo"
    phase_id = "B"
    phase_root = _phase_root(output_dir, project_id, phase_id)

    upstream_text = "upstream block\n" * 4
    image_text = "image semantics\n" * 5
    summary_text = "summary block\n" * 6
    report_text = "report block\n" * 7
    structured_text = json.dumps({"items": ["a", "b", "c"]}, ensure_ascii=False)

    created_files = [
        _write(phase_root / "_internal" / "_upstream_context.md", upstream_text),
        _write(phase_root / "_internal" / "_profile_context.md", "profile should be excluded"),
        _write(phase_root / "_internal" / "_bug_cases.md", "bug should be excluded"),
        _write(phase_root / "_internal" / "_diff_context.md", "diff should be excluded"),
        _write(phase_root / "image_semantics.md", image_text),
        _write(phase_root / "ingest" / "plain_text_summary.md", summary_text),
        _write(phase_root / REPORT_MAP[phase_id], report_text),
        _write(phase_root / STRUCTURED_JSON_MAP[phase_id], structured_text),
    ]

    skill_path = Path(PHASE_DEFS[phase_id]["skill"])
    skill_text = skill_path.read_text(encoding="utf-8")

    calls: list[str] = []

    def fake_estimate_tokens(text: str) -> int:
        calls.append(text)
        return len(text)

    monkeypatch.setattr(perf_tracker, "estimate_tokens", fake_estimate_tokens)

    metrics_first = perf_tracker.collect_phase_metrics(output_dir, project_id, phase_id, duration_seconds=12.5)
    calls_after_first = len(calls)
    metrics_second = perf_tracker.collect_phase_metrics(output_dir, project_id, phase_id, duration_seconds=12.5)

    expected_input_tokens = len(upstream_text) + len(image_text) + len(summary_text) + len(skill_text)
    expected_output_tokens = len(report_text) + len(structured_text)
    expected_total_size = round(sum(path.stat().st_size for path in created_files) / 1024, 1)

    assert metrics_first["project_id"] == metrics_second["project_id"]
    assert metrics_first["phase_id"] == metrics_second["phase_id"]
    assert metrics_first["input_tokens"] == metrics_second["input_tokens"]
    assert metrics_first["output_tokens"] == metrics_second["output_tokens"]
    assert metrics_first["total_tokens"] == metrics_second["total_tokens"]
    assert metrics_first["input_files"] == metrics_second["input_files"]
    assert metrics_first["output_files"] == metrics_second["output_files"]
    assert metrics_first["output_file_count"] == metrics_second["output_file_count"]
    assert metrics_first["output_dir_size_kb"] == metrics_second["output_dir_size_kb"]
    assert metrics_first["tokens_per_second"] == metrics_second["tokens_per_second"]
    assert metrics_first["cost_estimate_usd"] == metrics_second["cost_estimate_usd"]
    assert metrics_first["input_tokens"] == expected_input_tokens
    assert metrics_first["output_tokens"] == expected_output_tokens
    assert metrics_first["total_tokens"] == expected_input_tokens + expected_output_tokens
    assert metrics_first["input_files"] == {
        "upstream_context": len(upstream_text),
        "image_semantics": len(image_text),
        "plain_text_summary": len(summary_text),
        "skill_prompt": len(skill_text),
    }
    assert metrics_first["output_files"] == {
        REPORT_MAP[phase_id]: len(report_text),
        STRUCTURED_JSON_MAP[phase_id]: len(structured_text),
    }
    assert metrics_first["output_file_count"] == len(created_files)
    assert metrics_first["output_dir_size_kb"] == expected_total_size
    assert metrics_first["tokens_per_second"] == round(expected_output_tokens / 12.5, 1)
    assert metrics_first["cost_estimate_usd"] > 0
    assert len(calls) == calls_after_first
    assert calls_after_first > 0
