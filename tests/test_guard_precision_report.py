import json
from pathlib import Path

from dqg.constants import GUARD_EVENT_FILENAME
from dqg.reporting.guard_precision_report import (
    build_guard_precision_summary,
    render_guard_precision_markdown,
    write_guard_precision_report,
)


def test_build_summary_counts(tmp_path: Path) -> None:
    proj = tmp_path / "output" / "demo" / "Q05" / "_internal"
    proj.mkdir(parents=True)
    payload = [
        {"guardrail": "finalize_checks", "passed": True, "level": "INFO"},
        {"guardrail": "finalize_checks", "passed": False, "level": "BLOCKED"},
    ]
    (proj / "_guardrail_results.json").write_text(json.dumps(payload), encoding="utf-8")
    s = build_guard_precision_summary(tmp_path / "output")
    assert s["guardrail_files_read"] >= 1
    assert s["by_guard"]["finalize_checks"]["pass"] == 1
    assert s["by_guard"]["finalize_checks"]["fail"] == 1
    # 兼容性：旧 key 不丢，新 key 存在
    assert s["by_guard"]["finalize_checks"]["blocked"] == 1
    assert s["by_guard"]["finalize_checks"]["triggered"] == 0


def test_build_summary_aggregates_guard_events(tmp_path: Path) -> None:
    proj = tmp_path / "output" / "demo" / "Q01" / "_internal"
    proj.mkdir(parents=True)
    events = [
        {"guard": "rationalization", "event": "LAYER1_HIT", "phase": "Q01", "model": "m"},
        {"guard": "rationalization", "event": "REJUDGE_PASSED", "phase": "Q01", "model": "m"},
        {"guard": "rationalization", "event": "LAYER1_HIT", "phase": "Q01", "model": "m"},
        {"guard": "rationalization", "event": "GUARD_EXHAUSTED", "phase": "Q01", "model": "m"},
        {"guard": "overcorrection", "event": "LAYER1_HIT", "phase": "Q01", "model": "m"},
    ]
    jsonl = "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n"
    (proj / GUARD_EVENT_FILENAME).write_text(jsonl, encoding="utf-8")

    s = build_guard_precision_summary(tmp_path / "output")
    assert s["guard_event_files_read"] == 1

    rat = s["by_guard"]["rationalization_guard"]
    assert rat["triggered"] == 2  # 两次 LAYER1_HIT
    assert rat["pass"] == 1  # 一次 REJUDGE_PASSED
    assert rat["fail"] == 1  # 一次 GUARD_EXHAUSTED
    assert rat["blocked"] == 1  # GUARD_EXHAUSTED 也算 blocked

    over = s["by_guard"]["overcorrection_guard"]
    assert over["triggered"] == 1
    assert over["pass"] == 0


def test_build_summary_tolerates_broken_jsonl(tmp_path: Path) -> None:
    proj = tmp_path / "output" / "demo" / "Q01" / "_internal"
    proj.mkdir(parents=True)
    broken = 'not-json\n{"guard": "rationalization", "event": "LAYER1_HIT"}\n\n'
    (proj / GUARD_EVENT_FILENAME).write_text(broken, encoding="utf-8")

    s = build_guard_precision_summary(tmp_path / "output")
    # 损坏行跳过，有效行被聚合
    assert s["by_guard"]["rationalization_guard"]["triggered"] == 1


def test_markdown_contains_triggered_column_and_guard_names(tmp_path: Path) -> None:
    proj = tmp_path / "output" / "demo" / "Q01" / "_internal"
    proj.mkdir(parents=True)
    (proj / GUARD_EVENT_FILENAME).write_text(
        json.dumps({"guard": "rationalization", "event": "LAYER1_HIT"}) + "\n",
        encoding="utf-8",
    )
    s = build_guard_precision_summary(tmp_path / "output")
    md = render_guard_precision_markdown(s)
    # 表头含 triggered 列
    assert "| triggered |" in md
    # KNOWN_GUARDS 包含两个 runtime guard 名
    assert "rationalization_guard" in md
    assert "overcorrection_guard" in md


def test_write_report_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "gp.md"
    p = write_guard_precision_report(tmp_path / "missing_output", dest=dest)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Guard 精度周报" in text
