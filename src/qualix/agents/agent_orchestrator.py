"""AgentOrchestrator: 真 Multi-Agent 编排器."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from qualix.agents.agent import Agent, AgentResult
from qualix.agents.builtin_tools import build_builtin_tools
from qualix.agents.llm_backends import LLMConfig
from qualix.agents.pipeline_io import (
    extract_and_save_json,
    format_deterministic_report,
    process_critique_feedback,
    render_report_from_json,
)
from qualix.constants import DEFAULT_FALLBACK_MODEL, DEFAULT_JUDGE_MODEL, DEFAULT_PRIMARY_MODEL, MODEL_TIER
from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.log import get_logger
from qualix.security.tool_permissions import filter_tools_by_role

log = get_logger(__name__)

class AgentOrchestrator:
    """真 Multi-Agent 编排器：独立进程 + 不同模型 + 文件通信."""

    MAX_SUBAGENT_DEPTH = 2
    DEFAULT_SUBAGENT_RESULT_LIMIT = 16_000

    def __init__(self, output_dir: Path, _depth: int = 0, subagent_result_limit: int | None = None):
        self.output_dir = output_dir
        self._depth = _depth
        self.subagent_result_limit = subagent_result_limit or self.DEFAULT_SUBAGENT_RESULT_LIMIT

    def create_worker(
        self, project_id: str, phase_id: str, skill_content: str, tools: list[Callable] | None = None
    ) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 如果你在分析中发现了当前项目代码或需求里有价值的全局约束、隐式逻辑，请立即调用 write_to_wiki 工具将其记入 `.qualix-wiki/`。不要让它随风消逝！"
        phase_def = PHASE_DEFS.get(phase_id, {})
        tier = phase_def.get("recommended_model", "strong")
        model = MODEL_TIER.get(tier, DEFAULT_PRIMARY_MODEL)
        return Agent(
            name=f"{project_id}-{phase_id}-worker",
            role="worker",
            system_prompt=skill_content + writeback_prompt,
            model=LLMConfig(primary=model, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools,
        )

    def create_judge(self, project_id: str, phase_id: str, rubric: str, tools: list[Callable] | None = None) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 本项目已开启 LLM-Wiki。如果你在评审中发现严重且值得沉淀的不良规范，请用 write_to_wiki 将教训写入 `.qualix-wiki/`。"
        return Agent(
            name=f"{project_id}-{phase_id}-judge",
            role="judge",
            system_prompt=rubric + writeback_prompt,
            model=LLMConfig(primary=DEFAULT_JUDGE_MODEL, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools,
        )

    def create_critique(
        self, project_id: str, phase_id: str, critique_prompt: str, tools: list[Callable] | None = None
    ) -> Agent:
        writeback_prompt = "\n\n【The Writeback Discipline 约束】: 如果你在挑错中找出了被违背的设计原则或高频痛点，务必调用 write_to_wiki 工具将其定格入 `.qualix-wiki/`，为长效免疫做贡献。"
        return Agent(
            name=f"{project_id}-{phase_id}-critique",
            role="critique",
            system_prompt=critique_prompt + writeback_prompt,
            model=LLMConfig(primary=DEFAULT_JUDGE_MODEL, fallback=DEFAULT_FALLBACK_MODEL),
            output_dir=self.output_dir,
            tools=tools,
        )

    def run_pipeline(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None = None,
    ) -> dict[str, AgentResult]:
        """执行 Worker -> Judge -> Critique 流水线.

        Phase 2 行为：
        - Worker 在主进程 adaptive_loop 中执行（保留迭代内存状态）
        - Judge 在独立子进程执行（context 完全隔离，见 judge_vote._run_single_judge）
        - Critique 在 Judge 完成后立即提交线程池，与 Worker 下轮迭代无依赖；
          pipeline 等待 Critique 完成后返回完整结果（阻塞直至 Critique 结束）
        """

        results: dict[str, AgentResult] = {}
        builtin_tools = build_builtin_tools(
            output_dir=self.output_dir,
            project_id=project_id,
            max_subagent_depth=self.MAX_SUBAGENT_DEPTH,
            current_depth=self._depth,
            subagent_result_limit=self.subagent_result_limit,
        )

        # Step 1: Worker（主进程，adaptive_loop 管理迭代）
        worker_result, pd, worker_output, structured_json_path = self._run_worker(
            project_id,
            phase_id,
            worker_prompt,
            builtin_tools,
            context_files,
        )
        results["worker"] = worker_result
        if worker_result.status == "failed":
            return results

        # Step 2: Judge（子进程，context 完全隔离）
        judge_result, det_path = self._run_judge(
            project_id,
            phase_id,
            judge_rubric,
            builtin_tools,
            pd,
            worker_output,
            structured_json_path,
        )
        results["judge"] = judge_result

        # Step 3: Critique — Judge 完成后直接调用（无需 ThreadPoolExecutor）
        try:
            critique_result = self._run_critique(
                project_id,
                phase_id,
                critique_prompt,
                builtin_tools,
                pd,
                worker_output,
                structured_json_path,
                det_path,
                judge_result,
            )
        except Exception as exc:
            log.error(
                "Critique failed for project=%s phase=%s: %s",
                project_id, phase_id, exc, exc_info=True,
            )
            critique_result = AgentResult(
                agent_name=f"{project_id}-{phase_id}-critique",
                role="critique",
                status="failed",
                error=str(exc),
            )

        results["critique"] = critique_result

        self._save_trajectories(results, project_id, phase_id)

        gap_tasks_path = pd / "_coverage_gap_tasks.json"
        if gap_tasks_path.exists():
            self._auto_remediate_gaps(project_id, phase_id, gap_tasks_path, worker_prompt, builtin_tools)

        return results

    # TODO: add subprocess isolation for Critique (critique_runner_subprocess) once
    # that module is implemented — mirror the judge_vote._run_single_judge pattern.

    def _run_worker(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        builtin_tools: list,
        context_files: list[Path] | None,
    ) -> tuple[AgentResult, Path, Path, Path | None]:
        worker_tools = filter_tools_by_role(builtin_tools, "worker")
        worker = self.create_worker(project_id, phase_id, worker_prompt, tools=worker_tools)

        if phase_id == "Q01":
            instruction = (
                "执行 Phase A 需求结构化。你的首要输出是 RSM（需求语义模型）——"
                "一份完整的结构化 JSON，包含所有 REQ/BR/SE/GAP/OPEN。"
                "这份 RSM 将作为整个 pipeline 的数据总线，驱动后续所有 Phase。"
                "每条 REQ 必须有明确的 description 和 acceptance_criteria；"
                "每条 GAP 必须有 required_clarification；"
                "每条 SE 必须标注 category。"
                "JSON 是唯一的正式产物，md 报告会从 JSON 自动生成。"
            )
        else:
            instruction = (
                "执行 Phase 任务。你的主要输出是结构化 JSON（严格遵循 schema）。"
                "在 JSON 之外可以附加推理过程，但 JSON 是唯一的正式产物。"
            )

        result = worker.run(instruction, context_files)

        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _phase_dir(self.output_dir, project_id, phase_def)
        pd.mkdir(parents=True, exist_ok=True)

        worker_output = pd / "_worker_output.md"
        worker_output.write_text(result.content, encoding="utf-8")

        structured_json_path = extract_and_save_json(result.content, pd, phase_id, project_id)
        if structured_json_path and structured_json_path.exists():
            render_report_from_json(structured_json_path, pd, phase_id)

        from qualix.schemas.rsm import load_rsm

        rsm_lifecycle = load_rsm(self.output_dir, project_id)
        if rsm_lifecycle:
            log.info("RSM updated after Phase %s: %d items", phase_id, len(rsm_lifecycle))

        return result, pd, worker_output, structured_json_path

    def _run_judge(
        self,
        project_id: str,
        phase_id: str,
        judge_rubric: str,
        builtin_tools: list,
        pd: Path,
        worker_output: Path,
        structured_json_path: Path | None,
    ) -> tuple[AgentResult, Path]:
        from qualix.quality.auto_checks import auto_derive_checks

        deterministic_errors = auto_derive_checks(self.output_dir, project_id, phase_id)
        deterministic_report = format_deterministic_report(deterministic_errors, phase_id)
        det_path = pd / "_deterministic_check.md"
        det_path.write_text(deterministic_report, encoding="utf-8")

        judge_tools = filter_tools_by_role(builtin_tools, "judge")
        judge = self.create_judge(project_id, phase_id, judge_rubric, tools=judge_tools)
        judge_context = []
        if structured_json_path and structured_json_path.exists():
            judge_context.append(structured_json_path)
        else:
            judge_context.append(worker_output)
        judge_context.append(det_path)

        result = judge.run(
            "评审以下结构化产物的质量。\n\n"
            "注意：_deterministic_check.md 包含自动化校验结果（schema/交叉引用/覆盖率），"
            "这些是已确认的事实，不需要重复检查。\n"
            "你的职责是补充 deterministic checker 无法覆盖的语义判断：\n"
            "1. 需求完整性（是否有遗漏的隐式需求）\n"
            "2. 逻辑一致性（需求之间是否矛盾）\n"
            "3. 可实现性（技术方案是否可行）\n"
            "4. 风险识别（是否有未被标注的风险）\n\n"
            "输出 JSON 格式的评审结果。",
            context_files=judge_context,
        )

        if result.status != "failed":
            (pd / "_judge_result_v2.json").write_text(result.content, encoding="utf-8")

        return result, det_path

    def _run_critique(
        self,
        project_id: str,
        phase_id: str,
        critique_prompt: str,
        builtin_tools: list,
        pd: Path,
        worker_output: Path,
        structured_json_path: Path | None,
        det_path: Path,
        judge_result: AgentResult,
    ) -> AgentResult:
        critique_tools = filter_tools_by_role(builtin_tools, "critique")
        critique = self.create_critique(project_id, phase_id, critique_prompt, tools=critique_tools)
        critique_files = (
            [structured_json_path] if structured_json_path and structured_json_path.exists() else [worker_output]
        )
        if judge_result.status != "failed":
            critique_files.append(pd / "_judge_result_v2.json")
        critique_files.append(det_path)

        result = critique.run(
            "假设产物有遗漏和错误，主动找问题。\n\n"
            "【重要】你的输出必须是结构化可执行反馈 JSON，格式如下：\n"
            '{"phase_id": "' + phase_id + '", "items": [\n'
            '  {"target_id": "REQ-001", "action": "modify", '
            '"reason": "描述不完整", "patch": "新的描述内容", '
            '"confidence": 0.9, "evidence_source": "PRD 第3段"}\n'
            '], "summary": "最严重的问题是..."}\n\n'
            "action 可选值: add / modify / delete / escalate\n"
            "confidence < 0.5 的反馈会被 Worker 忽略，请确保每条反馈有充分证据。",
            context_files=critique_files,
        )

        if result.status != "failed":
            (pd / "_critique_v2.json").write_text(result.content, encoding="utf-8")
            process_critique_feedback(result.content, pd, phase_id)

        return result

    def _save_trajectories(self, results: dict[str, AgentResult], project_id: str, phase_id: str) -> None:
        from qualix.quality.trajectory import compress_trajectory, save_trajectories

        trajectories = []
        for role_name, agent_result in results.items():
            if agent_result.trajectory:
                trajectories.append(
                    compress_trajectory(
                        trajectory=agent_result.trajectory,
                        project_id=project_id,
                        phase_id=phase_id,
                        agent_name=agent_result.agent_name,
                        agent_role=role_name,
                        model_used=agent_result.model_used,
                        status=agent_result.status,
                        duration_seconds=agent_result.duration_seconds,
                        token_usage=agent_result.token_usage,
                    )
                )
        if trajectories:
            save_trajectories(self.output_dir, project_id, phase_id, trajectories)

    def _auto_remediate_gaps(
        self,
        project_id: str,
        phase_id: str,
        gap_tasks_path: Path,
        worker_prompt: str,
        builtin_tools: list,
    ) -> None:
        """Coverage Gap 自动补充."""

        from qualix.json_utils import load_json_strict

        gap_data = load_json_strict(gap_tasks_path)
        tasks = gap_data.get("tasks", [])
        if not tasks:
            return

        tasks = tasks[:5]
        target_ids = [t["target_id"] for t in tasks]
        actions = [f"- {t['target_id']}: {t['action']}（{t['description'][:60]}）" for t in tasks]

        log.info("Auto-remediating %d coverage gaps for Phase %s: %s", len(tasks), phase_id, target_ids)

        remediation_prompt = (
            f"## 覆盖率缺口定向补充 — Phase {phase_id}\n\n"
            f"以下 ID 在 RSM 覆盖率检查中被标记为缺口，请针对性补充：\n\n"
            + "\n".join(actions)
            + "\n\n请只补充以上列出的缺口，不要修改已有的产出物。"
            + "输出补充内容的结构化 JSON。"
        )

        worker_tools = filter_tools_by_role(builtin_tools, "worker")
        remediation_worker = self.create_worker(
            project_id,
            phase_id,
            worker_prompt,
            tools=worker_tools,
        )

        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _phase_dir(self.output_dir, project_id, phase_def)

        result = remediation_worker.run(
            remediation_prompt,
            context_files=[
                pd / f for f in (pd.iterdir()) if f.suffix in (".json", ".md") and not f.name.startswith("_")
            ]
            if pd.exists()
            else None,
        )

        if result.status != "failed":
            remediation_path = pd / "_remediation_output.md"
            remediation_path.write_text(result.content, encoding="utf-8")
            log.info("Remediation completed for %d gaps", len(tasks))

            from qualix.schemas.rsm import load_rsm

            rsm_lifecycle = load_rsm(self.output_dir, project_id)
            if rsm_lifecycle:
                log.info("RSM refreshed after remediation: %d items", len(rsm_lifecycle))

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


# ---------------------------------------------------------------------------
# Prompt builders — canonical home; multi_agent.py re-exports these
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

    from qualix.context.enum_contract import render_enum_contract_prefix

    enum_block = render_enum_contract_prefix(phase_id)
    head: list[str] = [
        f"# Worker Agent — Phase {phase_id}",
        f"项目: {project_id}",
        f"产物目录: {pd}",
        "",
    ]
    if enum_block:
        head.extend(["## ENUM_CONTRACT（与 schema 同源）", "", enum_block, ""])
    parts = [
        *head,
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

    ctx_path = pd / "_upstream_context.md"
    if ctx_path.exists():
        parts.append("## 上游 Context（已缓存，直接使用）")
        parts.append(f"文件: {ctx_path}")
        parts.append("")

    img_path = pd / "image_semantics.md"
    if img_path.exists():
        parts.append("## 图片语义（已缓存，不要重新读图片）")
        parts.append(f"文件: {img_path}")
        parts.append("")

    if inputs:
        parts.append("## 额外输入")
        for k, v in inputs.items():
            parts.append(f"- {k}: {v}")
        parts.append("")

    from qualix.constants import REPORT_MAP

    report_file = REPORT_MAP.get(phase_id)
    is_rerun = report_file and (pd / report_file).exists()
    if is_rerun:
        upstream_path = pd / "_upstream_context.md"
        if not upstream_path.exists():
            upstream_path = pd / "_internal" / "_upstream_context.md"
        if upstream_path.exists():
            from qualix.agents.handoff_builder import extract_anchor_summary

            try:
                anchor = extract_anchor_summary(upstream_path.read_text(encoding="utf-8", errors="replace"))
                if anchor:
                    parts.append(anchor)
                    parts.append("")
            except Exception as e:
                log.debug("Anchor extraction failed (non-blocking): %s", e)

    return "\n".join(parts)


def generate_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str:
    """生成 Judge Agent 的 prompt（委托 quality/judge.py 的标准实现）."""
    from qualix.quality.judge import generate_judge_prompt as _canonical_judge_prompt

    result = _canonical_judge_prompt(output_dir, project_id, phase_id)
    if result:
        return result

    phase_def = PHASE_DEFS.get(phase_id, {})
    pd = _phase_dir(output_dir, project_id, phase_def)
    return f"# Judge Agent — Phase {phase_id}\n项目: {project_id}\n\n请评审 {pd} 下的产物质量，按 1-5 分打分。\n"


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
    ]

    from qualix.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt

    _protocol = get_protocol(phase_id)
    if _protocol:
        parts.append(render_protocol_for_prompt(_protocol.critique))
        parts.append("")
    else:
        parts.extend(
            [
                "## 你的角色",
                "你是 Critique Agent。假设 Worker 的产物有遗漏和错误，主动找问题。",
                "你已经看到了 Judge 的评审结果，你的任务是找到 Judge 也没发现的问题。",
                "",
                "## 重点检查方向",
                "1. 并发/幂等/事务 — 是否遗漏了并发场景的 GAP？",
                "2. 异常流 — 每个外部调用（保司接口/MQ/定时任务）的失败处理是否有 SE 或 GAP？",
                "3. 状态迁移边界 — 每条状态迁移边是否都有数据流定义？",
                "4. 权限/安全 — 数据隔离、脱敏、越权访问是否有 SE？",
                "5. 业务常识 — 是否有把正常业务流程当缺口的 GAP？",
                "",
            ]
        )

    parts.extend(
        [
            "## 输入",
            f"报告: {pd / 'phase_a_report.md'}",
            f"Judge 结果: {pd / '_judge_result.json'}",
            "",
            "## 输出格式",
            f"写入 JSON 到: {pd / '_critique.json'}",
            "```json",
            "{",
            '  "issues_found": [{"type": "FN/FP", "severity": "...", "description": "...", "suggestion": "..."}],',
            '  "revision_needed": true/false,',
            '  "summary": "..."',
            "}",
            "```",
        ]
    )

    return "\n".join(parts)
