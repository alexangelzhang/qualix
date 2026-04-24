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

from dqg.cache.llm_result_cache import get_cached_result, put_cached_result
from dqg.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.quality.judge_rubrics import ANTI_RATIONALIZATION_SECTION as _ANTI_RATIONALIZATION_SECTION
from dqg.quality.judge_rubrics import JUDGE_RUBRICS as _JUDGE_RUBRICS
from dqg.services.phase_service import read_relevance_excerpt
from dqg.tracking.case_selector import render_relevant_cases_for_prompt


def generate_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """生成 LLM-as-Judge 评审 prompt.

    Returns:
        judge prompt 文本，如果 phase 不支持评审则返回 None
    """
    rubric = _JUDGE_RUBRICS.get(phase_id)
    if not rubric:
        return None

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    # 动态维度：根据 Phase A SE 分布追加针对性评分维度
    from dqg.quality.dynamic_rubric import enrich_rubric_with_dynamic_dimensions, generate_dynamic_dimensions

    dynamic_dims = generate_dynamic_dimensions(output_dir, project_id, phase_id)
    if dynamic_dims:
        rubric = enrich_rubric_with_dynamic_dimensions(rubric, dynamic_dims)

    pd = _phase_dir(output_dir, project_id, phase_def)
    checklist = phase_def.get("approve_checklist", [])

    # 构建 prompt
    lines = [
        f"# Quality Judge — Phase {phase_id}: {rubric['name']}",
        "",
        "## 你的身份",
        "",
        "你是一位有 10 年经验的质量负责人。你见过太多'测试通过但线上出事'、'评审通过但需求遗漏'的案例。",
        "你不相信'看起来没问题'，只相信证据。你的口头禅是：'证据在哪？'",
        "",
        "你的行为准则：",
        "- 你对每个结论都要求看到原文引用，没有引用的结论你不认可",
        "- 你对'基本覆盖''整体还行'这类模糊表述零容忍",
        "- 你知道 LLM 倾向于给高分和正面评价，所以你会刻意寻找问题",
        "- 你宁可被认为苛刻，也不愿放过一个真问题",
        "",
        "## 评审规则",
        "",
        "1. 你是独立评审员，不是执行者。你的任务是找出问题，不是修复问题。",
        "2. 每个评分维度按 1-5 分 Likert 量表打分，严格对照每级标准。",
        "3. 漏报（FN）比误报（FP）更严重 — 宁可多报不可漏报。",
        "4. 必须对照原始输入（PRD/技术方案/代码）逐条验证，不能只看输出的自洽性。",
        "5. 每个维度必须列出具体的扣分证据（引用原文位置）。",
        "",
        "## Gate Checklist（通过标准）",
        "",
    ]
    for item in checklist:
        lines.append(f"- [ ] {item}")

    lines.extend(
        [
            "",
            "## 评审维度（1-5 Likert 量表）",
            "",
        ]
    )
    for dim in rubric["dimensions"]:
        lines.append(f"### {dim['id']}: {dim['name']}（权重 {dim['weight']:.0%}）")
        lines.append(f"- 定义: {dim['description']}")
        lines.append("")
        lines.append("| 分数 | 标准 |")
        lines.append("|------|------|")
        for score in (5, 4, 3, 2, 1):
            criteria = dim.get("rubric", {}).get(score, "")
            lines.append(f"| {score} | {criteria} |")
        lines.append("")

    lines.extend(
        [
            "",
            "## 评审输入",
            "",
            f"Phase 输出目录: `{pd}`",
            "",
            "请读取以下文件进行评审：",
            "",
        ]
    )

    # 列出需要读取的文件
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
        lines.append(f"{i}. `{path}`")
        excerpt = read_relevance_excerpt(path)
        if excerpt:
            relevance_parts.append(excerpt)

    # 上游产物
    if phase_id != "Q01":
        upstream_dir = output_dir / project_id / PHASE_DIR_MAP["Q01"]
        upstream_path = upstream_dir / STRUCTURED_JSON_MAP["Q01"]
        lines.append(f"{len(report_files) + 1}. Phase Q01 产物: `{upstream_path}`")
        excerpt = read_relevance_excerpt(upstream_path)
        if excerpt:
            relevance_parts.append(excerpt)

    bug_cases_md = render_relevant_cases_for_prompt(phase_id, "\n".join(relevance_parts), max_cases=10)
    if bug_cases_md:
        lines.extend(["", bug_cases_md, ""])

    lines.extend(_ANTI_RATIONALIZATION_SECTION)

    lines.extend(
        [
            "",
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
            '        {"type": "FN/FP/WRONG", "description": "具体问题", "evidence": "原文引用"}',
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
            "## 开始评审",
            "",
            "请逐个维度评审，先读取所有文件，再给出评分。",
        ]
    )

    return "\n".join(lines)


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
    if prompt is None:
        prompt = generate_judge_prompt(output_dir, project_id, phase_id)
    if not prompt:
        return None

    phase_def = PHASE_DEFS[phase_id]
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)

    path = pd / "_judge_prompt.md"
    path.write_text(prompt, encoding="utf-8")

    # 落盘 rubric 快照，用于趋势对比和可观测性
    rubric = _JUDGE_RUBRICS.get(phase_id)
    if rubric:
        from dqg.json_utils import save_json
        from dqg.quality.dynamic_rubric import enrich_rubric_with_dynamic_dimensions, generate_dynamic_dimensions

        dynamic_dims = generate_dynamic_dimensions(output_dir, project_id, phase_id)
        if dynamic_dims:
            rubric = enrich_rubric_with_dynamic_dimensions(rubric, dynamic_dims)
        rubric_path = pd / "_internal" / "_judge_rubric.json"
        rubric_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(rubric_path, rubric)

    return path


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

    from dqg.json_utils import save_json

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
    save_json(result_path, result)
    return result
