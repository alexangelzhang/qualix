"""Tests for StructuredChatResult and chat_structured()."""

from qualix.agents.llm_backends import StructuredChatResult, _extract_json


def test_extract_json_from_code_block():
    text = '```json\n{"verdict": "PASS", "overall": 4.0}\n```'
    result = _extract_json(text)
    assert result == {"verdict": "PASS", "overall": 4.0}


def test_extract_json_from_raw():
    text = 'Here is the result: {"verdict": "FAIL", "overall": 2.0} done.'
    result = _extract_json(text)
    assert result == {"verdict": "FAIL", "overall": 2.0}


def test_extract_json_returns_none_on_invalid():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


def test_structured_chat_result_fields():
    r = StructuredChatResult(parsed={"a": 1}, raw_text="raw", provider_meta={"usage": {}})
    assert r.parsed == {"a": 1}
    assert r.raw_text == "raw"
