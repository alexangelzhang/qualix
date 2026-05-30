"""Tests for qualix.security.tool_permissions."""

from qualix.security.tool_permissions import filter_tools_by_role


def _make_tool(name: str):
    """创建一个带 __name__ 的 mock 工具函数."""
    def tool():
        pass
    tool.__name__ = name
    return tool


ALL_TOOLS = [
    _make_tool("spawn_subagent"),
    _make_tool("append_persistent_memory"),
    _make_tool("search_upstream_context"),
    _make_tool("read_wiki_page"),
    _make_tool("write_to_wiki"),
    _make_tool("batch_query"),
]


class TestFilterToolsByRole:

    def test_worker_gets_all_tools(self):
        result = filter_tools_by_role(ALL_TOOLS, "worker")
        assert len(result) == 6

    def test_judge_gets_read_only(self):
        result = filter_tools_by_role(ALL_TOOLS, "judge")
        names = {t.__name__ for t in result}
        assert names == {"search_upstream_context", "read_wiki_page", "batch_query"}
        assert "write_to_wiki" not in names
        assert "append_persistent_memory" not in names
        assert "spawn_subagent" not in names

    def test_critique_can_write_but_no_subagent(self):
        result = filter_tools_by_role(ALL_TOOLS, "critique")
        names = {t.__name__ for t in result}
        assert "write_to_wiki" in names
        assert "append_persistent_memory" in names
        assert "batch_query" in names
        assert "spawn_subagent" not in names

    def test_researcher_minimal_tools(self):
        result = filter_tools_by_role(ALL_TOOLS, "researcher")
        names = {t.__name__ for t in result}
        assert names == {"search_upstream_context", "read_wiki_page", "batch_query"}

    def test_unknown_role_gets_all(self):
        result = filter_tools_by_role(ALL_TOOLS, "unknown_role")
        assert len(result) == 6

    def test_empty_tools_list(self):
        result = filter_tools_by_role([], "judge")
        assert result == []
