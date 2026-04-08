from __future__ import annotations

from pathlib import Path

from dqg.store.core import row_to_dict
from dqg.tracking.bug_cases import load_cases_by_phase, render_cases_for_prompt
from dqg.tracking.case_selector import select_relevant_cases


def _write_case(
    root: Path,
    phase_dir: str,
    case_id: str,
    *,
    phase: str,
    title: str,
    lesson: str,
    severity: str = "medium",
    status: str = "open",
    input_text: str = "",
) -> None:
    case_dir = root / phase_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.json").write_text(
        (
            "{"
            f'"case_id": "{case_id}", '
            f'"phase": "{phase}", '
            '"error_type": "FN", '
            f'"severity": "{severity}", '
            f'"title": "{title}", '
            '"root_cause": "SKILL_RULE", '
            '"fix_target": "skills/requirement-structuring.md", '
            '"tags": ["auth"], '
            f'"status": "{status}", '
            '"source": {"validation_error": "字段缺失"}, '
            '"expected": {"content": "需要权限校验"}, '
            '"actual": {"content": "缺少权限拦截"}, '
            f'"lesson": "{lesson}"'
            "}"
        ),
        encoding="utf-8",
    )
    if input_text:
        (case_dir / "input.md").write_text(input_text, encoding="utf-8")


def test_store_private_alias_still_exports_row_to_dict() -> None:
    import dqg.store as store

    assert store._row_to_dict is row_to_dict


def test_load_cases_by_phase_preloads_input_excerpt_and_render_reuses_it(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    input_text = "权限校验失败\n" + ("x" * 600)
    _write_case(
        cases_root,
        "phaseA",
        "CASE-001",
        phase="A",
        title="权限缺失",
        lesson="必须补权限校验",
        input_text=input_text,
    )

    cases = load_cases_by_phase("A", cases_root)
    assert len(cases) == 1
    assert cases[0]["_has_input"] is True
    assert cases[0]["_input_excerpt"].startswith("权限校验失败")
    assert cases[0]["_input_excerpt"].endswith("...(截断)")

    rendered = render_cases_for_prompt("A", cases_root)
    assert "权限校验失败" in rendered
    assert "...(截断)" in rendered


def test_select_relevant_cases_uses_preloaded_case_content(tmp_path: Path) -> None:
    cases_root = tmp_path / "cases"
    _write_case(
        cases_root,
        "phaseA",
        "CASE-001",
        phase="A",
        title="权限缺失",
        lesson="命中 lesson",
        input_text="权限校验失败，需要补充拦截逻辑",
    )
    _write_case(
        cases_root,
        "phaseA",
        "CASE-002",
        phase="A",
        title="无关案例",
        lesson="其他问题",
        input_text="库存同步异常",
    )

    import dqg.tracking.case_selector as case_selector

    original_load = case_selector.load_cases_by_phase

    def patched_load_cases_by_phase(phase: str):
        return original_load(phase, cases_root)

    case_selector.load_cases_by_phase = patched_load_cases_by_phase
    try:
        selected = select_relevant_cases("A", "这里要求补权限校验和拦截", max_cases=1)
    finally:
        case_selector.load_cases_by_phase = original_load

    assert len(selected) == 1
    assert selected[0]["case_id"] == "CASE-001"
