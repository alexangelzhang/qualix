"""AgentOrchestrator: 真 Multi-Agent 编排器."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from dqg.agents.llm_backends import LLMConfig
from dqg.constants import DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL, DEFAULT_PRIMARY_MODEL
from dqg.agents.agent import Agent, AgentResult
from dqg.log import get_logger

log = get_logger(__name__)


class AgentOrchestrator:
    """真 Multi-Agent 编排器：独立进程 + 不同模型 + 文件通信."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def create_worker(self, project_id: str, phase_id: str, skill_content: str, tools: list[Callable] | None = None) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 如果你在分析中发现了当前项目代码或需求里有价值的全局约束、隐式逻辑，请立即调用 write_to_wiki 工具将其记入 `.dqg-wiki/`。不要让它随风消逝！"
        return Agent(
            name=f"{project_id}-{phase_id}-worker",
            role="worker",
            system_prompt=skill_content + writeback_prompt,
            model=LLMConfig(primary=DEFAULT_PRIMARY_MODEL, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools
        )

    def create_judge(self, project_id: str, phase_id: str, rubric: str, tools: list[Callable] | None = None) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 本项目已开启 LLM-Wiki。如果你在评审中发现严重且值得沉淀的不良规范，请用 write_to_wiki 将教训写入 `.dqg-wiki/`。"
        return Agent(
            name=f"{project_id}-{phase_id}-judge",
            role="judge",
            system_prompt=rubric + writeback_prompt,
            model=LLMConfig(primary=DEFAULT_JUDGE_MODEL, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools
        )

    def create_critique(self, project_id: str, phase_id: str, critique_prompt: str, tools: list[Callable] | None = None) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 如果你在挑错中找出了被违背的设计原则或高频痛点，务必调用 write_to_wiki 工具将其定格入 `.dqg-wiki/`，为长效免疫做贡献。"
        return Agent(
            name=f"{project_id}-{phase_id}-critique",
            role="critique",
            system_prompt=critique_prompt + writeback_prompt,
            model=LLMConfig(primary=DEFAULT_JUDGE_MODEL, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools
        )

    def _build_builtin_tools(self) -> list[Callable]:
        """构建内置工具集 (Swarm & Memory & Search)."""
        def spawn_subagent(task_prompt: str) -> str:
            """创建一个轻量级子 Agent 去独立执行探勘任务，避免主 Agent 陷入长上下文。
            参数:
            - task_prompt: 对子 Agent 的任务指示。
            返回: 子 Agent 测试的结果内容。
            """
            log.info("Spawning subagent for task...")
            sub = Agent(
                name="subagent", role="researcher", system_prompt="你是一个独立调研器。",
                model=LLMConfig(primary="claude-haiku-3.5", fallback=DEFAULT_FALLBACK_MODEL)
            )
            res = sub.run(task_prompt)
            return res.content

        def append_persistent_memory(rule_description: str) -> str:
            """将发现的高频错误、或人类强制要求等规则，永久写入当前仓库的记忆 (.dqg/MEMORY.md)。此后所有 Agent 将严格遵守该规则。
            参数:
            - rule_description: 要永久记忆的规则描述。
            """
            mem_dir = Path(".dqg")
            mem_dir.mkdir(exist_ok=True)
            mem_file = mem_dir / "MEMORY.md"
            with open(mem_file, "a", encoding="utf-8") as f:
                f.write(f"- {rule_description}\n")
            return f"Successfully recorded rule into .dqg/MEMORY.md: {rule_description}"

        def search_upstream_context(query_keyword: str) -> str:
            """在无需吞噬全部上游产物的前提下，搜刮过往 Phase 和代码库的事实和片段。
            参数:
            - query_keyword: 要搜索的关键词。
            """
            from dqg.memory.memory_layer import MemoryLayer
            mem = MemoryLayer(self.output_dir)
            res = mem.search(query_keyword, scope="facts", limit=5)
            # jsonify or dict dump
            return json.dumps(res, ensure_ascii=False)

        def read_wiki_page(page_name: str) -> str:
            """按需读取当前项目的 .dqg-wiki 下的某个百科章节。
            参数:
            - page_name: 例如 index.md 或是 entities/Order.md
            """
            path = Path(".dqg-wiki") / page_name
            if not path.exists():
                return f"Page {page_name} does not exist."
            return path.read_text(encoding="utf-8")

        def write_to_wiki(page_name: str, page_content: str, mode: str = "overwrite") -> str:
            """【重要】当你发现新的隐式知识、约束时，将认知写入项目的 .dqg-wiki 下。
            参数:
            - page_name: 写入文件名（如 entities/User.md或index.md）
            - page_content: 要记录的 Markdown 格式内容
            - mode: overwrite（覆盖）或 append（追加）
            """
            path = Path(".dqg-wiki") / page_name
            path.parent.mkdir(parents=True, exist_ok=True)
            mode_flag = "a" if mode == "append" else "w"
            with open(path, mode_flag, encoding="utf-8") as f:
                f.write(page_content)
            return f"Successfully wrote to Wiki page: {page_name}"

        return [spawn_subagent, append_persistent_memory, search_upstream_context, read_wiki_page, write_to_wiki]

    def run_pipeline(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None = None,
    ) -> dict[str, AgentResult]:
        """执行 Worker → Judge → Critique 流水线."""
        results = {}
        builtin_tools = self._build_builtin_tools()

        # Step 1: Worker
        worker = self.create_worker(project_id, phase_id, worker_prompt, tools=builtin_tools)
        worker_result = worker.run("执行 Phase 任务，输出报告和结构化 JSON。", context_files)
        results["worker"] = worker_result

        if worker_result.status == "failed":
            return results

        # 保存 Worker 输出
        from dqg.core.state_machine import PHASE_DEFS, phase_dir as _pd
        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _pd(self.output_dir, project_id, phase_def)
        worker_output = pd / "_worker_output.md"
        worker_output.write_text(worker_result.content, encoding="utf-8")

        # Step 2: Judge（独立 context，只看 Worker 输出，不看推理过程）
        judge = self.create_judge(project_id, phase_id, judge_rubric, tools=builtin_tools)
        judge_result = judge.run(
            "评审以下报告的质量，输出 JSON 格式的评审结果。",
            context_files=[worker_output],
        )
        results["judge"] = judge_result

        if judge_result.status != "failed":
            judge_output = pd / "_judge_result_v2.json"
            judge_output.write_text(judge_result.content, encoding="utf-8")

        # Step 3: Critique（独立 context，看 Worker 输出 + Judge 结果）
        critique = self.create_critique(project_id, phase_id, critique_prompt, tools=builtin_tools)
        critique_files = [worker_output]
        if judge_result.status != "failed":
            critique_files.append(pd / "_judge_result_v2.json")

        critique_result = critique.run(
            "假设报告有遗漏和错误，主动找问题。输出 JSON 格式的发现。",
            context_files=critique_files,
        )
        results["critique"] = critique_result

        if critique_result.status != "failed":
            critique_output = pd / "_critique_v2.json"
            critique_output.write_text(critique_result.content, encoding="utf-8")

        return results

    def format_pipeline_result(self, results: dict[str, AgentResult]) -> str:
        """格式化流水线结果."""
        lines = ["  Multi-Agent Pipeline 结果:"]
        for role, result in results.items():
            status_icon = {"success": "✓", "fallback": "⚠", "failed": "✗"}.get(result.status, "?")
            lines.append(
                f"    [{status_icon}] {role}: {result.status} "
                f"(model={result.model_used}, {result.duration_seconds:.1f}s)"
            )
            if result.error:
                lines.append(f"        error: {result.error[:100]}")
        return "\n".join(lines)
