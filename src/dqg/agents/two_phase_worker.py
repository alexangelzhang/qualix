"""Worker 内部拆分：Collector + Writer 两阶段执行.

把 Worker 从单一 prompt 拆为两个 subagent：
1. Collector Agent：只做检索和证据收集，输出 _evidence_pack.json
2. Writer Agent：只看 evidence pack + skill，不看原始文档，输出报告

Writer 的 context 更干净（不含原始文档），产出质量更高。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)


def run_two_phase_worker(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    skill_content: str,
    context_files: list[Path] | None = None,
    worker_model: str = "claude-opus-4-6",
    fallback: str = "deepseek-chat",
) -> dict[str, Any]:
    """两阶段 Worker 执行：Collector → Writer.

    Returns:
        {"evidence_path": Path, "report_content": str, "status": "success"|"failed"}
    """
    from dqg.agent_framework import Agent, LLMConfig
    from dqg.constants import PHASE_DIR_MAP

    dir_suffix = PHASE_DIR_MAP.get(phase_id, f"phase{phase_id}")
    phase_dir = output_dir / project_id / dir_suffix
    int_dir = phase_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: Collector — 只做证据收集
    collector_prompt = _build_collector_prompt(skill_content, phase_id)
    collector = Agent(
        name=f"collector-{phase_id}",
        role="worker",
        system_prompt=collector_prompt,
        model=LLMConfig(primary=worker_model, fallback=fallback),
        output_dir=output_dir,
    )

    collector_result = collector.run(
        "收集证据：读取所有输入文档，提取与本 Phase 相关的关键信息，输出结构化证据列表。",
        context_files=context_files,
    )

    if collector_result.status == "failed":
        return {"status": "failed", "error": "Collector failed"}

    # 保存 evidence pack
    evidence_pack = _parse_evidence_pack(collector_result.content)
    evidence_path = int_dir / "_evidence_pack.json"
    save_json(evidence_path, evidence_pack)

    # Phase 2: Writer — 只看 evidence pack + skill，不看原始文档
    writer_prompt = _build_writer_prompt(skill_content, phase_id)
    writer = Agent(
        name=f"writer-{phase_id}",
        role="worker",
        system_prompt=writer_prompt,
        model=LLMConfig(primary=worker_model, fallback=fallback),
        output_dir=output_dir,
    )

    # Writer 只看 evidence pack，不看原始文档
    writer_result = writer.run(
        "基于证据包生成报告：严格按照 skill 要求，从证据包中提取信息生成结构化报告。",
        context_files=[evidence_path],
    )

    if writer_result.status == "failed":
        return {"status": "failed", "error": "Writer failed"}

    return {
        "status": "success",
        "evidence_path": str(evidence_path),
        "report_content": writer_result.content,
        "collector_tokens": getattr(collector_result, "token_usage", 0),
        "writer_tokens": getattr(writer_result, "token_usage", 0),
    }


def _build_collector_prompt(skill_content: str, phase_id: str) -> str:
    """构建 Collector Agent 的 system prompt."""
    return (
        f"# Evidence Collector — Phase {phase_id}\n\n"
        "你是证据收集专家。你的任务是从输入文档中提取与本 Phase 相关的所有关键信息。\n\n"
        "## 输出格式\n\n"
        "输出 JSON 格式的证据列表：\n"
        "```json\n"
        '{"evidences": [\n'
        '  {"id": "E-001", "source": "文件名:行号", "type": "requirement|design|code|constraint", '
        '"content": "原文摘录", "relevance": "与哪个 REQ/BR/SE 相关"}\n'
        "]}\n"
        "```\n\n"
        "## 收集规则\n\n"
        "1. 每条证据必须有来源标注（文件名:行号）\n"
        "2. 原文摘录必须是原文，不能改写\n"
        "3. 不做分析和判断，只做提取\n"
        "4. 宁多勿少——遗漏比冗余更危险\n\n"
        "## 本 Phase 的关注点\n\n"
        f"{_extract_focus_from_skill(skill_content)}"
    )


def _build_writer_prompt(skill_content: str, phase_id: str) -> str:
    """构建 Writer Agent 的 system prompt."""
    return (
        f"# Report Writer — Phase {phase_id}\n\n"
        "你是报告撰写专家。你的输入是一个结构化的证据包（_evidence_pack.json），"
        "你需要基于这些证据按照 skill 要求生成报告。\n\n"
        "## 关键约束\n\n"
        "1. 只使用证据包中的信息，不要编造\n"
        "2. 每条结论必须引用证据 ID（如 [E-001]）\n"
        "3. 证据包中没有的信息，标记为 GAP\n"
        "4. 严格按照 skill 的输出模板格式\n\n"
        "## Skill 要求\n\n"
        f"{skill_content}"
    )


def _extract_focus_from_skill(skill_content: str) -> str:
    """从 skill 内容中提取收集焦点."""
    # 提取 "核心对象" 或 "产物范围" 章节
    lines = skill_content.split("\n")
    focus_lines: list[str] = []
    in_section = False
    for line in lines:
        if any(kw in line for kw in ("核心对象", "产物范围", "执行流程", "## 输入")):
            in_section = True
            focus_lines.append(line)
            continue
        if in_section:
            if line.startswith("## ") and not any(kw in line for kw in ("核心对象", "产物范围", "执行流程")):
                break
            focus_lines.append(line)

    return "\n".join(focus_lines[:30]) if focus_lines else "按 skill 要求收集所有相关证据。"


def _parse_evidence_pack(content: str) -> dict[str, Any]:
    """从 Collector 输出中解析证据包."""
    import json
    import re

    # 尝试提取 JSON 块
    json_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试裸 JSON
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            pass

    # fallback：把整个内容作为单条证据
    return {
        "evidences": [{
            "id": "E-RAW",
            "source": "collector_output",
            "type": "raw",
            "content": content[:5000],
            "relevance": "全文",
        }],
    }
