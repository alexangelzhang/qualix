"""Test Oracle-guided evidence selection with priority IDs."""

from __future__ import annotations

from types import SimpleNamespace


def _make_chunk(source: str, content: str, file_path: str = "") -> SimpleNamespace:
    return SimpleNamespace(source=source, content=content, file_path=file_path)


def test_priority_ids_boost_relevant_quotes():
    """Quotes matching priority_ids should be selected first."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [
        _make_chunk(
            "Phase A",
            (
                "REQ-001 用户登录需要手机验证码\n\n"
                "REQ-002 管理员可以重置密码\n\n"
                "REQ-003 系统支持 OAuth2 登录\n\n"
                "BR-001 验证码 60 秒内有效\n\n"
                "BR-002 密码重置需要邮箱确认\n\n"
                "BR-003 OAuth2 回调必须验证 state 参数\n\n"
                "SE-001 登录接口返回 JWT token\n\n"
                "SE-002 重置密码接口发送邮件\n\n"
            ),
            "phase_a.json",
        ),
    ]

    # With priority: REQ-003 and BR-003 should come first
    result = render_key_quotes(chunks, max_quotes=3, priority_ids={"REQ-003", "BR-003"})
    combined_text = "\n".join(result)
    req003_pos = combined_text.find("REQ-003")
    req001_pos = combined_text.find("REQ-001")
    assert req003_pos >= 0, "REQ-003 should be in priority results"
    assert req003_pos < req001_pos or req001_pos == -1, "REQ-003 should appear before REQ-001"


def test_priority_ids_empty_falls_back_to_regex():
    """Empty priority_ids should behave identically to current regex selection."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [_make_chunk("Phase A", "REQ-001 需求内容\n\nBR-001 业务规则", "phase_a.json")]
    result_none = render_key_quotes(chunks)
    result_empty = render_key_quotes(chunks, priority_ids=set())
    assert result_none == result_empty


def test_priority_ids_with_no_matches_falls_back():
    """If no quotes match priority_ids, fall back to regex selection."""
    from dqg.context.evidence_renderer import render_key_quotes

    chunks = [_make_chunk("Phase A", "REQ-001 需求内容\n\nBR-001 业务规则", "phase_a.json")]
    result = render_key_quotes(chunks, priority_ids={"REQ-999", "BR-999"})
    assert len(result) > 0
    assert "REQ-001" in "\n".join(result)


def test_extract_priority_ids_from_targets():
    """extract_priority_ids should return flat set of SE/BR/REQ IDs."""
    from dqg.runtime.phase_contract import extract_priority_ids

    targets = [
        {"se_id": "SE-001", "mapping_target": "REQ-001", "source": "phase_a"},
        {"se_id": "SE-002", "mapping_target": "BR-003", "source": "phase_a"},
        {"se_id": "PROFILE-RISK-001", "mapping_target": "profile_baseline", "source": "profile"},
    ]

    ids = extract_priority_ids(targets)
    assert "SE-001" in ids
    assert "SE-002" in ids
    assert "REQ-001" in ids
    assert "BR-003" in ids
    # Profile targets: se_id included, but profile_baseline mapping excluded
    assert "PROFILE-RISK-001" in ids
    assert "profile_baseline" not in ids


def test_extract_priority_ids_empty():
    """Empty targets should return empty set."""
    from dqg.runtime.phase_contract import extract_priority_ids

    assert extract_priority_ids([]) == set()
    assert extract_priority_ids(None) == set()
