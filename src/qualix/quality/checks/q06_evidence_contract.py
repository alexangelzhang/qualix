"""Q06 evidence field contract checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _check_covered_evidence_fields(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """G10: COVERED 条目必须提供 test_class / test_location / test citation 作为证据位置。

    - test_class='' 且 test_location=None → WARNING（无证据，可能是 LLM 漏填）
    - test_location.file 设置了但在 code_repos 中找不到 → BLOCKED（幻觉文件路径）
    - evidence_citations 若存在，只能作为候选证据；至少一条 test citation 可替代 test_class/test_location 的位置证据
    """
    errors: list[str] = []
    covered = [i for i in data.get("audit_items", []) if isinstance(i, dict) and str(i.get("status", "")) == "COVERED"]
    if not covered:
        return []

    for item in covered:
        eut_id = item.get("eut_id", "?")
        test_class = (item.get("test_class") or "").strip()
        test_location = item.get("test_location")
        loc_file = ""
        if isinstance(test_location, dict):
            loc_file = (test_location.get("file") or "").strip()
        has_test_citation = _has_test_evidence_citation(item, eut_id)

        if not test_class and not loc_file and not has_test_citation:
            errors.append(
                f"WARNING: [evidence_contract] {eut_id} COVERED 但未提供"
                " test_class、test_location 或 test evidence_citations，无可追溯的测试证据"
            )
            continue

        if (
            not test_class
            and not loc_file
            and has_test_citation
            and code_repos
            and not _has_existing_test_evidence_citation(item, eut_id, code_repos)
        ):
            errors.append(
                f"BLOCKED: [evidence_contract] {eut_id} COVERED evidence_citations"
                " 未能在代码仓库中定位到真实测试文件，疑似幻觉路径"
            )
            continue

        if loc_file and code_repos:
            loc_name = Path(loc_file).name
            found = any(
                next(
                    (f for f in Path(r).expanduser().resolve().rglob(loc_name) if f.is_file()),
                    None,
                )
                for r in code_repos
                if Path(r).expanduser().resolve().is_dir()
            )
            if not found:
                errors.append(
                    f"BLOCKED: [evidence_contract] {eut_id} COVERED test_location.file"
                    f" '{loc_file}' 在代码仓库中不存在，疑似幻觉路径"
                )

    return errors


def _has_test_evidence_citation(item: dict[str, Any], eut_id: str) -> bool:
    """Return true when an audit item carries a same-EUT test citation."""

    citations = item.get("evidence_citations") or []
    if not isinstance(citations, list):
        return False
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        if str(citation.get("eut_id", "") or "") != str(eut_id):
            continue
        if str(citation.get("kind", "") or "").lower() == "test":
            return True
    return False


def _has_existing_test_evidence_citation(item: dict[str, Any], eut_id: str, code_repos: list[str]) -> bool:
    """Return true when a same-EUT test citation points to an existing repo file."""

    citations = item.get("evidence_citations") or []
    if not isinstance(citations, list):
        return False
    test_paths = [
        str(citation.get("path", "") or "").strip()
        for citation in citations
        if isinstance(citation, dict)
        and str(citation.get("eut_id", "") or "") == str(eut_id)
        and str(citation.get("kind", "") or "").lower() == "test"
        and str(citation.get("path", "") or "").strip()
    ]
    if not test_paths:
        return False
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        for test_path in test_paths:
            candidate = repo / test_path
            if candidate.is_file():
                return True
            loc_name = Path(test_path).name
            if next((f for f in repo.rglob(loc_name) if f.is_file()), None):
                return True
    return False
