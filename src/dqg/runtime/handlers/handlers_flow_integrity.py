"""FlowIntegrity Handler: finalize 流程完整性检查（两阶段）.

两个 handler 分工：
- handle_flow_integrity_pre (order=5): 检查基础产物（报告/JSON/schema 非空）
  在所有 handler 之前执行，CRITICAL 问题直接 BLOCKED
- handle_flow_integrity_post (order=76): 检查 judge/critique 闭环
  在 auto_judge(order=75) 之后执行，确保 judge result 已生成

严重度分级：
- CRITICAL → BLOCKED（finalize 不通过）
- HIGH → WARNING（允许通过但标记）
- MEDIUM → INFO（仅记录）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger
from dqg.quality.judge_rubrics import JUDGE_RUBRICS
from dqg.runtime.events import EventType
from dqg.runtime.lifecycle import register_handler

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 检查函数：每个返回 (severity, message) 列表
# ---------------------------------------------------------------------------


def _check_structured_json_nonempty(
    pd: Path,
    phase_id: str,
) -> list[tuple[str, str]]:
    """CRITICAL: 结构化 JSON 必须存在且非空."""
    issues: list[tuple[str, str]] = []
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return issues

    json_path = pd / json_file
    if not json_path.exists():
        issues.append(("CRITICAL", f"结构化产物 {json_file} 不存在"))
        return issues

    data = load_json(json_path)
    if data is None:
        issues.append(("CRITICAL", f"结构化产物 {json_file} JSON 解析失败（文件损坏）"))
        return issues

    if isinstance(data, dict) and not data:
        issues.append(("CRITICAL", f"结构化产物 {json_file} 为空对象"))

    return issues


def _check_report_exists(
    pd: Path,
    phase_id: str,
) -> list[tuple[str, str]]:
    """CRITICAL: 报告文件必须存在且有实质内容."""
    issues: list[tuple[str, str]] = []
    report_file = REPORT_MAP.get(phase_id)
    if not report_file:
        return issues

    report_path = pd / report_file
    if not report_path.exists():
        issues.append(("CRITICAL", f"报告文件 {report_file} 不存在"))

    return issues


def _check_judge_result(
    pd: Path,
    phase_id: str,
) -> list[tuple[str, str]]:
    """CRITICAL: judge_result 必须存在且可解析.
    HIGH: judge dimensions 必须匹配 rubric.
    """
    issues: list[tuple[str, str]] = []
    result_path = pd / "_judge_result.json"

    # judge prompt 存在但 result 不存在 → CRITICAL
    prompt_path = pd / "_judge_prompt.md"
    if prompt_path.exists() and not result_path.exists():
        issues.append(
            (
                "CRITICAL",
                "_judge_prompt.md 已生成但 _judge_result.json 不存在 — Judge 评审未执行或结果未写回",
            )
        )
        return issues

    if not result_path.exists():
        # 没有 prompt 也没有 result，可能是不支持 judge 的 phase
        rubric = JUDGE_RUBRICS.get(phase_id)
        if rubric:
            issues.append(("HIGH", f"Phase {phase_id} 支持 Judge 评审但 _judge_result.json 不存在"))
        return issues

    data = load_json(result_path)
    if data is None:
        issues.append(("CRITICAL", "_judge_result.json JSON 解析失败（文件损坏）"))
        return issues

    # 检查必要字段
    if "overall_score" not in data:
        issues.append(("CRITICAL", "_judge_result.json 缺少 overall_score 字段"))

    if "dimensions" not in data:
        issues.append(("HIGH", "_judge_result.json 缺少 dimensions 字段"))
    else:
        # 检查 dimensions 是否匹配 rubric
        rubric = JUDGE_RUBRICS.get(phase_id)
        if rubric and not data.get("auto_synthesized"):
            expected_dims = {d["id"] for d in rubric.get("dimensions", [])}
            actual_dims = {d.get("id", "") for d in data.get("dimensions", [])}
            missing = expected_dims - actual_dims
            if missing:
                issues.append(
                    (
                        "HIGH",
                        f"Judge dimensions 不匹配 rubric: 缺少 {', '.join(sorted(missing))}",
                    )
                )

    return issues


def _check_critique_closure(
    pd: Path,
    phase_id: str,
) -> list[tuple[str, str]]:
    """CRITICAL: critique prompt 存在时，critique result 也应存在.
    MEDIUM: preference 存在时，critique 也应存在.
    """
    issues: list[tuple[str, str]] = []

    critique_prompt = pd / "_critique_prompt.md"
    critique_result = pd / "_critique.json"
    preference_result = pd / "_preference.json"

    if critique_prompt.exists() and not critique_result.exists():
        issues.append(
            (
                "CRITICAL",
                "_critique_prompt.md 已生成但 _critique.json 不存在 — Critique 未执行，RLAIF 反馈循环断裂",
            )
        )

    if preference_result.exists() and not critique_result.exists():
        issues.append(
            (
                "MEDIUM",
                "_preference.json 存在但 _critique.json 不存在 — Gene/Capsule 提取将被跳过",
            )
        )

    # 检查 preference 说 v2 更好但 v2 文件不存在
    if preference_result.exists():
        pref = load_json(preference_result)
        if pref and pref.get("preferred") == "v2":
            report_file = REPORT_MAP.get(phase_id, "")
            if report_file:
                v2_report = pd / report_file.replace(".md", "_v2.md")
                if not v2_report.exists():
                    issues.append(
                        (
                            "MEDIUM",
                            f"Preference 判定 v2 更好但 {v2_report.name} 不存在",
                        )
                    )

    return issues


def _check_schema_semantic_completeness(
    pd: Path,
    phase_id: str,
) -> list[tuple[str, str]]:
    """HIGH: 结构化 JSON 的关键数组不能为空（可能是 Worker 未产出有效内容）."""
    issues: list[tuple[str, str]] = []
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return issues

    json_path = pd / json_file
    if not json_path.exists():
        return issues  # 已在 _check_structured_json_nonempty 中报告

    data = load_json(json_path)
    if not isinstance(data, dict):
        return issues

    # Phase 特定的核心数组字段（空数组 = 可能是 Worker 未产出）
    core_arrays: dict[str, list[str]] = {
        "Q01": ["requirements"],
        "Q02": ["req_mapping", "interfaces"],
        "Q03": ["issues"],
        "Q04": ["coverage_summary"],
        "Q05": ["eut_items"],
        "Q05a": ["eut_items"],
        "Q05b": ["tasks"],
        "Q06": ["audit_items"],
        "Q07": ["findings"],
    }

    fields = core_arrays.get(phase_id, [])
    for field_name in fields:
        val = data.get(field_name)
        if isinstance(val, list) and len(val) == 0:
            issues.append(
                (
                    "HIGH",
                    f"结构化产物 {json_file} 的 {field_name} 为空数组 — 可能是 Worker 未产出有效内容",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# 主 handler（两阶段）
# ---------------------------------------------------------------------------


def _apply_issues(
    issues: list[tuple[str, str]],
    ctx: ExecutionContext,
    result: PhaseResult,
    tag: str,
) -> int:
    """将检查结果按严重度分级写入 result. 返回 CRITICAL 数量."""
    critical_count = 0
    for severity, message in issues:
        if severity == "CRITICAL":
            result.add_error(f"BLOCKED: {message}")
            critical_count += 1
        elif severity == "HIGH":
            result.add_warning(f"FlowIntegrity[{tag}]: {message}")
        else:
            result.add_event(EventType.INFO, f"FlowIntegrity[{tag}]: {message}")

    if critical_count:
        log.error(
            "FlowIntegrity[%s] BLOCKED: Phase %s 有 %d 个 CRITICAL 问题",
            tag,
            ctx.phase_id,
            critical_count,
        )
    elif issues:
        log.warning(
            "FlowIntegrity[%s]: Phase %s 有 %d 个问题（%d HIGH, %d MEDIUM）",
            tag,
            ctx.phase_id,
            len(issues),
            sum(1 for s, _ in issues if s == "HIGH"),
            sum(1 for s, _ in issues if s == "MEDIUM"),
        )
    return critical_count


def handle_flow_integrity_pre(ctx: ExecutionContext, result: PhaseResult) -> None:
    """流程完整性 PRE 检查（order=5）— 基础产物存在性.

    在所有 finalize handler 之前执行。
    检查报告/结构化 JSON/schema 非空。
    """
    phase_def = PHASE_DEFS.get(ctx.phase_id)
    if not phase_def:
        return

    pd = _phase_dir(ctx.output_dir, ctx.project_id, phase_def)

    issues: list[tuple[str, str]] = []
    issues.extend(_check_report_exists(pd, ctx.phase_id))
    issues.extend(_check_structured_json_nonempty(pd, ctx.phase_id))
    issues.extend(_check_schema_semantic_completeness(pd, ctx.phase_id))

    _apply_issues(issues, ctx, result, "pre")


def handle_flow_integrity_post(ctx: ExecutionContext, result: PhaseResult) -> None:
    """流程完整性 POST 检查（order=76）— judge/critique 闭环.

    在 auto_judge(order=75) 之后执行。
    此时 judge_result 应该已存在（AI 手动执行或 auto_judge 合成）。
    """
    phase_def = PHASE_DEFS.get(ctx.phase_id)
    if not phase_def:
        return

    pd = _phase_dir(ctx.output_dir, ctx.project_id, phase_def)

    issues: list[tuple[str, str]] = []
    issues.extend(_check_judge_result(pd, ctx.phase_id))
    issues.extend(_check_critique_closure(pd, ctx.phase_id))

    _apply_issues(issues, ctx, result, "post")


def register_flow_integrity_handler() -> None:
    """注册流程完整性检查 handler（两阶段）."""
    # PRE: order=5，最早执行，检查基础产物
    register_handler(
        "flow_integrity_pre",
        handle_flow_integrity_pre,
        stage="finalize",
        order=5,
        required=True,
    )
    # POST: order=76，在 auto_judge(75) 之后，检查 judge/critique 闭环
    register_handler(
        "flow_integrity_post",
        handle_flow_integrity_post,
        stage="finalize",
        order=76,
        depends_on=["auto_judge"],
        required=True,
    )
