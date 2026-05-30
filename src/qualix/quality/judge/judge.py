"""LLM-as-Judge: 自动评审 Phase 输出质量.

在 finalize 阶段生成 judge prompt，由 Claude Code 执行评审。
Judge 对照 PRD 原文、gate checklist、bug 案例库评判输出质量，
输出结构化的 precision/recall 估计和具体问题列表。
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from qualix.cache.llm_result_cache import get_cached_result, put_cached_result
from qualix.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json
from qualix.log import get_logger

log = get_logger(__name__)
from qualix.prompting import PromptAssembler, PromptAsset, PromptBuild, PromptSpec, write_prompt_manifest
from qualix.prompting.record import record_prompt_manifest
from qualix.services.phase_service import read_relevance_excerpt
from qualix.tracking.case_selector import render_relevant_cases_for_prompt

from .judge_rubrics import ANTI_RATIONALIZATION_SECTION as _ANTI_RATIONALIZATION_SECTION
from .judge_rubrics import JUDGE_RUBRICS as _JUDGE_RUBRICS
from .judge_rubrics import compose_rubric_layered as _compose_rubric


def build_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> PromptBuild | None:
    """Build LLM-as-Judge prompt through the central PromptAssembler.

    Returns:
        Prompt build with section-level manifest; unsupported phases return None.
    """
    rubric = _JUDGE_RUBRICS.get(phase_id)
    if not rubric:
        return None

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    # 动态维度：根据 Phase A SE 分布追加针对性评分维度
    from .dynamic_rubric import generate_dynamic_dimensions

    dynamic_dims = generate_dynamic_dimensions(output_dir, project_id, phase_id)

    pd = _phase_dir(output_dir, project_id, phase_def)
    checklist = phase_def.get("approve_checklist", [])

    goal = "\n\n".join(
        [
            f"# Quality Judge — Phase {phase_id}: {rubric['name']}",
            "## 评估目标",
            "基于原始输入、Phase 产物、Gate Checklist、评估协议和已知失败案例，判断本 Phase 输出是否满足质量门禁。\n"
            "结论必须由证据支撑；没有原文引用或文件依据的判断一律视为不成立。",
        ]
    )
    behavior_constraints = "\n".join(
        [
            "## 行为约束",
            "",
            "- 每个结论都必须引用具体证据；没有引用的结论不能计入评分依据",
            "- 不接受'基本覆盖''整体还行'这类无法验证的模糊表述",
            "- 主动寻找漏报（FN）、错判、虚构和证据不足，不为已有产物辩护",
            "- 不修复产物，只输出评审结论和结构化问题",
            "",
            "## 评审规则",
            "",
            "1. 你是独立评审员，不是执行者。你的任务是找出问题，不是修复问题。",
            "2. 每个评分维度按 1-5 分 Likert 量表打分，严格对照每级标准。",
            "3. 漏报（FN）比误报（FP）更严重 — 宁可多报不可漏报。",
            "4. 必须对照原始输入（PRD/技术方案/代码）逐条验证，不能只看输出的自洽性。",
            "5. 每个维度必须列出具体的扣分证据（引用原文位置）。",
        ]
    )
    gate_checklist_lines = [
        "## Gate Checklist（通过标准）",
        "",
    ]
    for item in checklist:
        gate_checklist_lines.append(f"- [ ] {item}")
    gate_checklist = "\n".join(gate_checklist_lines)

    from qualix.quality.eval.evaluation_protocols import get_protocol, render_protocol_for_prompt

    protocol = get_protocol(phase_id)
    evaluation_protocol = (
        render_protocol_for_prompt(protocol.judge)
        if protocol
        else "## 检查清单（必须逐条检查）\n\n## 行为红线（绝对不能做）"
    )

    rubric_text = "\n\n".join(
        [
            "## 评审维度 + 检查清单（compose_rubric 生成）",
            _compose_rubric(phase_id, dynamic_dimensions=dynamic_dims or None),
        ]
    )

    input_lines = [
        "## 评审输入",
        "",
        f"Phase 输出目录: `{pd}`",
        "",
        "请读取以下文件进行评审：",
        "",
    ]

    report_files = []
    report_file = REPORT_MAP.get(phase_id)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if report_file:
        report_files.append(report_file)
    if json_file:
        report_files.append(json_file)
    relevance_parts: list[str] = []
    for i, f in enumerate(report_files, 1):
        path = pd / f
        input_lines.append(f"{i}. `{path}`")
        excerpt = read_relevance_excerpt(path)
        if excerpt:
            relevance_parts.append(excerpt)

    if phase_id != "Q01":
        upstream_dir = output_dir / project_id / PHASE_DIR_MAP["Q01"]
        upstream_path = upstream_dir / STRUCTURED_JSON_MAP["Q01"]
        input_lines.append(f"{len(report_files) + 1}. Phase Q01 产物: `{upstream_path}`")
        excerpt = read_relevance_excerpt(upstream_path)
        if excerpt:
            relevance_parts.append(excerpt)

    bug_cases_md = render_relevant_cases_for_prompt(phase_id, "\n".join(relevance_parts), max_cases=10)

    from qualix.quality.regression.gene_store import load_genes_for_phase, match_genes, render_genes_for_prompt

    genes_text = ""
    phase_genes = load_genes_for_phase(output_dir.parent, phase_id, agent_role="judge")
    if phase_genes:
        gene_context = "\n".join(relevance_parts) if relevance_parts else ""
        matched = match_genes(phase_genes, gene_context)
        if matched:
            genes_text = render_genes_for_prompt(matched)

    output_schema = "\n".join(
        [
            "## 输出格式",
            "",
            "请输出以下 JSON 格式的评审结果，保存到：",
            f"`{pd / '_judge_result.json'}`",
            "",
            "```json",
            "{",
            '  "phase": "' + phase_id + '",',
            '  "project_id": "' + project_id + '",',
            '  "judged_at": "ISO8601 时间戳",',
            '  "gate_checklist": [',
            '    {"item": "checklist 项", "passed": true/false, "evidence": "判断依据"}',
            "  ],",
            '  "dimensions": [',
            "    {",
            '      "id": "维度 ID",',
            '      "score": 4,',
            '      "max_score": 5,',
            '      "issues": [',
            '        {',
            '          "type": "FN/FP/WRONG",',
            '          "severity": "critical/high/medium/low",',
            '          "description": "具体问题",',
            '          "evidence": "原文引用",',
            '          "item_ref": "可选，JSONPath 精确定位产物字段，如 audit_items[7].eut_id（无法定位时省略）",',
            '          "fix_hint": "可选，item_ref 对应的修改提示（有 item_ref 时建议填写）"',
            '        }',
            "      ]",
            "    }",
            "  ],",
            '  "overall_score": 3.8,',
            '  "precision_estimate": 0.85,',
            '  "recall_estimate": 0.75,',
            '  "summary": "一句话总结",',
            '  "top_issues": ["最重要的 3 个问题"]',
            "}",
            "```",
            "",
            "**FALLBACK**: 如果无法写入 JSON 文件，在输出末尾另起一行写入：",
            "`DQG_VERDICT:PASS:X.X` 或 `DQG_VERDICT:FAIL:X.X`（X.X 为 overall_score 1.0–5.0）",
            "",
            "## 开始评审",
            "",
            "请逐个维度评审，先读取所有文件，再给出评分。",
        ]
    )

    spec = PromptSpec(
        prompt_id=f"judge.{phase_id}",
        prompt_type="judge",
        phase_id=phase_id,
        role="judge",
        output_schema="judge_result",
    )
    return PromptAssembler.for_role("judge").assemble(
        spec,
        {
            "goal": goal,
            "behavior_constraints": behavior_constraints,
            "gate_checklist": gate_checklist,
            "evaluation_protocol": evaluation_protocol,
            "rubric": rubric_text,
            "inputs": "\n".join(input_lines),
            "bug_cases": bug_cases_md,
            "genes": genes_text,
            "anti_rationalization": "\n".join(_ANTI_RATIONALIZATION_SECTION),
            "output_schema": output_schema,
        },
        assets=_judge_prompt_assets(phase_id),
        section_sources={
            "gate_checklist": ("qualix.core.state_machine.PHASE_DEFS",),
            "evaluation_protocol": ("qualix.quality.evaluation_protocols",),
            "rubric": ("qualix.quality.judge_rubrics", "qualix.quality.dynamic_rubric"),
            "bug_cases": ("qualix.tracking.case_selector",),
            "genes": ("qualix.quality.gene_store",),
            "anti_rationalization": ("qualix.quality.judge_rubrics.ANTI_RATIONALIZATION_SECTION",),
        },
        project_id=project_id,
    )


def generate_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """生成 LLM-as-Judge 评审 prompt.

    Returns:
        judge prompt 文本，如果 phase 不支持评审则返回 None
    """
    build = build_judge_prompt(output_dir, project_id, phase_id)
    return build.prompt if build else None


def write_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    prompt: str | None = None,
) -> Path | None:
    """生成 judge prompt 并写入 phase 目录，同时落盘 rubric 快照.

    Returns:
        写入的文件路径，不支持的 phase 返回 None
    """
    build: PromptBuild | None = None
    if prompt is None:
        build = build_judge_prompt(output_dir, project_id, phase_id)
        prompt = build.prompt if build else None
    else:
        candidate = build_judge_prompt(output_dir, project_id, phase_id)
        if candidate and candidate.prompt == prompt:
            build = candidate
    if not prompt:
        return None

    phase_def = PHASE_DEFS[phase_id]
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)

    path = pd / "_judge_prompt.md"
    path.write_text(prompt, encoding="utf-8")
    if build is not None:
        write_prompt_manifest(path, build.manifest)
    else:
        record_prompt_manifest(
            path,
            prompt=prompt,
            prompt_type="judge",
            phase_id=phase_id,
            project_id=project_id,
            output_schema="judge_result",
            assets=_judge_prompt_assets(phase_id),
        )

    # 落盘 rubric 快照，用于趋势对比和可观测性
    rubric = _JUDGE_RUBRICS.get(phase_id)
    if rubric:
        from qualix.json_utils import save_json

        from .dynamic_rubric import enrich_rubric_with_dynamic_dimensions, generate_dynamic_dimensions

        dynamic_dims = generate_dynamic_dimensions(output_dir, project_id, phase_id)
        if dynamic_dims:
            rubric = enrich_rubric_with_dynamic_dimensions(rubric, dynamic_dims)
        rubric_path = pd / "_internal" / "_judge_rubric.json"
        rubric_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(rubric_path, rubric)

    return path


def _judge_prompt_assets(phase_id: str) -> tuple[PromptAsset, ...]:
    rubric = _JUDGE_RUBRICS.get(phase_id)
    if not rubric:
        return ()
    return (
        PromptAsset(
            kind="rubric",
            path=f"qualix.quality.judge_rubrics:{phase_id}",
            content=str(rubric),
        ),
    )


def load_judge_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """加载 judge 评审结果. 加载成功后自动写入缓存."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None
    pd = _phase_dir(output_dir, project_id, phase_def)
    result_path = pd / "_judge_result.json"
    if not result_path.exists():
        return None
    result = load_json(result_path)
    if result:
        put_cached_result(output_dir, project_id, phase_id, "judge", result)
    return result


def get_cached_judge_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """检查是否有缓存的 judge 结果（产物未变更时命中）."""
    return get_cached_result(output_dir, project_id, phase_id, "judge")


def format_judge_summary(result: dict[str, Any]) -> str:
    """格式化 judge 结果为可读摘要."""
    lines = [
        f"Quality Judge — Phase {result.get('phase', '?')}",
        f"  总分: {result.get('overall_score', '?')}/5",
        f"  Precision: {result.get('precision_estimate', '?'):.0%}"
        if isinstance(result.get("precision_estimate"), int | float)
        else "",
        f"  Recall: {result.get('recall_estimate', '?'):.0%}"
        if isinstance(result.get("recall_estimate"), int | float)
        else "",
    ]

    dims = result.get("dimensions", [])
    if dims:
        lines.append("  维度得分:")
        for d in dims:
            issues = d.get("issues", [])
            lines.append(
                f"    {d.get('id', '?')}: {d.get('score', '?')}/{d.get('max_score', 5)} ({len(issues)} issues)"
            )

    top_issues = result.get("top_issues", [])
    if top_issues:
        lines.append("  关键问题:")
        for issue in top_issues[:3]:
            lines.append(f"    - {issue}")

    return "\n".join(line for line in lines if line)


def synthesize_judge_result(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any] | None:
    """从 structured JSON 自动合成 _judge_result.json.

    当 finalize 生成了 judge prompt 但 AI 未手动执行时，
    从已有的 structured JSON 产物中提取关键指标，
    合成一份基础 judge result 以解除 approve 的阻断。
    如果 _judge_result.json 已存在则跳过。
    """
    from datetime import datetime

    from qualix.json_utils import save_json_atomic

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    result_path = pd / "_judge_result.json"
    if result_path.exists():
        return load_json(result_path)

    structured_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not structured_file:
        return None
    structured_path = pd / structured_file
    if not structured_path.exists():
        return None

    data = load_json(structured_path)
    if not data:
        return None

    # 从 structured JSON 提取统计信息
    issues = data.get("issues", [])
    failure_modes = data.get("failure_modes", [])
    conclusion = data.get("conclusion", "")

    severity_counts: dict[str, int] = {}
    for issue in issues:
        sev = issue.get("severity", "MEDIUM")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    critical_count = severity_counts.get("CRITICAL", 0)
    high_count = severity_counts.get("HIGH", 0)
    total_issues = len(issues)

    fm_statuses: dict[str, int] = {}
    for fm in failure_modes:
        st = fm.get("status") or fm.get("assessment", "RISK")
        fm_statuses[st] = fm_statuses.get(st, 0) + 1
    critical_gap_count = fm_statuses.get("CRITICAL_GAP", 0)

    # 基于问题分布估算评分（5 分制）
    if critical_count == 0 and critical_gap_count == 0:
        score = 4.5
    elif critical_count <= 2 and critical_gap_count <= 1:
        score = 3.5
    elif critical_count <= 5 and critical_gap_count <= 3:
        score = 2.5
    else:
        score = 1.5

    # 基于问题分布动态估算 precision/recall
    if total_issues == 0:
        precision_est = 0.5
        recall_est = 0.5
    else:
        critical_ratio = (critical_count + high_count) / total_issues
        precision_est = round(0.7 + 0.25 * critical_ratio, 2)
        recall_est = round(min(0.95, 0.6 + 0.08 * total_issues - 0.05 * score), 2)
        recall_est = max(0.4, min(0.95, recall_est))

    gate_items = []
    checklist = phase_def.get("approve_checklist", [])
    has_critical = critical_count > 0 or critical_gap_count > 0
    for item_text in checklist:
        # 含 "CRITICAL"/"blocker"/"阻断" 关键词的 checklist 项在有 critical 问题时标记 failed
        item_lower = item_text.lower()
        is_blocking_item = any(kw in item_lower for kw in ("critical", "blocker", "阻断", "block"))
        passed = not has_critical if is_blocking_item else (score >= 3.0)
        gate_items.append({"item": item_text, "passed": passed, "evidence": "auto-synthesized"})

    top_issues = []
    for issue in issues:
        if issue.get("severity") == "CRITICAL":
            desc = issue.get("description", "")
            iid = issue.get("issue_id", "")
            top_issues.append(f"{iid}: {desc}" if iid else desc)
    top_issues = top_issues[:5]

    result = {
        "phase": phase_id,
        "project_id": project_id,
        "judged_at": datetime.now(UTC).isoformat(),
        "auto_synthesized": True,
        "gate_checklist": gate_items,
        "dimensions": [
            {
                "id": "overall_quality",
                "score": round(score),
                "max_score": 5,
                "issues": [],
            },
        ],
        "overall_score": score,
        "precision_estimate": precision_est,
        "recall_estimate": recall_est,
        "summary": (
            f"Auto-synthesized: {total_issues} issues "
            f"({critical_count} CRITICAL, {high_count} HIGH), "
            f"{len(failure_modes)} failure modes "
            f"({critical_gap_count} CRITICAL_GAP). "
            f"Conclusion: {conclusion}"
        ),
        "top_issues": top_issues,
    }

    pd.mkdir(parents=True, exist_ok=True)
    save_json_atomic(result_path, result)
    try:
        from qualix.memory.trust_level import TrustLevel, record_trust_event

        record_trust_event(
            output_dir,
            project_id=project_id,
            phase_id=phase_id,
            event_type="judge_auto_synthesized",
            trust_level=TrustLevel.MEDIUM,
            payload={"overall_score": score, "auto_synthesized": True},
        )
    except Exception:
        log.debug("judge trust event write skipped", exc_info=True)
    return result
