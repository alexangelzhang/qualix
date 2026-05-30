from qualix.context.enum_contract import EnumSource, render_enum_contract_prefix


def test_render_prefix_q03_contains_severity_enum() -> None:
    s = render_enum_contract_prefix("Q03")
    assert "CRITICAL" in s
    assert "CRITICAL_GAP" in s or "SAFE" in s


def test_render_prefix_unknown_phase_empty() -> None:
    assert render_enum_contract_prefix("Q99") == ""


def test_enum_source_tuple_lengths() -> None:
    assert len(EnumSource.Q03_SEVERITY) == 4
