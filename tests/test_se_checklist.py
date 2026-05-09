"""Q01 SE Checklist 解析与渲染测试 — 覆盖 se_examples 嵌套结构。"""

from __future__ import annotations

from pathlib import Path

import pytest

from dqg.quality.se_checklist import (
    _load_yaml,
    _parse_yaml_simple,
    format_checklist_prompt,
    load_se_checklist,
)

FIXTURE = """\
dimensions:
  - id: state_machine
    name: 状态机完整性
    optional: false
    applies_when: "always"
    questions:
      - "q1"
      - "q2"
    se_examples:
      - scenario: "非法跳转未拦截"
        bad_se: "需要拦截非法跳转"
        good_se:
          description: "非法 (src,dst) 调用返回 409 CONFLICT"
          verification: "每个组合发请求；断言 409 + errorCode=INVALID_TRANSITION"
      - scenario: "多出口无条件"
        bad_se: "按业务规则决定"
        good_se:
          description: "retry_count<3 走 A，否则走 B"
          verification: "参数化 retry_count ∈ {0,2,3,5}"

  - id: permission
    name: 权限边界
    optional: false
    applies_when: "always"
    questions:
      - "q3"

  - id: concurrency
    name: 并发/幂等
    optional: false
    applies_when: "always"
    questions:
      - "q4"
    se_examples:
      - scenario: "重复提交"
        bad_se: "防止重复"
        good_se:
          description: "相同 idempotencyKey 返回首次结果"
          verification: "重放后 responseA==responseB"
"""


@pytest.fixture
def checklist_dir(tmp_path: Path) -> Path:
    (tmp_path / "se_checklist.yaml").write_text(FIXTURE, encoding="utf-8")
    return tmp_path


def test_pyyaml_parses_se_examples(checklist_dir: Path) -> None:
    data = _load_yaml(checklist_dir / "se_checklist.yaml")
    assert data is not None
    dims = {d["id"]: d for d in data["dimensions"]}
    assert len(dims["state_machine"]["se_examples"]) == 2
    ex = dims["state_machine"]["se_examples"][0]
    assert ex["scenario"] == "非法跳转未拦截"
    assert ex["bad_se"] == "需要拦截非法跳转"
    assert ex["good_se"]["description"].startswith("非法 (src,dst)")
    assert "errorCode=INVALID_TRANSITION" in ex["good_se"]["verification"]
    assert "se_examples" not in dims["permission"] or dims["permission"]["se_examples"] == []


def test_simple_parser_parses_se_examples(checklist_dir: Path) -> None:
    data = _parse_yaml_simple(checklist_dir / "se_checklist.yaml")
    assert data is not None
    dims = {d["id"]: d for d in data["dimensions"]}
    sm_ex = dims["state_machine"].get("se_examples", [])
    assert len(sm_ex) == 2
    assert sm_ex[0]["scenario"] == "非法跳转未拦截"
    assert sm_ex[0]["good_se"]["verification"].startswith("每个组合发请求")
    assert sm_ex[1]["scenario"] == "多出口无条件"
    assert sm_ex[1]["good_se"]["description"] == "retry_count<3 走 A，否则走 B"
    # concurrency with single example
    assert len(dims["concurrency"]["se_examples"]) == 1
    # permission has no examples
    assert dims["permission"].get("se_examples", []) == []


def test_simple_parser_matches_pyyaml(checklist_dir: Path) -> None:
    py = _load_yaml(checklist_dir / "se_checklist.yaml")
    sm = _parse_yaml_simple(checklist_dir / "se_checklist.yaml")
    assert py is not None and sm is not None
    assert [d["id"] for d in py["dimensions"]] == [d["id"] for d in sm["dimensions"]]
    for py_dim, sm_dim in zip(py["dimensions"], sm["dimensions"], strict=True):
        assert py_dim.get("se_examples", []) == sm_dim.get("se_examples", [])


def test_load_se_checklist_passes_through_examples(checklist_dir: Path) -> None:
    dims = load_se_checklist(checklist_dir, prd_text="任意文本")
    sm = next(d for d in dims if d["id"] == "state_machine")
    assert len(sm["se_examples"]) == 2
    perm = next(d for d in dims if d["id"] == "permission")
    assert perm["se_examples"] == []


def test_format_prompt_renders_examples_block(checklist_dir: Path) -> None:
    dims = load_se_checklist(checklist_dir, prd_text="任意文本")
    prompt = format_checklist_prompt(dims)
    assert "示例对照" in prompt
    assert "✗ 不可验证写法：需要拦截非法跳转" in prompt
    assert "✓ 可验证 SE：非法 (src,dst) 调用返回 409 CONFLICT" in prompt
    assert "✓ 判定依据：每个组合发请求" in prompt
    assert "写法强度" in prompt


def test_format_prompt_skips_examples_when_absent(checklist_dir: Path) -> None:
    dims = load_se_checklist(checklist_dir, prd_text="任意文本")
    perm_only = [d for d in dims if d["id"] == "permission"]
    prompt = format_checklist_prompt(perm_only)
    assert "权限边界" in prompt
    assert "示例对照" not in prompt


def test_format_prompt_empty_dims_returns_empty() -> None:
    assert format_checklist_prompt([]) == ""
