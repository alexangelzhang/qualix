"""Tests for qualix.memory.memory_filter."""

from qualix.memory.memory_filter import (
    MemoryEntry,
    filter_memory_for_phase,
    parse_memory_entries,
)


class TestParseMemoryEntries:
    def test_plain_entries_are_global(self):
        text = "- PRD 中的图片必须解析\n- 接口幂等性必须校验"
        entries = parse_memory_entries(text)
        assert len(entries) == 2
        assert all(e.scope == "global" for e in entries)

    def test_project_tagged(self):
        text = "- [project:rights-platform] 权益中心使用 TMF 链路"
        entries = parse_memory_entries(text)
        assert len(entries) == 1
        assert entries[0].scope == "project:rights-platform"
        assert entries[0].project_id == "rights-platform"
        assert entries[0].content == "权益中心使用 TMF 链路"

    def test_global_tagged(self):
        text = "- [global] PRD 图片必须解析"
        entries = parse_memory_entries(text)
        assert len(entries) == 1
        assert entries[0].scope == "global"
        assert entries[0].content == "PRD 图片必须解析"

    def test_mixed(self):
        text = "- [global] 通用规则\n- [project:proj-a] 项目A规则\n- [project:proj-b] 项目B规则\n- 无标签规则\n"
        entries = parse_memory_entries(text)
        assert len(entries) == 4
        assert entries[0].scope == "global"
        assert entries[1].project_id == "proj-a"
        assert entries[2].project_id == "proj-b"
        assert entries[3].scope == "global"  # 无标签视为 global

    def test_empty_and_non_entry_lines_skipped(self):
        text = "\n# Header\n\n- 有效条目\n不是条目\n"
        entries = parse_memory_entries(text)
        assert len(entries) == 1


class TestFilterMemoryForPhase:
    def _make_entries(self) -> list[MemoryEntry]:
        return parse_memory_entries(
            "- [global] 通用规则1\n"
            "- [global] 通用规则2\n"
            "- [project:proj-a] 项目A特定规则\n"
            "- [project:proj-b] 项目B特定规则\n"
        )

    def test_phase_a_only_global(self):
        """Phase A 只注入 global 条目，不注入任何项目特定 memory."""
        entries = self._make_entries()
        result = filter_memory_for_phase(entries, "proj-a", "Q01")
        assert "通用规则1" in result
        assert "通用规则2" in result
        assert "项目A特定规则" not in result
        assert "项目B特定规则" not in result

    def test_other_phase_gets_global_plus_own_project(self):
        """非 Phase A 注入 global + 当前项目的条目."""
        entries = self._make_entries()
        result = filter_memory_for_phase(entries, "proj-a", "Q03")
        assert "通用规则1" in result
        assert "项目A特定规则" in result
        assert "项目B特定规则" not in result

    def test_cross_project_never_injected(self):
        """其他项目的 memory 永远不注入."""
        entries = self._make_entries()
        result = filter_memory_for_phase(entries, "proj-a", "Q07")
        assert "项目B特定规则" not in result

    def test_disclaimer_present(self):
        """注入的 memory 前有免责声明."""
        entries = self._make_entries()
        result = filter_memory_for_phase(entries, "proj-a", "Q05a")
        assert result.startswith("[System note:")

    def test_empty_returns_empty(self):
        result = filter_memory_for_phase([], "proj-a", "Q01")
        assert result == ""
