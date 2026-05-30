from __future__ import annotations

from pathlib import Path

from qualix.constants import WIKI_COMPILE_CONTEXT_LIMIT, WIKI_LINT_FILE_EXCERPT_LIMIT, WIKI_LINT_TOTAL_EXCERPT_LIMIT
from qualix.memory.wiki_layer import WikiManager


def test_compile_wiki_prefers_plain_text_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_ingest = output_dir / "demo" / "Q01" / "ingest"
    phase_ingest.mkdir(parents=True, exist_ok=True)
    phase_ingest.joinpath("plain_text_summary.md").write_text("summary-first", encoding="utf-8")
    phase_ingest.joinpath("plain_text.txt").write_text("raw-fallback", encoding="utf-8")

    wiki = WikiManager(output_dir)

    assert wiki.compile_wiki("demo") == "summary-first"


def test_compile_wiki_falls_back_to_plain_text(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_ingest = output_dir / "demo" / "Q01" / "ingest"
    phase_ingest.mkdir(parents=True, exist_ok=True)
    phase_ingest.joinpath("plain_text.txt").write_text("raw-fallback", encoding="utf-8")

    wiki = WikiManager(output_dir)

    assert wiki.compile_wiki("demo") == "raw-fallback"


def test_compile_wiki_truncates_long_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    phase_ingest = output_dir / "demo" / "Q01" / "ingest"
    phase_ingest.mkdir(parents=True, exist_ok=True)
    phase_ingest.joinpath("plain_text_summary.md").write_text("a" * (WIKI_COMPILE_CONTEXT_LIMIT + 100), encoding="utf-8")

    wiki = WikiManager(output_dir)

    compiled = wiki.compile_wiki("demo")
    assert compiled.startswith("a" * WIKI_COMPILE_CONTEXT_LIMIT)
    assert "...(截断)" in compiled


def test_lint_wiki_collects_truncated_bundle(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    wiki_root = output_dir / ".dqg-wiki"
    wiki_root.mkdir(parents=True, exist_ok=True)
    wiki_root.joinpath("index.md").write_text("index\n" + ("x" * (WIKI_LINT_FILE_EXCERPT_LIMIT + 50)), encoding="utf-8")
    wiki_root.joinpath("notes.md").write_text("notes\n" + ("y" * (WIKI_LINT_FILE_EXCERPT_LIMIT + 50)), encoding="utf-8")

    wiki = WikiManager(output_dir)
    wiki._wiki_root = lambda: wiki_root  # type: ignore[method-assign]

    bundle = wiki.lint_wiki("demo")
    assert "index.md" in bundle
    assert "notes.md" in bundle
    assert "...(截断)" in bundle
    assert len(bundle) <= WIKI_LINT_TOTAL_EXCERPT_LIMIT + 400
