"""Multi-Agent Phase 3: 自适应循环 + 多 Judge 投票.

核心能力:
1. Judge 发现问题 → 自动触发 Worker 修正 → 再次 Judge → 循环直到通过
2. 多 Judge 投票（不同模型/不同 prompt），取共识
3. 研发反馈自动路由到对应 Agent 的 bug case 库

用法:
    loop = AdaptiveLoop(output_dir)
    result = loop.run("damage-assessment", "Q01",
        worker_prompt="...", judge_rubric="...",
        max_iterations=3,
        judge_models=["claude-sonnet-4-6", "deepseek-chat"],
    )
"""

from __future__ import annotations

import inspect
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dqg.agents.agent import Agent, extract_llm_call
from dqg.agents.handoff_builder import build_handoff_document
from dqg.agents.issue_tracker import IssueTracker
from dqg.agents.judge_vote import (
    IterationRecord,
    judge_health_check,
    multi_judge_vote,
)
from dqg.agents.llm_backends import LLMConfig
from dqg.agents.loop_health import LoopHealthMonitor
from dqg.agents.pipeline_io import (
    extract_and_save_json,
    format_deterministic_report,
    render_report_from_json,
)
from dqg.constants import DEFAULT_ADAPTIVE_JUDGE_MODELS, STRUCTURED_JSON_MAP
from dqg.log import get_logger
from dqg.schemas import validate_phase_output

log = get_logger(__name__)

# _adaptive_summary.json 里 schema_errors 的上限，防止 Pydantic 长错误污染 summary
_SUMMARY_SCHEMA_ERROR_MAX_ITEMS = 20
_SUMMARY_SCHEMA_ERROR_MAX_CHARS = 300


def _truncate_schema_errors_for_summary(errors: list[str]) -> list[str]:
    """summary 写盘前对 schema_errors 做体积控制：每条 ≤300 字符，最多 20 条."""
    if not errors:
        return []
    trimmed = [
        e if len(e) <= _SUMMARY_SCHEMA_ERROR_MAX_CHARS else e[: _SUMMARY_SCHEMA_ERROR_MAX_CHARS - 1] + "…"
        for e in errors[:_SUMMARY_SCHEMA_ERROR_MAX_ITEMS]
    ]
    if len(errors) > _SUMMARY_SCHEMA_ERROR_MAX_ITEMS:
        trimmed.append(f"…(+{len(errors) - _SUMMARY_SCHEMA_ERROR_MAX_ITEMS} more)")
    return trimmed


if TYPE_CHECKING:
    from pathlib import Path

    from dqg.quality.evaluation_protocols import PhaseProtocol


@dataclass
class AdaptiveResult:
    project_id: str
    phase_id: str
    iterations: list[IterationRecord]
    final_verdict: str  # PASS / FAIL / MAX_ITERATIONS / EARLY_STOP
    total_duration: float = 0
    models_used: list[str] = field(default_factory=list)
    early_stop_reason: str = ""
    health_summary: dict[str, Any] = field(default_factory=dict)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)


class AdaptiveLoop:
    """自适应循环：Judge 不通过 → 自动修正 → 再 Judge → 直到通过或达上限."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def run(
        self,
        project_id: str,
        phase_id: str,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None = None,
        max_iterations: int = 3,
        pass_threshold: float = 3.5,
        worker_model: str = "claude-opus-4-6",
        judge_models: list[str] | None = None,
        fallback: str = "deepseek-chat",
    ) -> AdaptiveResult:
        """执行自适应循环."""
        if judge_models is None:
            judge_models = list(DEFAULT_ADAPTIVE_JUDGE_MODELS)

        from dqg.core.state_machine import PHASE_DEFS
        from dqg.core.state_machine import phase_dir as _pd

        phase_def = PHASE_DEFS.get(phase_id, {})
        pd = _pd(self.output_dir, project_id, phase_def)
        pd.mkdir(parents=True, exist_ok=True)

        # P1: ACT depth — resolve review depth from blast_radius risk_tier
        from dqg.constants import REVIEW_DEPTH_CONFIG, REVIEW_DEPTH_DEFAULT
        from dqg.json_utils import load_json as _load_json

        _blast_path = pd / "_internal" / "_blast_radius.json"
        _risk_tier = REVIEW_DEPTH_DEFAULT
        if _blast_path.exists():
            _blast_data = _load_json(_blast_path)
            if _blast_data and "risk_tier" in _blast_data:
                _risk_tier = _blast_data["risk_tier"]
                log.info("P1 ACT depth: risk_tier=%s from blast_radius", _risk_tier)

        _depth_cfg = REVIEW_DEPTH_CONFIG.get(_risk_tier, REVIEW_DEPTH_CONFIG[REVIEW_DEPTH_DEFAULT])
        # Override max_iterations from depth config (caller can still override via param)
        if max_iterations == 3:  # only override if caller used default
            max_iterations = _depth_cfg["max_iterations"]
            log.info("P1 ACT depth: max_iterations=%d (risk_tier=%s)", max_iterations, _risk_tier)
        _force_secondary = _depth_cfg["force_secondary"]
        _skip_critique = _depth_cfg["skip_critique"]

        # P2: Anchor injection — locate upstream context for anchor extraction
        _upstream_path = pd / "_upstream_context.md"
        if not _upstream_path.exists():
            _upstream_path = pd / "_internal" / "_upstream_context.md"
        _anchor_available = _upstream_path.exists()
        if _anchor_available:
            log.info("P2 anchor: upstream context found at %s", _upstream_path)

        # Resolve SKILL.md path for Critique context injection
        _skill_path: Path | None = None
        _skill_rel = phase_def.get("skill", "")
        if _skill_rel:
            from pathlib import Path as _Path

            _candidate = _Path(_skill_rel)
            if not _candidate.is_absolute():
                _candidate = self.output_dir.parent / _skill_rel
            if _candidate.exists():
                _skill_path = _candidate
                log.info("SKILL resolved for Critique: %s", _skill_path)

        # Prepend bootstrap context if available
        from dqg.constants import PHASE_DIR_MAP

        _dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
        _bootstrap_path = self.output_dir / project_id / _dir_suffix / "_internal" / "_bootstrap_context.md"
        if _bootstrap_path.exists():
            context_files = [_bootstrap_path] + (context_files or [])
            log.info("Bootstrap context prepended: %s", _bootstrap_path)

        # Judge prompt uses the same assembler path as finalize/manual review.
        from dqg.quality.evaluation_protocols import get_protocol
        from dqg.quality.judge import build_judge_prompt

        _protocol = get_protocol(phase_id)
        judge_build = build_judge_prompt(self.output_dir, project_id, phase_id)
        if judge_build:
            judge_rubric = judge_build.prompt
            log.info(
                "Judge prompt assembled: phase=%s, sections=%s",
                phase_id,
                ",".join(judge_build.manifest.assembly_order),
            )

        from dqg.constants import REPORT_MAP

        report_file = REPORT_MAP.get(phase_id, "phase_report.md")
        report_path = pd / report_file

        iterations: list[IterationRecord] = []
        all_llm_calls: list[dict[str, Any]] = []
        issue_tracker = IssueTracker()
        start = time.time()
        final_verdict = "MAX_ITERATIONS"
        monitor = LoopHealthMonitor()
        early_stop_reason = ""

        from dqg.runtime.task_store import complete_task_run, create_task_run

        task_id = create_task_run(
            self.output_dir,
            task_type="adaptive",
            project_id=project_id,
            phase_id=phase_id,
            config={
                "max_iterations": max_iterations,
                "pass_threshold": pass_threshold,
                "worker_model": worker_model,
                "judge_models": judge_models,
            },
        )
        trace_run_id = uuid.uuid4().hex[:12]

        for i in range(max_iterations):
            record, passed, iter_llm_calls = self._execute_iteration(
                i=i,
                pd=pd,
                report_path=report_path,
                worker_prompt=worker_prompt,
                judge_rubric=judge_rubric,
                critique_prompt=critique_prompt,
                context_files=context_files,
                worker_model=worker_model,
                judge_models=judge_models,
                fallback=fallback,
                pass_threshold=pass_threshold,
                iterations=iterations,
                task_id=task_id,
                force_secondary=_force_secondary,
                skip_critique=_skip_critique,
                upstream_path=_upstream_path if _anchor_available else None,
                skill_path=_skill_path,
                protocol=_protocol,
                project_id=project_id,
                phase_id=phase_id,
                trace_run_id=trace_run_id,
            )
            iterations.append(record)
            all_llm_calls.extend(iter_llm_calls)

            # Issue lifecycle tracking
            if record.judge_result is not None:
                judge_issues = []
                for v in record.judge_result.votes:
                    judge_issues.extend(v.issues)
                critique_issues = None
                if record.critique_result and record.critique_result.status != "failed":
                    import json as _json

                    try:
                        _cdata = _json.loads(record.critique_result.content)
                        critique_issues = _cdata.get("findings", [])
                    except (ValueError, AttributeError):
                        pass
                issue_tracker.record_iteration(
                    iteration=record.iteration,
                    judge_issues=judge_issues,
                    critique_issues=critique_issues,
                )

            # 健康监控：记录本轮结果并检查是否应早停
            if record.judge_result is not None:
                all_issues = []
                for v in record.judge_result.votes:
                    all_issues.extend(v.issues)
                health = judge_health_check([record.judge_result])
                monitor.record_iteration(
                    avg_score=record.judge_result.avg_score,
                    issues=all_issues,
                    judge_health=health,
                )

            if passed:
                final_verdict = "PASS" if record.judge_result.consensus == "PASS" else "PASS_WITH_CONCERNS"
                break

            # 早停检查（passed 已 break，这里只检查未通过的情况）
            health_result = monitor.check()
            if health_result.should_stop:
                final_verdict = "EARLY_STOP"
                early_stop_reason = health_result.message
                log.warning("Adaptive loop early stop: %s", health_result.status)
                break

        total_duration = time.time() - start
        models_used = list(set([worker_model, *judge_models, fallback]))

        self._handle_post_loop(
            iterations=iterations,
            final_verdict=final_verdict,
            max_iterations=max_iterations,
            phase_id=phase_id,
            project_id=project_id,
            task_id=task_id,
        )

        complete_task_run(
            self.output_dir,
            task_id,
            status="completed" if final_verdict in ("PASS", "PASS_WITH_CONCERNS") else "failed",
            result_summary=f"{final_verdict} after {len(iterations)} iterations"
            + (f" ({early_stop_reason})" if early_stop_reason else ""),
        )

        result = AdaptiveResult(
            project_id=project_id,
            phase_id=phase_id,
            iterations=iterations,
            final_verdict=final_verdict,
            total_duration=total_duration,
            models_used=models_used,
            early_stop_reason=early_stop_reason,
            health_summary=monitor.get_summary(),
            llm_calls=all_llm_calls,
        )

        self._write_summary(pd, result, issue_tracker)
        return result

    def _schema_errors_after_worker(
        self,
        *,
        project_id: str,
        phase_id: str,
        pd: Path,
        worker_content: str,
        worker_ok: bool,
    ) -> list[str]:
        """从本轮 Worker 输出提取 JSON 并跑 validate_phase_output（与 finalize 同源）.

        契约：
        - phase_id 未在 STRUCTURED_JSON_MAP 注册 → 返回 []（视为本轮无需校验，
          finalize 阶段 validate_phase_output 仍会兜底报 "未知的 Phase ID"）。
        - worker_ok=False → 返回 []（Worker 已失败，跑 schema 校验无意义，由上层处理）。
        - 本轮 Worker 未产出 JSON 块但 phase_dir 有残留 JSON → 清空残留再校验，
          避免把上一轮 JSON 当本轮结果。
        """
        json_file = STRUCTURED_JSON_MAP.get(phase_id)
        if not json_file or not worker_ok:
            return []

        json_path = pd / json_file
        extracted = extract_and_save_json(worker_content, pd, phase_id, project_id)
        if extracted is None and json_path.exists():
            # 避免用上一轮残留 JSON 做误判：本轮未能解析出 JSON 时清空旧文件再校验
            try:
                json_path.unlink()
            except OSError:
                log.debug("Could not remove stale structured JSON: %s", json_path, exc_info=True)

        errors = validate_phase_output(self.output_dir, project_id, phase_id)
        out = list(errors) if errors else []

        if extracted is not None:
            try:
                render_report_from_json(extracted, pd, phase_id)
            except Exception:
                log.debug("render_report_from_json failed after adaptive worker", exc_info=True)

        if out:
            log.info("Adaptive T14: schema_errors count=%d (phase=%s)", len(out), phase_id)
        return out

    def _write_summary(self, pd: Path, result: AdaptiveResult, issue_tracker: IssueTracker | None = None) -> None:
        """Write adaptive loop summary JSON."""
        from dqg.json_utils import save_json

        # 最后一轮仍有 schema_errors = adaptive loop 未修复 schema 问题（AC 3 诊断信号）
        last_schema_errors = result.iterations[-1].schema_errors if result.iterations else []

        summary_path = pd / "_adaptive_summary.json"
        save_json(
            summary_path,
            {
                "project_id": result.project_id,
                "phase_id": result.phase_id,
                "final_verdict": result.final_verdict,
                "early_stop_reason": result.early_stop_reason,
                "total_iterations": len(result.iterations),
                "total_duration": round(result.total_duration, 1),
                "models_used": result.models_used,
                "health_summary": result.health_summary,
                "llm_calls": result.llm_calls,
                "adaptive_loop_schema_unresolved": bool(last_schema_errors),
                "adaptive_loop_last_schema_errors": _truncate_schema_errors_for_summary(last_schema_errors),
                "issue_tracker": {
                    "total": issue_tracker.total,
                    "resolved": issue_tracker.resolved_count,
                    "open": issue_tracker.open_count,
                    "issues": issue_tracker.get_summary(),
                }
                if issue_tracker
                else None,
                "iterations": [
                    {
                        "iteration": r.iteration,
                        "worker_status": r.worker_result.status if r.worker_result else "skipped",
                        "judge_consensus": r.judge_result.consensus if r.judge_result else "skipped",
                        "judge_avg_score": round(r.judge_result.avg_score, 2) if r.judge_result else 0,
                        "fix_applied": r.fix_applied,
                        "duration": round(r.duration, 1),
                        "schema_errors": _truncate_schema_errors_for_summary(r.schema_errors),
                    }
                    for r in result.iterations
                ],
            },
        )

    def _execute_iteration(
        self,
        i: int,
        pd: Path,
        report_path: Path,
        worker_prompt: str,
        judge_rubric: str,
        critique_prompt: str,
        context_files: list[Path] | None,
        worker_model: str,
        judge_models: list[str],
        fallback: str,
        pass_threshold: float,
        iterations: list[IterationRecord],
        task_id: str,
        force_secondary: bool = False,
        skip_critique: bool = False,
        upstream_path: Path | None = None,
        skill_path: Path | None = None,
        protocol: PhaseProtocol | None = None,
        project_id: str = "",
        phase_id: str = "",
        trace_run_id: str = "",
    ) -> tuple[IterationRecord, bool, list[dict[str, Any]]]:
        """执行单轮迭代：Worker → Judge → Critique，返回 (record, passed, llm_calls)."""
        from dqg.reporting.trace_spans import enrich_llm_call_span
        from dqg.runtime.task_store import add_task_event, save_checkpoint

        iter_start = time.time()
        record = IterationRecord(iteration=i + 1)
        iter_llm_calls: list[dict[str, Any]] = []
        span_iter = i + 1
        _span_idx = 0

        def _attach(call: dict[str, Any], agent_step: str) -> dict[str, Any]:
            nonlocal _span_idx
            out = enrich_llm_call_span(
                call,
                project_id=project_id,
                phase_id=phase_id,
                iteration=span_iter,
                agent_step=agent_step,
                trace_run_id=trace_run_id,
                llm_index=_span_idx,
            )
            _span_idx += 1
            return out

        def _agent_run(
            agent: Agent,
            user_msg: str,
            *,
            context_files: list[Any] | None,
            dynamic: list[Any] | None = None,
            span_kw: dict[str, Any],
        ) -> Any:
            try:
                sig = inspect.signature(agent.run)
            except (TypeError, ValueError):
                if dynamic is not None:
                    return agent.run(user_msg, context_files, dynamic)
                return agent.run(user_msg, context_files)
            if "telemetry_span" in sig.parameters:
                return agent.run(
                    user_msg,
                    context_files,
                    dynamic_context_files=dynamic,
                    telemetry_span=span_kw,
                )
            if dynamic is not None:
                return agent.run(user_msg, context_files, dynamic)
            return agent.run(user_msg, context_files)

        no_tool_prefix = (
            "【重要约束】\n"
            "1. 你不能调用任何工具（bash/readFile/grep/fsWrite 等），所有信息已在 context_files 中提供。\n"
            "2. 每条结论必须标注来源（[来源: 文件名:行号]）和置信度（`High`/`Medium`/`Low`）。\n"
            "3. 报告末尾必须包含「自我评审记录」章节（Judge + Critique 视角）。\n"
            "4. 直接输出 Markdown 报告内容，不要输出 JSON 或 tool_call。\n\n"
        )
        if i == 0:
            worker = Agent(
                name=f"worker-iter{i + 1}",
                role="worker",
                system_prompt=no_tool_prefix + worker_prompt,
                model=LLMConfig(primary=worker_model, fallback=fallback),
                output_dir=self.output_dir,
            )
            _ts = {"trace_run_id": trace_run_id, "phase_id": phase_id, "project_id": project_id, "iteration": span_iter}
            record.worker_result = _agent_run(
                worker,
                "基于提供的上下文，执行 Phase 任务，直接输出结构化报告。",
                context_files=context_files,
                span_kw=_ts,
            )
            if record.worker_result.status != "failed":
                report_path.write_text(record.worker_result.content, encoding="utf-8")
        else:
            prev = iterations[-1]
            handoff_path = pd / f"_handoff_iter{i + 1}.md"
            # P2: Extract anchor summary for handoff
            anchor_facts = None
            if upstream_path and upstream_path.exists():
                from dqg.agents.handoff_builder import extract_anchor_summary

                try:
                    anchor_facts = extract_anchor_summary(upstream_path.read_text(encoding="utf-8", errors="replace"))
                except Exception as e:
                    log.debug("P2 anchor extraction failed: %s", e)
            handoff_path.write_text(
                build_handoff_document(prev, i + 1, anchor_facts=anchor_facts),
                encoding="utf-8",
            )
            fixer = Agent(
                name=f"fixer-iter{i + 1}",
                role="worker",
                system_prompt=no_tool_prefix + worker_prompt,
                model=LLMConfig(primary=worker_model, fallback=fallback),
                output_dir=self.output_dir,
            )
            _fixer_dynamic = [handoff_path, report_path]
            if upstream_path and upstream_path.exists():
                _fixer_dynamic.append(upstream_path)
            _ts = {"trace_run_id": trace_run_id, "phase_id": phase_id, "project_id": project_id, "iteration": span_iter}
            record.worker_result = _agent_run(
                fixer,
                f"基于交接文档中的评审反馈修正报告（第 {i + 1} 轮），保持原有格式和结构。",
                context_files=context_files,
                dynamic=_fixer_dynamic,
                span_kw=_ts,
            )
            if record.worker_result.status != "failed":
                report_path.write_text(record.worker_result.content, encoding="utf-8")
                record.fix_applied = True

        # Collect worker LLM call telemetry
        if record.worker_result:
            iter_llm_calls.append(
                _attach(
                    extract_llm_call(record.worker_result),
                    "worker" if i == 0 else "fixer",
                )
            )

        # T14: finalize 同源 schema 校验回流到本轮 Judge + 下轮 handoff（与 phase_runtime 一致）
        record.schema_errors = self._schema_errors_after_worker(
            project_id=project_id,
            phase_id=phase_id,
            pd=pd,
            worker_content=record.worker_result.content if record.worker_result else "",
            worker_ok=record.worker_result is not None and record.worker_result.status != "failed",
        )

        # judge_rubric 保持入参原值，本轮拼接的 deterministic report 不会跨迭代累积
        judge_rubric_iter = judge_rubric
        if record.schema_errors:
            judge_rubric_iter = judge_rubric + "\n\n" + format_deterministic_report(record.schema_errors, phase_id)

        record.judge_result = multi_judge_vote(
            self.output_dir,
            report_path,
            judge_rubric_iter,
            judge_models,
            fallback,
            force_secondary=force_secondary,
        )

        # HARD_BLOCK: multi_judge_vote returns None when guard exhausted
        if record.judge_result is None:
            log.warning("Judge returned None (HARD_BLOCK), stopping adaptive loop")
            record.duration = time.time() - iter_start
            return record, False, iter_llm_calls

        # Collect judge LLM call telemetry
        for vote in record.judge_result.votes:
            if vote.token_usage:
                iter_llm_calls.append(
                    _attach(
                        {
                            "agent_name": f"judge-{vote.model}",
                            "agent_role": "judge",
                            "model_id": vote.model,
                            "prompt_hash": "",
                            "input_tokens": vote.token_usage.get("input_tokens", 0),
                            "output_tokens": vote.token_usage.get("output_tokens", 0),
                            "cache_creation_input_tokens": vote.token_usage.get("cache_creation_input_tokens", 0),
                            "cache_read_input_tokens": vote.token_usage.get("cache_read_input_tokens", 0),
                            "cache_hit": False,
                            "duration_seconds": round(vote.duration, 2),
                            "status": "success" if vote.health == "HEALTHY" else vote.health,
                        },
                        f"judge:{vote.model}",
                    )
                )

        judge_log = pd / f"_judge_iter{i + 1}.json"
        from dqg.json_utils import save_json

        save_json(
            judge_log,
            {
                "iteration": i + 1,
                "consensus": record.judge_result.consensus,
                "avg_score": record.judge_result.avg_score,
                "votes": [
                    {"model": v.model, "verdict": v.verdict, "overall": v.overall} for v in record.judge_result.votes
                ],
                "disagreements": record.judge_result.disagreements,
            },
        )

        record.duration = time.time() - iter_start

        add_task_event(
            self.output_dir,
            task_id,
            "iteration_completed",
            {
                "iteration": i + 1,
                "consensus": record.judge_result.consensus if record.judge_result else "unknown",
                "avg_score": record.judge_result.avg_score if record.judge_result else 0,
            },
        )
        save_checkpoint(
            self.output_dir,
            task_id,
            checkpoint_id=f"iter-{i + 1}",
            phase_id="",
            iteration=i + 1,
            state_snapshot={
                "iterations_completed": i + 1,
                "report_file": str(report_path),
            },
        )

        passed = False
        if (
            record.judge_result.consensus == "PASS"
            or record.judge_result.avg_score >= pass_threshold
            or (
                record.judge_result.consensus == "PASS_WITH_CONCERNS"
                and record.judge_result.avg_score >= pass_threshold - 0.5
            )
        ):
            passed = True

        if not skip_critique:
            # Build Judge issues summary for Critique context
            judge_issues_text = ""
            if record.judge_result and record.judge_result.votes:
                issue_lines = [
                    "## Judge 已发现的问题（不要重复，聚焦新发现）",
                    f"Judge verdict: {record.judge_result.consensus}, avg_score: {record.judge_result.avg_score}",
                    "",
                ]
                for vote in record.judge_result.votes:
                    for issue in vote.issues:
                        sev = issue.get("severity", "?")
                        desc = issue.get("description", "")
                        issue_lines.append(f"- [{sev}] {desc}")
                if len(issue_lines) > 3:  # has actual issues
                    judge_issues_text = "\n".join(issue_lines)

            # Collect context files for Critique: report + upstream evidence + SKILL
            critique_context: list[Path] = [report_path]
            if upstream_path and upstream_path.exists():
                critique_context.append(upstream_path)
            if skill_path and skill_path.exists():
                critique_context.append(skill_path)

            critique_user_msg = "找出报告中的遗漏和错误，给出修正建议。"
            if skill_path:
                critique_user_msg = (
                    "严格按照 SKILL.md 中定义的所有审计维度逐条检查（包括但不限于：SE 覆盖率、路径覆盖、"
                    "断言强度、Mock 真实性、状态机覆盖、可维护性、边界场景、变异测试分析）。\n\n"
                ) + critique_user_msg
            if judge_issues_text:
                critique_user_msg = judge_issues_text + "\n\n" + critique_user_msg

            critique = Agent(
                name=f"critique-iter{i + 1}",
                role="critique",
                system_prompt=critique_prompt,
                model=LLMConfig(primary=fallback, fallback=fallback),
                output_dir=self.output_dir,
            )
            _ts = {"trace_run_id": trace_run_id, "phase_id": phase_id, "project_id": project_id, "iteration": span_iter}
            record.critique_result = _agent_run(
                critique,
                critique_user_msg,
                context_files=critique_context,
                span_kw=_ts,
            )

            # Collect critique LLM call telemetry
            if record.critique_result:
                iter_llm_calls.append(_attach(extract_llm_call(record.critique_result), "critique"))

        return record, passed, iter_llm_calls

    def _handle_post_loop(
        self,
        iterations: list[IterationRecord],
        final_verdict: str,
        max_iterations: int,
        phase_id: str,
        project_id: str,
        task_id: str,
    ) -> None:
        """循环结束后处理：SkillReflector 触发."""
        all_judge_results = [r.judge_result for r in iterations if r.judge_result is not None]
        all_failed = final_verdict not in ("PASS", "PASS_WITH_CONCERNS") and len(iterations) >= max_iterations
        if all_failed and all_judge_results:
            health = judge_health_check(all_judge_results)
            if health == "SEMANTIC_FAIL":
                log.info("All iterations FAIL with healthy judges → triggering SkillReflector")
                from dqg.tracking.skill_reflector import SkillReflector

                reflector = SkillReflector(phase=phase_id, project_id=project_id)
                judge_dicts = []
                for vr in all_judge_results:
                    for v in vr.votes:
                        judge_dicts.append(
                            {
                                "verdict": v.verdict,
                                "overall": v.overall,
                                "issues": v.issues,
                            }
                        )
                evolution_outcome = reflector.reflect_and_write(judge_dicts)
                log.info("SkillReflector outcome: %s", evolution_outcome.action)
            elif health == "INFRA_FAILURE":
                log.warning("Judge infrastructure failure detected, skipping skill evolution")

    def format_result(self, result: AdaptiveResult) -> str:
        """格式化自适应循环结果."""
        lines = [
            f"  自适应 Multi-Agent — Phase {result.phase_id}",
            f"  最终判定: {result.final_verdict}  迭代: {len(result.iterations)}/{3}  耗时: {result.total_duration:.1f}s",
            f"  使用模型: {', '.join(result.models_used)}",
        ]
        for r in result.iterations:
            j = r.judge_result
            judge_info = f"consensus={j.consensus}, avg={j.avg_score:.1f}" if j else ""
            if j and j.disagreements:
                judge_info += f", 分歧={len(j.disagreements)}"
            if r.schema_errors:
                judge_info += f", schema_errors={len(r.schema_errors)}"
            lines.append(
                f"    Iter {r.iteration}: {judge_info}{' [已修正]' if r.fix_applied else ''} ({r.duration:.1f}s)"
            )
        return "\n".join(lines)
