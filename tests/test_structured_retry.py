"""Tests for dqg.structured_retry — LLM 输出结构化重试."""

import json
from pathlib import Path

from dqg.agents.structured_retry import (
    fix_common_json_issues,
    simplify_payload,
    try_parse_structured_output,
    write_structured_output,
)


class TestFixCommonJsonIssues:
    def test_removes_markdown_wrapper(self):
        raw = '```json\n{"key": "value"}\n```'
        assert json.loads(fix_common_json_issues(raw)) == {"key": "value"}

    def test_removes_trailing_comma(self):
        raw = '{"a": 1, "b": 2,}'
        assert json.loads(fix_common_json_issues(raw)) == {"a": 1, "b": 2}

    def test_fixes_single_quotes(self):
        raw = "{'key': 'value'}"
        assert json.loads(fix_common_json_issues(raw)) == {"key": "value"}

    def test_valid_json_unchanged(self):
        raw = '{"key": "value"}'
        assert fix_common_json_issues(raw) == raw


class TestSimplifyPayload:
    def test_keeps_required_keys(self):
        data = {"project_id": "test", "requirements": [1, 2], "extra": "stuff"}
        result = simplify_payload(data, required_keys={"project_id", "requirements"})
        assert "project_id" in result
        assert "requirements" in result

    def test_truncates_long_strings(self):
        data = {"description": "x" * 1000}
        result = simplify_payload(data)
        assert len(result["description"]) < 1000

    def test_truncates_long_lists(self):
        data = {"items": list(range(50))}
        result = simplify_payload(data)
        assert len(result["items"]) == 10


class TestTryParseStructuredOutput:
    def test_valid_json(self):
        data, errors = try_parse_structured_output('{"key": "value"}')
        assert data == {"key": "value"}
        assert errors == []

    def test_markdown_wrapped_json(self):
        data, _errors = try_parse_structured_output('```json\n{"key": "value"}\n```')
        assert data == {"key": "value"}

    def test_json_with_trailing_comma(self):
        data, _errors = try_parse_structured_output('{"a": 1,}')
        assert data == {"a": 1}

    def test_json_embedded_in_text(self):
        raw = 'Here is the output:\n{"project_id": "test", "conclusion": "pass"}\nDone.'
        data, _errors = try_parse_structured_output(raw)
        assert data is not None
        assert data["project_id"] == "test"

    def test_completely_invalid(self):
        data, errors = try_parse_structured_output("this is not json at all")
        assert data is None
        assert len(errors) > 0

    def test_array_not_dict(self):
        data, errors = try_parse_structured_output("[1, 2, 3]")
        assert data is None
        assert any("不是 dict" in e for e in errors)


class TestWriteStructuredOutput:
    def test_write_success(self, tmp_path: Path):
        output = tmp_path / "test.json"
        data = {"project_id": "test", "items": [1, 2]}
        success, errors = write_structured_output(output, data)
        assert success is True
        assert errors == []
        assert output.exists()
        assert json.loads(output.read_text()) == data

    def test_fallback_to_markdown(self, tmp_path: Path):
        output = tmp_path / "test.json"
        # 创建一个无法序列化的对象
        data = {"key": object()}
        success, errors = write_structured_output(output, data)
        assert success is False
        assert len(errors) > 0
