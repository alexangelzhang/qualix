"""Multi-Agent Orchestrator: DAG 调度 Worker/Judge/Critique 独立 Agent.

Phase 1 实现：用 Claude Code 的 Agent tool 模拟独立 agent，
通过文件交换数据，context 隔离。

用法:
    orchestrator = MultiAgentOrchestrator(output_dir)
    result = orchestrator.run_phase("damage-assessment", "A", {
        "prd_url": "https://...",
    })
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir


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
PHASE_A_AGENTS = {
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

# Phase 间 DAG
PHASE_DAG: dict[str, list[str]] = {
    "A": [],
    "A.5": ["A"],
    "A.6": ["A"],
    "B": ["A"],
    "C": ["B"],
    "D": ["A.5", "A.6"],
}


# ---------------------------------------------------------------------------
# Prompt 生成
# ---------------------------------------------------------------------------

def generate_worker_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    skill_path: str,
    inputs: dict[str, str] | None = None,
) -> str:
    """生成 Worker Agent 的完整 prompt."""
    phase_def = PHASE_DEFS.get(phase_id, {})
    pd = _phase_dir(output_dir, project_id, phase_def)

    parts = [
        f"# Worker Agent — Phase {phase_id}",
        f"项目: {project_id}",
        f"产物目录: {pd}",
        "",
        "## 任务",
        f"严格按照 skill 文件 `{skill_path}` 的 Step 0-6 执行 Phase {phase_id}。",
        "输出报告和结构化 JSON 到产物目录。",
        "必须输出 `_reasoning_log.md` 记录每步决策过程。",
        "",
        "## 约束",
        "- 你是 Worker Agent，只负责执行，不负责评审",
        "- 严格遵循 skill 中的规则和禁止事项",
        "- 每条结论标注来源和置信度",
        "",
    ]

    # 加载上游 context（如果存在）
    ctx_path = pd / "_upstream_context.md"
    if ctx_path.exists():
        parts.append("## 上游 Context（已缓存，直接使用）")
        parts.append(f"文件: {ctx_path}")
        parts.append("")

    # 加载图片语义缓存
    img_path = pd / "image_semantics.md"
    if img_path.exists():
        parts.append("## 图片语义（已缓存，不要重新读图片）")
        parts.append(f"文件: {img_path}")
        parts.append("")

    # 额外输入
    if inputs:
        parts.append("## 额外输入")
        for k, v in inputs.items():
            parts.append(f"- {k}: {v}")
        parts.append("")

    return "\n".join(parts)


def generate_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str:
    """生成 Judge Agent 的 prompt（独立 context，看不到 Worker 推理过程）."""
    phase_def = PHASE_DEFS.get(phase_id, {})
    pd = _phase_dir(output_dir, project_id, phase_def)

    report_map = {
        "A": "phase_a_report.md",
        "A.5": "tech_design_coverage_review.md",
        "A.6": "tech_design_quality_review.md",
        "B": "eut_matrix.md",
        "C": "ut_audit_report.md",
        "D": "review_report.md",
    }
    report_file = report_map.get(phase_id, "")

    parts = [
        f"# Judge Agent — Phase {phase_id}",
        f"项目: {project_id}",
        "",
        "## 你的角色",
        "你是独立的评审 Agent。你看不到 Worker 的推理过程，只看最终产物。",
        "你的任务是客观评估产物质量，不要被产物中的'自信'表述影响。",
        "",
        "## 评审对象",
        f"报告文件: {pd / report_file}",
        "",
        "## 评审维度（1-5 Likert 量表）",
        "",
        "### faithfulness（忠实度）",
        "- 5: 每条结论都有 PRD 原文行号引用，零幻觉",
        "- 4: 绝大多数有引用，个别推导已标注置信度",
        "- 3: 部分结论缺少引用",
        "- 2: 多处无引用或引用错误",
        "- 1: 大量幻觉",
        "",
        "### completeness（完整度）",
        "- 5: PRD 所有功能模块+图片语义+操作流程全覆盖",
        "- 4: 主要功能覆盖，个别细节遗漏",
        "- 3: 有明显遗漏（如缺状态机/缺操作流程）",
        "- 2: 大量遗漏",
        "- 1: 严重不完整",
        "",
        "### se_explicitness（语义显式化）",
        "- 5: 每个 SE 有判定依据表格，可直接写测试",
        "- 4: 绝大多数有判定依据",
        "- 3: 部分 SE 缺判定依据",
        "- 2: 多数 SE 无判定依据",
        "- 1: SE 形同虚设",
        "",
        "### gap_detection（缺口发现）",
        "- 5: GAP 全部有风险等级，无过度推断，无遗漏",
        "- 4: GAP 基本准确，个别可商榷",
        "- 3: 有过度推断或明显遗漏",
        "- 2: 多处过度推断",
        "- 1: GAP 不可信",
        "",
        "### structure_quality（结构质量）",
        "- 5: 状态机准确（节点/边区分正确），流程图无错误节点，BR 保留层级",
        "- 4: 基本准确，个别瑕疵",
        "- 3: 有结构性错误（如动作当状态）",
        "- 2: 多处结构错误",
        "- 1: 结构不可用",
        "",
        "## 重点检查（已知 bug 模式）",
        "- 状态机：是否把迁移动作画成了状态节点？",
        "- 状态机：驳回循环的目标节点是否正确？",
        "- 状态机：正常路径和异常终结是否分开？",
        "- 流程图：是否把 UI 提示当成了流程节点？",
        "- BR：是否压平了 PRD 的层级结构？",
        "- GAP：是否把正常设计决策当成了缺口？",
        "- 是否缺少用户操作流程视角？",
        "",
        "## 输出格式",
        f"写入 JSON 到: {pd / '_judge_result.json'}",
        "```json",
        '{',
        '  "scores": {"faithfulness": N, "completeness": N, "se_explicitness": N, "gap_detection": N, "structure_quality": N},',
        '  "overall": N.N,',
        '  "issues": [{"type": "FN/FP/VAGUE", "severity": "critical/high/medium/low", "description": "...", "suggestion": "..."}],',
        '  "verdict": "PASS / PASS_WITH_CONCERNS / FAIL"',
        '}',
        "```",
    ]

    return "\n".join(parts)


def generate_critique_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str:
    """生成 Critique Agent 的 prompt."""
    phase_def = PHASE_DEFS.get(phase_id, {})
    pd = _phase_dir(output_dir, project_id, phase_def)

    parts = [
        f"# Critique Agent — Phase {phase_id}",
        f"项目: {project_id}",
        "",
        "## 你的角色",
        "你是 Critique Agent。假设 Worker 的产物有遗漏和错误，主动找问题。",
        "你已经看到了 Judge 的评审结果，你的任务是找到 Judge 也没发现的问题。",
        "",
        "## 输入",
        f"报告: {pd / 'phase_a_report.md'}",
        f"Judge 结果: {pd / '_judge_result.json'}",
        "",
        "## 重点检查方向",
        "1. 并发/幂等/事务 — 是否遗漏了并发场景的 GAP？",
        "2. 异常流 — 每个外部调用（保司接口/MQ/定时任务）的失败处理是否有 SE 或 GAP？",
        "3. 状态迁移边界 — 每条状态迁移边是否都有数据流定义？",
        "4. 权限/安全 — 数据隔离、脱敏、越权访问是否有 SE？",
        "5. 业务常识 — 是否有把正常业务流程当缺口的 GAP？",
        "",
        "## 输出格式",
        f"写入 JSON 到: {pd / '_critique.json'}",
        "```json",
        '{',
        '  "issues_found": [{"type": "FN/FP", "severity": "...", "description": "...", "suggestion": "..."}],',
        '  "revision_needed": true/false,',
        '  "summary": "..."',
        '}',
        "```",
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    agent_name: str
    role: str
    status: str  # success / failed / skipped
    output_files: list[str] = field(default_factory=list)
    duration_seconds: float = 0
    error: str = ""


class MultiAgentOrchestrator:
    """DAG 调度器：编排 Worker → Judge → Critique 流程."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def get_ready_phases(self, project_id: str) -> list[str]:
        """获取当前可执行的 Phase（依赖已满足）."""
        from dqg.core.state_machine import load_state
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
                if hasattr(state.phases.get(d, {}), 'status')
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
        worker_prompt = generate_worker_prompt(
            self.output_dir, project_id, phase_id, skill_path, inputs
        )
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
            lines.append(f"    Step {i+1}: {parallel}{'（并行）' if len(group) > 1 else ''}")
            for phase_id in group:
                lines.append(f"      └── Worker → Judge → Critique")

        return "\n".join(lines)
