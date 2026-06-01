"""Multi-Agent Orchestrator: DAG 调度 Worker/Judge/Critique 独立 Agent.

Phase 2: true subprocess isolation for Judge; Critique dispatched immediately
after Judge completes.

Worker 在主进程 adaptive_loop 中执行（迭代需要内存状态）。
Judge 通过 judge_runner_subprocess 在独立子进程运行（context 完全隔离）。
Critique 在 Judge 输出文件写入后立即启动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from qualix.agents.agent_orchestrator import (
    generate_critique_prompt,
    generate_judge_prompt,
    generate_worker_prompt,
)
from qualix.core.state_machine import PHASE_DEFS
from qualix.log import get_logger

log = get_logger(__name__)
from qualix.core.state_machine import phase_dir as _phase_dir

# Re-exported for backward compatibility
__all__ = ["generate_worker_prompt", "generate_judge_prompt", "generate_critique_prompt"]

# ---------------------------------------------------------------------------
# Agent 角色定义
# ---------------------------------------------------------------------------


@dataclass
class AgentRole:
    name: str
    role: str  # worker / judge / critique
    prompt_template: str
    input_files: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


# Phase A 的三个 Agent
PHASE_A_AGENTS: Final = MappingProxyType(
    {
        "worker": AgentRole(
            name="phase-a-worker",
            role="worker",
            prompt_template="worker_prompt.md",
            input_files=["_upstream_context.md", "image_semantics.md"],
            output_files=["phase_a_report.md", "phase_a_structured.json", "_reasoning_log.md"],
            depends_on=[],
        ),
        "judge": AgentRole(
            name="phase-a-judge",
            role="judge",
            prompt_template="judge_prompt.md",
            input_files=["phase_a_report.md", "phase_a_structured.json"],
            output_files=["_judge_result.json"],
            depends_on=["worker"],
        ),
        "critique": AgentRole(
            name="phase-a-critique",
            role="critique",
            prompt_template="critique_prompt.md",
            input_files=["phase_a_report.md", "_judge_result.json"],
            output_files=["_critique.json"],
            depends_on=["judge"],
        ),
    }
)

# Phase 间 DAG 单一来源来自 phase_registry.PHASE_DEFS。
PHASE_DAG: Final = MappingProxyType(
    {phase_id: list(phase_def.get("depends_on", [])) for phase_id, phase_def in PHASE_DEFS.items()}
)


# ---------------------------------------------------------------------------
# Prompt 生成（实装在 agent_orchestrator.py，此处 re-export 供向后兼容）
# generate_worker_prompt / generate_judge_prompt / generate_critique_prompt
# 已在文件顶部通过 import 引入，__all__ 声明向外暴露
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class MultiAgentOrchestrator:
    """DAG 调度器：编排 Worker → Judge → Critique 流程."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def get_ready_phases(self, project_id: str) -> list[str]:
        """获取当前可执行的 Phase（依赖已满足）."""
        from qualix.core.state_machine import load_state

        state = load_state(self.output_dir, project_id)

        ready = []
        for phase_id, deps in PHASE_DAG.items():
            ps = state.phases.get(phase_id)
            if ps and ps.status in ("approved", "skipped"):
                continue  # 已完成
            if ps and ps.status in ("in_progress", "pending_review"):
                continue  # 进行中

            # 检查依赖
            all_deps_met = all(
                state.phases.get(d, {}).status in ("approved", "skipped")
                if hasattr(state.phases.get(d, {}), "status")
                else False
                for d in deps
            )
            if all_deps_met:
                ready.append(phase_id)

        return ready

    def generate_prompts(
        self,
        project_id: str,
        phase_id: str,
        inputs: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """生成三个 Agent 的 prompt 文件，返回文件路径."""
        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _phase_dir(self.output_dir, project_id, phase_def)
        pd.mkdir(parents=True, exist_ok=True)

        skill_path = phase_def.get("skill", "")
        prompts = {}

        # Worker prompt
        worker_prompt = generate_worker_prompt(self.output_dir, project_id, phase_id, skill_path, inputs)
        wp = pd / "_worker_prompt.md"
        wp.write_text(worker_prompt, encoding="utf-8")
        prompts["worker"] = str(wp)

        # Judge prompt
        judge_prompt = generate_judge_prompt(self.output_dir, project_id, phase_id)
        jp = pd / "_judge_prompt_v2.md"
        jp.write_text(judge_prompt, encoding="utf-8")
        prompts["judge"] = str(jp)

        # Critique prompt
        critique_prompt = generate_critique_prompt(self.output_dir, project_id, phase_id)
        cp = pd / "_critique_prompt_v2.md"
        cp.write_text(critique_prompt, encoding="utf-8")
        prompts["critique"] = str(cp)

        return prompts

    def get_parallel_phases(self, project_id: str) -> list[list[str]]:
        """获取可并行执行的 Phase 组."""
        ready = self.get_ready_phases(project_id)
        if not ready:
            return []

        # 按依赖层级分组
        groups: list[list[str]] = []
        remaining = set(ready)

        while remaining:
            # 找出当前没有未完成依赖的 phase
            batch = []
            for p in remaining:
                deps = PHASE_DAG.get(p, [])
                if all(d not in remaining for d in deps):
                    batch.append(p)
            if not batch:
                break
            groups.append(sorted(batch))
            remaining -= set(batch)

        return groups

    def format_execution_plan(self, project_id: str) -> str:
        """格式化执行计划."""
        groups = self.get_parallel_phases(project_id)
        if not groups:
            return "  所有 Phase 已完成或无可执行 Phase"

        lines = ["  Multi-Agent 执行计划:"]
        for i, group in enumerate(groups):
            parallel = " + ".join(group)
            lines.append(f"    Step {i + 1}: {parallel}{'（并行）' if len(group) > 1 else ''}")
            for _phase_id in group:
                lines.append("      └── Worker → Judge → Critique")

        return "\n".join(lines)

