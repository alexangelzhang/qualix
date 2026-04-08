from __future__ import annotations

from pathlib import Path

from dqg.quality.judge import generate_judge_prompt
from dqg.quality.critique import generate_critique_prompt
from dqg.tracking.experiment import generate_experiment_prompt
from dqg.tracking.case_selector import select_relevant_cases
from dqg.constants import BUG_CASE_RELEVANCE_EXCERPT_LIMIT, BUG_CASE_RELEVANCE_SEED_LIMIT


def _write_case(root: Path, phase_dir: str, case_id: str, *, phase: str, title: str, lesson: str, input_text: str, severity: str = "medium") -> None:
    case_dir = root / phase_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.json").write_text(
        "{" 
        f'"case_id": "{case_id}", '
        f'"phase": "{phase}", '
        '"error_type": "FN", '
        f'"severity": "{severity}", '
        f'"title": "{title}", '
        '"root_cause": "SKILL_RULE", '
        '"fix_target": "skills/requirement-structuring.md", '
        '"tags": ["auth"], '
        '"status": "open", '
        '"source": {"validation_error": "字段缺失"}, '
        '"expected": {"content": "需要权限校验"}, '
        '"actual": {"content": "缺少权限拦截"}, '
        f'"lesson": "{lesson}"' 
        "}",
        encoding="utf-8",
    )
    (case_dir / "input.md").write_text(input_text, encoding="utf-8")


def test_relevance_matching_used_by_judge_critique_and_experiment(tmp_path: Path, monkeypatch) -> None:
    cases_root = tmp_path / "cases"
    _write_case(
        cases_root,
        "phaseA",
        "CASE-001",
        phase="A",
        title="权限缺失",
        lesson="需要补权限校验",
        input_text="权限校验失败，请补权限拦截",
        severity="critical",
    )
    _write_case(
        cases_root,
        "phaseA",
        "CASE-002",
        phase="A",
        title="库存无关",
        lesson="库存逻辑",
        input_text="库存同步异常",
        severity="low",
    )

    import dqg.tracking.case_selector as case_selector
    original_load = case_selector.load_cases_by_phase
    monkeypatch.setattr(case_selector, "load_cases_by_phase", lambda phase: original_load(phase, cases_root))

    phase_dir = tmp_path / "output" / "demo" / "phaseA"
    phase_dir.mkdir(parents=True, exist_ok=True)
    long_tail = "尾部不应进入相关性输入" * 1200
    (phase_dir / "phase_a_report.md").write_text(f"权限校验失败\n{long_tail}", encoding="utf-8")
    (phase_dir / "phase_a_structured.json").write_text('{"project_id":"demo"}', encoding="utf-8")

    judge_prompt = generate_judge_prompt(tmp_path / "output", "demo", "A")
    critique_prompt = generate_critique_prompt(tmp_path / "output", "demo", "A")

    assert judge_prompt and "权限缺失" in judge_prompt and "库存无关" not in judge_prompt
    assert critique_prompt and "权限缺失" in critique_prompt and "库存无关" not in critique_prompt
    assert judge_prompt.count("尾部不应进入相关性输入") < 100
    assert critique_prompt.count("尾部不应进入相关性输入") < 100
    selected = select_relevant_cases("A", "权限校验失败，请补权限拦截", max_cases=2)
    assert [case["case_id"] for case in selected] == ["CASE-001"]

    # experiment uses skill content as relevance input
    skill_path = Path("skills/requirement-structuring.md")
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    old = skill_path.read_text(encoding="utf-8") if skill_path.exists() else None
    try:
        skill_path.write_text("权限校验与拦截" + ("尾部不应进入相关性输入" * 1200), encoding="utf-8")
        exp_prompt = generate_experiment_prompt(tmp_path / "output", "A", 1)
        assert exp_prompt and "权限缺失" in exp_prompt and "库存无关" not in exp_prompt
        assert exp_prompt.count("尾部不应进入相关性输入") < 100
    finally:
        if old is None:
            skill_path.unlink(missing_ok=True)
        else:
            skill_path.write_text(old, encoding="utf-8")
