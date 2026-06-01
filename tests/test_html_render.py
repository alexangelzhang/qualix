"""Tests for qualix.reporting.html_render (Q05a EUT Matrix HTML renderer)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qualix.reporting.html_render import render_q05_eut_matrix

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "q05_eut_matrix" / "phase_b_structured.json"


def test_render_q05_smoke(tmp_path: Path):
    out = tmp_path / "eut_matrix.html"
    result = render_q05_eut_matrix(FIXTURE_JSON, out)

    # 基本契约
    assert result["test_case_count"] == 2
    assert result["project_id"] == "demo-q05-render"
    assert Path(result["html_path"]) == out.resolve()
    assert Path(result["source_json"]) == FIXTURE_JSON.resolve()

    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    # 每个 TC-ID 都应出现在嵌入的 JSON 中
    payload = json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))
    for tc in payload["test_cases"]:
        assert tc["id"] in html

    # 占位符都被替换掉
    assert "{{PROJECT_ID}}" not in html
    assert "{{GENERATED_AT}}" not in html
    assert "{{DATA_JSON}}" not in html


def test_render_missing_source(tmp_path: Path):
    missing = tmp_path / "does_not_exist.json"
    out = tmp_path / "out.html"
    with pytest.raises(FileNotFoundError):
        render_q05_eut_matrix(missing, out)


def test_render_empty_test_cases(tmp_path: Path):
    src = tmp_path / "phase_b_structured.json"
    src.write_text(json.dumps({"project_id": "demo", "test_cases": []}), encoding="utf-8")
    out = tmp_path / "out.html"
    result = render_q05_eut_matrix(src, out)
    assert result["test_case_count"] == 0
    assert result["project_id"] == "demo"
    html = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html


def test_render_missing_test_cases_key_raises(tmp_path: Path):
    src = tmp_path / "bad.json"
    src.write_text(json.dumps({"project_id": "demo"}), encoding="utf-8")
    out = tmp_path / "out.html"
    with pytest.raises(ValueError, match="test_cases"):
        render_q05_eut_matrix(src, out)


def test_render_embedded_json_is_parsable(tmp_path: Path):
    src = tmp_path / "src.json"
    src.write_text(
        json.dumps(
            {
                "project_id": "demo",
                "test_cases": [{"id": "TC-1", "status": "COVERED", "scenario": "有 </script> 字面量"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.html"
    render_q05_eut_matrix(src, out)
    html = out.read_text(encoding="utf-8")

    # 提取嵌入 JSON 段
    marker = '<script id="qualix-data" type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    embedded = html[start:end]

    # 数据区域内部的 </script> 字面量必须被转义，避免提前闭合 <script>
    assert "</script>" not in embedded
    assert "<\\/script>" in embedded

    # 反解析（把 <\/ 还原成 </）应得到合法 JSON
    restored = embedded.replace("<\\/", "</")
    parsed = json.loads(restored)
    assert parsed["test_cases"][0]["id"] == "TC-1"
    assert "_generated_at" in parsed
