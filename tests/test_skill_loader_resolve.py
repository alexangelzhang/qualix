"""Tests for resolve_worker_prompt unified skill resolution."""

from unittest.mock import patch

from qualix.context.skill_loader import resolve_worker_prompt


def test_resolve_worker_prompt_default():
    """Default resolution uses PHASE_DEFS skill path."""
    with patch("qualix.context.skill_loader.load_skill_progressive") as mock_load:
        mock_load.return_value = "skill content"
        result = resolve_worker_prompt("Q01")
        assert result.endswith("skill content")
        assert "ENUM_CONTRACT" in result
        call_args = mock_load.call_args
        assert "requirement-structuring" in str(call_args[0][0])
        assert call_args[0][1] == "Q01"


def test_resolve_worker_prompt_with_override(tmp_path):
    """Override replaces SKILL.md path but still goes through progressive loader."""
    override_file = tmp_path / "custom_skill.md"
    override_file.write_text("custom content")
    with patch("qualix.context.skill_loader.load_skill_progressive") as mock_load:
        mock_load.return_value = "loaded via progressive"
        result = resolve_worker_prompt("Q01", skill_override=str(override_file))
        assert result.endswith("loaded via progressive")
        assert "ENUM_CONTRACT" in result
        call_args = mock_load.call_args
        assert str(call_args[0][0]) == str(override_file)
