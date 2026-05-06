"""Builtin Tools: Agent 内置工具集（Swarm/Memory/Search/Wiki/Batch）."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dqg.agents.agent import Agent
from dqg.agents.llm_backends import LLMConfig
from dqg.constants import DEFAULT_FALLBACK_MODEL
from dqg.json_utils import dump_json_str
from dqg.log import get_logger

log = get_logger(__name__)


def build_builtin_tools(
    output_dir: Path,
    project_id: str = "",
    max_subagent_depth: int = 2,
    current_depth: int = 0,
    subagent_result_limit: int = 16_000,
) -> list[Callable]:
    """构建内置工具集 (Swarm & Memory & Search)."""

    def spawn_subagent(task_prompt: str) -> str:
        """创建一个轻量级子 Agent 去独立执行探勘任务，避免主 Agent 陷入长上下文。
        参数:
        - task_prompt: 对子 Agent 的任务指示。
        返回: 子 Agent 测试的结果内容。
        """
        if current_depth >= max_subagent_depth:
            log.warning("Subagent depth limit reached (%d), rejecting spawn", current_depth)
            return f"BLOCKED: 子 Agent 嵌套深度已达上限 ({max_subagent_depth})，禁止继续委派。"
        log.info("Spawning subagent at depth %d...", current_depth + 1)
        sub = Agent(
            name="subagent",
            role="researcher",
            system_prompt="你是一个独立调研器。",
            model=LLMConfig(primary="claude-haiku-3.5", fallback=DEFAULT_FALLBACK_MODEL),
        )
        res = sub.run(task_prompt)
        content = res.content
        if len(content) > subagent_result_limit:
            content = content[:subagent_result_limit] + "\n...(结果已截断)"
        return content

    def append_persistent_memory(rule_description: str) -> str:
        """将发现的高频错误、或人类强制要求等规则，永久写入当前仓库的记忆 (.dqg/MEMORY.md)。此后所有 Agent 将严格遵守该规则。
        参数:
        - rule_description: 要永久记忆的规则描述。
        """
        from dqg.security.content_scanner import scan_content

        blocked = scan_content(rule_description)
        if blocked:
            log.warning("Memory write blocked: %s", blocked)
            return f"BLOCKED: {blocked}"
        mem_dir = Path(".dqg")
        mem_dir.mkdir(exist_ok=True)
        mem_file = mem_dir / "MEMORY.md"
        tag = f"[project:{project_id}] " if project_id else ""
        with open(mem_file, "a", encoding="utf-8") as f:
            f.write(f"- {tag}{rule_description}\n")
        return f"Successfully recorded rule into .dqg/MEMORY.md: {rule_description}"

    def search_upstream_context(query_keyword: str) -> str:
        """在无需吞噬全部上游产物的前提下，搜刮过往 Phase 和代码库的事实和片段。
        参数:
        - query_keyword: 要搜索的关键词。
        """
        from dqg.memory.memory_layer import MemoryLayer

        mem = MemoryLayer(output_dir)
        res = mem.search(query_keyword, scope="facts", limit=5)
        return dump_json_str(res)

    def read_wiki_page(page_name: str) -> str:
        """按需读取当前项目的 .dqg-wiki 下的某个百科章节。
        参数:
        - page_name: 例如 index.md 或是 entities/Order.md
        """
        path = Path(".dqg-wiki") / page_name
        if not path.exists():
            return f"Page {page_name} does not exist."
        content = path.read_text(encoding="utf-8")
        return (
            "[System note: 以下 wiki 内容由 Agent 在之前的 Phase 中生成，"
            "可能包含不准确的推断。请与原始证据交叉验证后再引用。]\n\n" + content
        )

    def write_to_wiki(page_name: str, page_content: str, mode: str = "overwrite") -> str:
        """【重要】当你发现新的隐式知识、约束时，将认知写入项目的 .dqg-wiki 下。
        参数:
        - page_name: 写入文件名（如 entities/User.md或index.md）
        - page_content: 要记录的 Markdown 格式内容
        - mode: overwrite（覆盖）或 append（追加）
        """
        from datetime import datetime

        from dqg.security.content_scanner import scan_content

        blocked = scan_content(page_content)
        if blocked:
            log.warning("Wiki write blocked for %s: %s", page_name, blocked)
            return f"BLOCKED: {blocked}"
        metadata = f"\n\n<!-- written_by: agent | project: {project_id} | timestamp: {datetime.now().isoformat()} -->"
        path = Path(".dqg-wiki") / page_name
        path.parent.mkdir(parents=True, exist_ok=True)
        mode_flag = "a" if mode == "append" else "w"
        with open(path, mode_flag, encoding="utf-8") as f:
            f.write(page_content + metadata)
        return f"Successfully wrote to Wiki page: {page_name}"

    def batch_query(queries: list) -> str:
        """批量执行多个查询，一次返回所有结果，大幅减少 tool call 开销。
        参数:
        - queries: 查询列表，每个元素是 {"type": "search", "keyword": "..."} 或 {"type": "wiki", "page": "..."}
        返回: JSON 数组，每个元素对应一个查询的结果。
        """
        results = []
        for q in queries:
            qtype = q.get("type", "")
            try:
                if qtype == "search":
                    results.append(
                        {
                            "type": "search",
                            "keyword": q.get("keyword", ""),
                            "result": search_upstream_context(q["keyword"]),
                        }
                    )
                elif qtype == "wiki":
                    results.append({"type": "wiki", "page": q.get("page", ""), "result": read_wiki_page(q["page"])})
                else:
                    results.append({"type": qtype, "error": f"未知查询类型: {qtype}"})
            except Exception as e:
                results.append({"type": qtype, "error": str(e)})
        return dump_json_str(results)

    return [
        spawn_subagent,
        append_persistent_memory,
        search_upstream_context,
        read_wiki_page,
        write_to_wiki,
        batch_query,
    ]
