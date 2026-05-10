"""T14: adaptive_loop 内 schema 校验反馈回路（ISSUE.md 2026-05-10）."""

from __future__ import annotations

from pathlib import Path

import pytest

from dqg.agents.handoff_builder import build_handoff_document
from dqg.agents.judge_vote import IterationRecord, JudgeVote, VoteResult


def test_handoff_includes_schema_errors_under_issues() -> None:
    vote = JudgeVote(
        model="m",
        scores={},
        overall=3.0,
        verdict="FAIL",
        issues=[{"severity": "high", "description": "semantic gap"}],
    )
    vr = VoteResult(votes=[vote], consensus="FAIL", avg_score=3.0, disagreements=[])
    prev = IterationRecord(
        iteration=1,
        judge_result=vr,
        schema_errors=["findings.0.severity: Field required", "extra field foo"],
    )
    doc = build_handoff_document(prev, next_iteration=2, anchor_facts=None)
    assert "结构化输出 / Schema" in doc
    assert "S-1." in doc
    assert "findings.0.severity" in doc
    assert "S-2." in doc


def test_iteration_record_schema_errors_default() -> None:
    r = IterationRecord(iteration=1)
    assert r.schema_errors == []


@pytest.fixture
def q06_phase_dir(tmp_path: Path) -> tuple[Path, Path]:
    """output/<pid>/Q06 with stale structured JSON."""
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    out = tmp_path / "output"
    pid = "p1"
    sub = PHASE_DIR_MAP["Q06"]
    pd = out / pid / sub
    pd.mkdir(parents=True)
    json_name = STRUCTURED_JSON_MAP["Q06"]
    stale = pd / json_name
    stale.write_text('{"findings": []}', encoding="utf-8")
    return out, pd


def test_schema_errors_after_worker_removes_stale_when_no_json_in_content(
    q06_phase_dir: tuple[Path, Path],
) -> None:
    """本轮输出无 JSON 块时删除残留 JSON，validate 反映「缺失」而非误用过期文件。"""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    output_dir, pd = q06_phase_dir
    loop = AdaptiveLoop(output_dir)
    errs = loop._schema_errors_after_worker(
        project_id="p1",
        phase_id="Q06",
        pd=pd,
        worker_content="仅 Markdown，没有 ```json 块也没有裸对象。",
        worker_ok=True,
    )
    from dqg.constants import STRUCTURED_JSON_MAP

    jp = pd / STRUCTURED_JSON_MAP["Q06"]
    assert not jp.exists()
    assert errs
    assert any("不存在" in e or "not" in e.lower() or "文件" in e for e in errs)


def test_schema_errors_after_worker_validates_extracted_json(q06_phase_dir: tuple[Path, Path]) -> None:
    """Worker 输出含合法 JSON 但缺必填字段时，应得到 Pydantic 风格错误列表。"""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    output_dir, pd = q06_phase_dir
    loop = AdaptiveLoop(output_dir)
    # 缺 severity 等必填（与 ISSUE 验收口径一致：故意不完整）
    bad_json = '{"findings": [{"finding_id": "F-1", "description": "x"}], "project_id": "p1"}'
    body = f"说明\n```json\n{bad_json}\n```\n"
    errs = loop._schema_errors_after_worker(
        project_id="p1",
        phase_id="Q06",
        pd=pd,
        worker_content=body,
        worker_ok=True,
    )
    assert errs
    joined = " ".join(errs)
    assert "severity" in joined.lower() or "findings" in joined.lower()


def test_schema_errors_after_worker_skips_when_worker_failed(q06_phase_dir: tuple[Path, Path]) -> None:
    """Worker 失败时短路返回 []，且不触碰 phase_dir 里的既有 JSON。"""
    from dqg.agents.adaptive_loop import AdaptiveLoop
    from dqg.constants import STRUCTURED_JSON_MAP

    output_dir, pd = q06_phase_dir
    loop = AdaptiveLoop(output_dir)
    stale_path = pd / STRUCTURED_JSON_MAP["Q06"]
    stale_before = stale_path.read_text(encoding="utf-8")

    errs = loop._schema_errors_after_worker(
        project_id="p1",
        phase_id="Q06",
        pd=pd,
        worker_content="任意内容",
        worker_ok=False,
    )
    assert errs == []
    # 未触碰既有 JSON（没删、没改写）
    assert stale_path.exists()
    assert stale_path.read_text(encoding="utf-8") == stale_before


def test_schema_errors_after_worker_skips_when_phase_unregistered(tmp_path: Path) -> None:
    """phase 不在 STRUCTURED_JSON_MAP 时短路返回 []（契约：finalize 兜底报错）。"""
    from dqg.agents.adaptive_loop import AdaptiveLoop

    loop = AdaptiveLoop(tmp_path / "output")
    errs = loop._schema_errors_after_worker(
        project_id="p1",
        phase_id="Q99_NOT_REGISTERED",
        pd=tmp_path,
        worker_content='{"foo": 1}',
        worker_ok=True,
    )
    assert errs == []


def test_truncate_schema_errors_for_summary_caps_items_and_chars() -> None:
    """_adaptive_summary.json 里的 schema_errors 应受条数/字符长度双上限约束。"""
    from dqg.agents.adaptive_loop import (
        _SUMMARY_SCHEMA_ERROR_MAX_CHARS,
        _SUMMARY_SCHEMA_ERROR_MAX_ITEMS,
        _truncate_schema_errors_for_summary,
    )

    long_errs = [f"err{i}: " + "x" * 1000 for i in range(_SUMMARY_SCHEMA_ERROR_MAX_ITEMS + 5)]
    out = _truncate_schema_errors_for_summary(long_errs)
    # 头部 N 条被保留（且每条截到上限），尾部追加一条 "…(+K more)"
    assert len(out) == _SUMMARY_SCHEMA_ERROR_MAX_ITEMS + 1
    assert all(len(e) <= _SUMMARY_SCHEMA_ERROR_MAX_CHARS for e in out[:-1])
    assert out[-1].startswith("…(+5 more")
