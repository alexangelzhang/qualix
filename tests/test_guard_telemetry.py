"""Tests for dqg.quality.judge.guard_telemetry."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dqg.agents.judge_vote import JudgeVote
from dqg.constants import GUARD_EVENT_FILENAME, GUARD_PAIR_DIRNAME
from dqg.quality.judge.guard_telemetry import log_guard_event, save_guard_pair


def _make_vote(*, model: str = "m", overall: float = 3.0, verdict: str = "PASS", raw: str = "hello") -> JudgeVote:
    return JudgeVote(
        model=model,
        scores={},
        overall=overall,
        verdict=verdict,
        issues=[],
        raw_output=raw,
    )


def test_log_guard_event_appends_one_jsonl_line(tmp_path: Path) -> None:
    log_guard_event(
        tmp_path,
        guard="rationalization",
        event="LAYER1_HIT",
        phase="Q01",
        model="claude-sonnet-4-6",
        detected_patterns=[r"虽然.{0,20}但"],
        confirmed_items=["虽然 EUT then 字段单薄，但基本覆盖"],
    )
    p = tmp_path / GUARD_EVENT_FILENAME
    assert p.is_file()
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["guard"] == "rationalization"
    assert obj["event"] == "LAYER1_HIT"
    assert obj["phase"] == "Q01"
    assert obj["model"] == "claude-sonnet-4-6"
    assert obj["detected_patterns"] == [r"虽然.{0,20}但"]
    assert obj["confirmed_items"] == ["虽然 EUT then 字段单薄，但基本覆盖"]
    assert "pair_ref" not in obj  # 未传时不应出现


def test_log_guard_event_appends_not_overwrites(tmp_path: Path) -> None:
    for i in range(3):
        log_guard_event(
            tmp_path,
            guard="rationalization",
            event="LAYER1_HIT",
            phase="Q01",
            model=f"m{i}",
        )
    p = tmp_path / GUARD_EVENT_FILENAME
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 3
    models = [json.loads(ln)["model"] for ln in lines]
    assert models == ["m0", "m1", "m2"]


def test_log_guard_event_carries_pair_ref(tmp_path: Path) -> None:
    log_guard_event(
        tmp_path,
        guard="rationalization",
        event="REJUDGE_PASSED",
        phase="Q01",
        model="m",
        pair_ref="_rationalization_pairs/20260510_abc.json",
    )
    p = tmp_path / GUARD_EVENT_FILENAME
    obj = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert obj["pair_ref"] == "_rationalization_pairs/20260510_abc.json"


def test_save_guard_pair_roundtrip(tmp_path: Path) -> None:
    before = _make_vote(model="primary", overall=4.5, verdict="PASS", raw="before output")
    after = _make_vote(model="primary", overall=2.5, verdict="FAIL", raw="after output")
    ref = save_guard_pair(
        tmp_path,
        guard="rationalization",
        phase="Q01",
        model="primary",
        before_vote=before,
        after_vote=after,
        terminal_state="GUARD_EXHAUSTED",
        detected_patterns=[r"覆盖率.{0,5}达标"],
        confirmed_items=["覆盖率 达标"],
    )
    assert ref is not None
    assert ref.startswith(f"{GUARD_PAIR_DIRNAME}/")
    pair_path = tmp_path / ref
    assert pair_path.is_file()
    payload = json.loads(pair_path.read_text(encoding="utf-8"))
    assert payload["terminal_state"] == "GUARD_EXHAUSTED"
    assert payload["before"]["raw_output"] == "before output"
    assert payload["before"]["overall"] == 4.5
    assert payload["after"]["raw_output"] == "after output"
    assert payload["after"]["verdict"] == "FAIL"
    assert payload["detected_patterns"] == [r"覆盖率.{0,5}达标"]


def test_log_guard_event_silent_on_oserror(tmp_path: Path, monkeypatch) -> None:
    # Make the internal_dir a file (not a dir) to force OSError on mkdir
    blocking_file = tmp_path / "blocker"
    blocking_file.write_text("x", encoding="utf-8")
    # Passing a path that can't become a directory → mkdir raises, but call must not throw
    log_guard_event(
        blocking_file,
        guard="rationalization",
        event="LAYER1_HIT",
        phase="Q01",
        model="m",
    )
    # no exception → success; no file should exist under the blocker (it's a regular file)
    assert blocking_file.is_file()


def test_save_guard_pair_returns_none_on_failure(tmp_path: Path) -> None:
    blocking_file = tmp_path / "blocker"
    blocking_file.write_text("x", encoding="utf-8")
    ref = save_guard_pair(
        blocking_file,
        guard="rationalization",
        phase="Q01",
        model="m",
        before_vote=_make_vote(),
        after_vote=_make_vote(),
        terminal_state="REJUDGE_PASSED",
    )
    assert ref is None


def test_log_guard_event_concurrent_appends(tmp_path: Path) -> None:
    n = 20

    def _emit(i: int) -> None:
        log_guard_event(
            tmp_path,
            guard="rationalization",
            event="LAYER1_HIT",
            phase="Q01",
            model=f"m{i}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_emit, range(n)))

    p = tmp_path / GUARD_EVENT_FILENAME
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == n
    # 所有行都是合法 JSON
    for ln in lines:
        obj = json.loads(ln)
        assert obj["guard"] == "rationalization"
