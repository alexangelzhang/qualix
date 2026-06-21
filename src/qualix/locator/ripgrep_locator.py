"""Deterministic read-only evidence locator backed by ripgrep when available."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

from qualix.schemas.evidence import EvidenceCitation, EvidenceConfidence, EvidenceKind

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.$#-]{2,}|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}")
_STOP_WORDS = {
    "and",
    "the",
    "for",
    "find",
    "locate",
    "where",
    "with",
    "that",
    "this",
    "test",
    "tests",
    "code",
    "file",
    "files",
    "实现",
    "测试",
    "代码",
    "相关",
    "定位",
}
_INCLUDE_SUFFIXES = {
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".md",
    ".py",
    ".scala",
    ".ts",
    ".tsx",
    ".xml",
}
_EXCLUDED_DIRS = {
    ".codegraph",
    ".git",
    ".gitnexus",
    ".mypy_cache",
    ".pytest_cache",
    ".qualix",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
}


class RipgrepLocator:
    """Locate file-line evidence candidates without mutating the repository."""

    name = "ripgrep"

    def locate(
        self,
        *,
        query: str,
        code_repos: Sequence[str | Path],
        phase: str,
        eut_id: str,
        se_id: str = "",
        limit: int = 10,
        context_lines: int = 2,
    ) -> list[EvidenceCitation]:
        terms = _extract_terms(query)
        if se_id:
            terms.append(se_id)
        terms = _dedupe_terms(terms)

        repo_paths = [Path(p).expanduser().resolve() for p in code_repos]
        citations: dict[tuple[str, int, int | None, EvidenceKind], EvidenceCitation] = {}

        for repo in repo_paths:
            if not repo.is_dir():
                continue
            for term in terms:
                for match in self._search_term(repo, term):
                    citation = _build_citation(
                        repo=repo,
                        file_path=match.file_path,
                        line_no=match.line_no,
                        term=term,
                        phase=phase,
                        se_id=se_id,
                        eut_id=eut_id,
                        context_lines=context_lines,
                    )
                    key = (citation.path, citation.line_start, citation.line_end, citation.kind)
                    existing = citations.get(key)
                    if existing is None:
                        citations[key] = citation
                    elif term not in existing.matched_terms:
                        existing.matched_terms.append(term)
                        existing.confidence = _confidence(existing)
                        existing.reason = _reason(existing.matched_terms)

        ordered = sorted(citations.values(), key=_sort_key)
        return ordered[: max(limit, 0)]

    def _search_term(self, repo: Path, term: str) -> Iterable[_Match]:
        try:
            yield from _search_with_rg(repo, term)
            return
        except FileNotFoundError:
            yield from _search_with_python(repo, term)


class _Match:
    def __init__(self, file_path: Path, line_no: int) -> None:
        self.file_path = file_path
        self.line_no = line_no


def _extract_terms(query: str) -> list[str]:
    terms: list[str] = []
    for match in _TOKEN_RE.finditer(query):
        term = match.group(0).strip()
        if not term:
            continue
        if term.lower() in _STOP_WORDS:
            continue
        terms.append(term)
    if not terms and query.strip():
        terms.append(query.strip())
    return _dedupe_terms(terms)


def _dedupe_terms(terms: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def _search_with_rg(repo: Path, term: str) -> Iterable[_Match]:
    cmd = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "--fixed-strings",
        "--ignore-case",
    ]
    for suffix in sorted(_INCLUDE_SUFFIXES):
        cmd.extend(["--glob", f"*{suffix}"])
    for directory in sorted(_EXCLUDED_DIRS):
        cmd.extend(["--glob", f"!{directory}/**"])
    cmd.extend([term, str(repo)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode not in (0, 1):
        return
    for line in result.stdout.splitlines():
        parsed = _parse_rg_line(line)
        if parsed is None:
            continue
        file_path, line_no = parsed
        yield _Match(file_path=file_path, line_no=line_no)


def _parse_rg_line(line: str) -> tuple[Path, int] | None:
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    try:
        line_no = int(parts[1])
    except ValueError:
        return None
    return Path(parts[0]), line_no


def _search_with_python(repo: Path, term: str) -> Iterable[_Match]:
    lowered = term.lower()
    for file_path in repo.rglob("*"):
        if not file_path.is_file():
            continue
        if _is_excluded(file_path):
            continue
        if file_path.suffix.lower() not in _INCLUDE_SUFFIXES:
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, start=1):
            if lowered in line.lower():
                yield _Match(file_path=file_path, line_no=idx)


def _is_excluded(path: Path) -> bool:
    return any(part in _EXCLUDED_DIRS for part in path.parts)


def _build_citation(
    *,
    repo: Path,
    file_path: Path,
    line_no: int,
    term: str,
    phase: str,
    se_id: str,
    eut_id: str,
    context_lines: int,
) -> EvidenceCitation:
    line_count = _line_count(file_path)
    start = max(1, line_no - max(context_lines, 0))
    end = min(line_count, line_no + max(context_lines, 0)) if line_count else line_no
    rel_path = _relative_path(file_path, repo)
    matched_terms = [term]
    return EvidenceCitation(
        path=rel_path,
        line_start=start,
        line_end=end,
        kind=_infer_kind(file_path),
        phase=phase,
        se_id=se_id,
        eut_id=eut_id,
        repo=str(repo),
        locator=RipgrepLocator.name,
        confidence=_confidence_for_terms(matched_terms),
        reason=_reason(matched_terms),
        matched_terms=matched_terms,
    )


def _line_count(file_path: Path) -> int:
    try:
        return len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def _relative_path(file_path: Path, repo: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(repo))
    except ValueError:
        return str(file_path)


def _infer_kind(path: Path) -> EvidenceKind:
    lower_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in {".xml", ".html"} and ("coverage" in name or "jacoco" in name):
        return EvidenceKind.COVERAGE
    if suffix == ".md":
        if "report" in name or "review" in name:
            return EvidenceKind.REPORT
        return EvidenceKind.DESIGN
    if any(part in {"test", "tests", "__tests__"} for part in lower_parts):
        return EvidenceKind.TEST
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("test.java") or name.endswith(".spec.ts"):
        return EvidenceKind.TEST
    return EvidenceKind.IMPLEMENTATION


def _confidence(citation: EvidenceCitation) -> EvidenceConfidence:
    return _confidence_for_terms(citation.matched_terms)


def _confidence_for_terms(terms: Sequence[str]) -> EvidenceConfidence:
    if len(terms) >= 3:
        return EvidenceConfidence.HIGH
    if len(terms) >= 2:
        return EvidenceConfidence.MEDIUM
    return EvidenceConfidence.LOW


def _reason(terms: Sequence[str]) -> str:
    return "matched terms: " + ", ".join(terms)


def _sort_key(citation: EvidenceCitation) -> tuple[int, str, int]:
    kind_bonus = 0
    if citation.kind == EvidenceKind.TEST:
        kind_bonus = 2
    elif citation.kind == EvidenceKind.IMPLEMENTATION:
        kind_bonus = 1
    score = len(citation.matched_terms) * 10 + kind_bonus
    return (-score, citation.path, citation.line_start)
