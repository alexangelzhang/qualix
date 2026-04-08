"""LLM-as-Judge: 自动评审 Phase 输出质量.

在 finalize 阶段生成 judge prompt，由 Claude Code 执行评审。
Judge 对照 PRD 原文、gate checklist、bug 案例库评判输出质量，
输出结构化的 precision/recall 估计和具体问题列表。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.constants import PHASE_DIR_MAP, REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.cache.llm_result_cache import get_cached_result, put_cached_result
from dqg.services.phase_service import read_relevance_excerpt
from dqg.tracking.case_selector import render_relevant_cases_for_prompt


# Phase → 评审维度定义（1-5 Likert 量表，每级有明确标准）
_JUDGE_RUBRICS: dict[str, dict[str, Any]] = {
    "A": {
        "name": "需求结构化",
        "dimensions": [
            {
                "id": "faithfulness",
                "name": "忠实度",
                "description": "输出的 REQ/SE/GAP 是否忠实于 PRD 原文，不编造",
                "weight": 0.25,
                "rubric": {
                    5: "所有 REQ/SE/GAP 都能在 PRD 原文中找到明确依据",
                    4: "90%+ 有依据，少量合理推断已标注置信度",
                    3: "70-90% 有依据，部分推断未标注",
                    2: "50-70% 有依据，存在明显编造内容",
                    1: "大量内容无法在 PRD 中找到依据",
                },
            },
            {
                "id": "completeness",
                "name": "完备性",
                "description": "PRD 中的所有需求点是否都被提取为 REQ/BR",
                "weight": 0.3,
                "rubric": {
                    5: "PRD 所有功能点、业务规则、约束条件均已提取，无遗漏",
                    4: "核心功能点全部覆盖，仅遗漏 1-2 个边缘场景",
                    3: "主要功能点已覆盖，遗漏 3-5 个需求点",
                    2: "明显遗漏多个功能点或整个业务模块",
                    1: "大面积遗漏，仅提取了部分表面需求",
                },
            },
            {
                "id": "se_explicitness",
                "name": "SE 显式率",
                "description": "关键业务语义是否都被显式化为可验证的 SE",
                "weight": 0.25,
                "rubric": {
                    5: "每个 REQ/BR 都有对应的可验证 SE，隐式语义全部显式化",
                    4: "90%+ REQ 有对应 SE，少量隐式语义未提取",
                    3: "70-90% 有 SE，并发/幂等/边界等隐式语义部分遗漏",
                    2: "SE 覆盖不足 70%，大量业务语义隐含在 REQ 描述中",
                    1: "几乎没有 SE，或 SE 与 REQ 重复无新增信息",
                },
            },
            {
                "id": "gap_detection",
                "name": "GAP 发现率",
                "description": "PRD 中的模糊点、缺失定义是否被识别为 GAP",
                "weight": 0.2,
                "rubric": {
                    5: "所有模糊描述、缺失定义、歧义点均已识别为 GAP/OPEN",
                    4: "主要模糊点已识别，仅遗漏 1-2 个非关键 GAP",
                    3: "识别了部分 GAP，但遗漏了并发/幂等/安全等关键缺口",
                    2: "GAP 识别明显不足，多个关键缺口未发现",
                    1: "几乎未识别 GAP，或 GAP 为 0 但 PRD 明显有模糊点",
                },
            },
        ],
    },
    "A.5": {
        "name": "技术方案覆盖度审计",
        "dimensions": [
            {
                "id": "coverage_accuracy",
                "name": "覆盖判定准确率",
                "description": "COVERED/PARTIAL/MISSING/IMPLICIT 的判定是否正确",
                "weight": 0.4,
                "rubric": {
                    5: "所有覆盖状态判定正确，COVERED 确实有完整设计，MISSING 确实缺失",
                    4: "90%+ 判定正确，个别 PARTIAL/COVERED 边界有争议",
                    3: "70-90% 正确，存在将仅提到接口名就判为 COVERED 的情况",
                    2: "多个判定错误，正向流程有但异常分支缺失仍判为 COVERED",
                    1: "大面积判定错误，覆盖率虚高",
                },
            },
            {
                "id": "missing_detection",
                "name": "遗漏检出率",
                "description": "技术方案中真正缺失的需求点是否被标记为 MISSING",
                "weight": 0.3,
                "rubric": {
                    5: "所有缺失的需求点都被准确标记为 MISSING",
                    4: "核心缺失全部检出，仅遗漏 1-2 个边缘 MISSING",
                    3: "检出了部分 MISSING，但遗漏了关键异常处理/并发场景的缺失",
                    2: "MISSING 检出不足，多个关键缺失未发现",
                    1: "几乎未检出 MISSING，或全部标为 COVERED",
                },
            },
            {
                "id": "reverse_audit",
                "name": "反向审计完整性",
                "description": "技术方案中的新增设计是否被标记为 NEW_DESIGN/NOT_IN_SCOPE",
                "weight": 0.3,
                "rubric": {
                    5: "技术方案中所有超出 PRD 范围的设计都被识别并标记",
                    4: "主要新增设计已识别，仅遗漏 1-2 个",
                    3: "部分新增设计被识别，但遗漏了重要的范围外设计",
                    2: "反向审计明显不足",
                    1: "未做反向审计",
                },
            },
        ],
    },
    "A.6": {
        "name": "技术方案质量评审",
        "dimensions": [
            {
                "id": "issue_validity",
                "name": "问题有效率",
                "description": "发现的质量问题是否是真问题（非噪音）",
                "weight": 0.3,
                "rubric": {
                    5: "所有 issue 都是真问题，有具体代码/设计证据支撑",
                    4: "90%+ 是真问题，个别 issue 证据稍弱",
                    3: "70-90% 是真问题，存在噪音 issue",
                    2: "噪音 issue 占比超 30%",
                    1: "大量噪音，issue 缺乏证据",
                },
            },
            {
                "id": "failure_mode_coverage",
                "name": "Failure Mode 覆盖率",
                "description": "关键业务路径是否都做了故障场景分析",
                "weight": 0.35,
                "rubric": {
                    5: "所有写操作/RPC 调用/状态迁移都有 Failure Mode 分析",
                    4: "核心路径全覆盖，仅遗漏 1-2 个非关键路径",
                    3: "主要路径已覆盖，但跨服务调用的部分失败场景遗漏",
                    2: "Failure Mode 分析不完整，多个关键路径缺失",
                    1: "几乎未做 Failure Mode 分析",
                },
            },
            {
                "id": "exception_coverage",
                "name": "异常矩阵覆盖率",
                "description": "异常分类目录中的类型是否都被检查",
                "weight": 0.35,
                "rubric": {
                    5: "9 类异常分支全部检查，每类有具体的技术方案对应分析",
                    4: "7-8 类已检查，仅遗漏 1-2 个低频异常类型",
                    3: "5-6 类已检查，遗漏了 E-CONFLICT/E-TIMEOUT 等关键类型",
                    2: "检查不足 5 类",
                    1: "几乎未对照异常矩阵检查",
                },
            },
        ],
    },
    "C": {
        "name": "单测覆盖审计",
        "dimensions": [
            {
                "id": "audit_accuracy",
                "name": "审计判定准确率",
                "description": "COVERED/MISSING/WRONG_TARGET 的判定是否正确",
                "weight": 0.35,
                "rubric": {
                    5: "所有审计状态判定正确，COVERED 确实有强断言，WRONG_TARGET 确实是弱断言",
                    4: "90%+ 判定正确，个别边界 case 有争议",
                    3: "70-90% 正确，存在将 assertNotNull 判为 COVERED 的情况",
                    2: "多个判定错误，弱断言未被识别",
                    1: "大面积判定错误",
                },
            },
            {
                "id": "wrong_target_detection",
                "name": "WRONG_TARGET 检出率",
                "description": "弱断言的测试是否被正确标记为 WRONG_TARGET",
                "weight": 0.3,
                "rubric": {
                    5: "所有弱断言（assertNotNull/assertTrue(true)等）都被标记为 WRONG_TARGET",
                    4: "90%+ 弱断言被检出",
                    3: "主要弱断言被检出，但遗漏了只验证返回值不验证业务语义的情况",
                    2: "WRONG_TARGET 检出不足，多个弱断言被判为 COVERED",
                    1: "几乎未检出 WRONG_TARGET",
                },
            },
            {
                "id": "exception_branch",
                "name": "异常分支覆盖",
                "description": "T1 核心异常分支是否都有对应测试",
                "weight": 0.35,
                "rubric": {
                    5: "所有 T1 异常分支都有测试，断言包含异常类型+状态不变+无脏数据",
                    4: "90%+ T1 异常有测试，个别断言不够完整",
                    3: "主要异常有测试，但缺少并发冲突/事务回滚等场景",
                    2: "异常分支测试明显不足",
                    1: "几乎无异常分支测试",
                },
            },
        ],
    },
}


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

    pd = _phase_dir(output_dir, project_id, phase_def)
    checklist = phase_def.get("approve_checklist", [])

    # 构建 prompt
    lines = [
        f"# Quality Judge — Phase {phase_id}: {rubric['name']}",
        "",
        "你是一个独立的质量评审员（Judge），负责评估 Phase 输出的准确性和完备性。",
        "你的评审必须基于证据，每个判断都要引用具体的原文或代码位置。",
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

    lines.extend([
        "",
        "## 评审维度（1-5 Likert 量表）",
        "",
    ])
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

    lines.extend([
        "",
        "## 评审输入",
        "",
        f"Phase 输出目录: `{pd}`",
        "",
        "请读取以下文件进行评审：",
        "",
    ])

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
    if phase_id != "A":
        upstream_dir = output_dir / project_id / PHASE_DIR_MAP["A"]
        upstream_path = upstream_dir / STRUCTURED_JSON_MAP["A"]
        lines.append(f"{len(report_files) + 1}. Phase A 产物: `{upstream_path}`")
        excerpt = read_relevance_excerpt(upstream_path)
        if excerpt:
            relevance_parts.append(excerpt)

    bug_cases_md = render_relevant_cases_for_prompt(phase_id, "\n".join(relevance_parts), max_cases=10)
    if bug_cases_md:
        lines.extend(["", bug_cases_md, ""])

    lines.extend([
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
    ])

    return "\n".join(lines)


def write_judge_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    prompt: str | None = None,
) -> Path | None:
    """生成 judge prompt 并写入 phase 目录.

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
        f"  Precision: {result.get('precision_estimate', '?'):.0%}" if isinstance(result.get('precision_estimate'), (int, float)) else "",
        f"  Recall: {result.get('recall_estimate', '?'):.0%}" if isinstance(result.get('recall_estimate'), (int, float)) else "",
    ]

    dims = result.get("dimensions", [])
    if dims:
        lines.append("  维度得分:")
        for d in dims:
            issues = d.get("issues", [])
            lines.append(f"    {d.get('id', '?')}: {d.get('score', '?')}/{d.get('max_score', 5)} ({len(issues)} issues)")

    top_issues = result.get("top_issues", [])
    if top_issues:
        lines.append("  关键问题:")
        for issue in top_issues[:3]:
            lines.append(f"    - {issue}")

    return "\n".join(line for line in lines if line)
