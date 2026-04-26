"""Self-Critique + RLAIF 融合闭环.

三步流程：
1. Self-Critique: Phase 输出后，对照 gate checklist + bug cases 自我审视，生成修正建议
2. Preference Comparison: 比较 v1（原始）vs v2（修正后），生成偏好标签
3. Feedback Loop: 偏好数据积累，有效 critique 沉淀为 bug case

所有步骤通过生成 prompt 文件实现，由 AI IDE 执行。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.prompting import PromptAssembler, PromptBuild, PromptSpec, write_prompt_manifest
from dqg.prompting.record import record_prompt_manifest
from dqg.services.phase_service import read_relevance_excerpt
from dqg.tracking.case_selector import render_relevant_cases_for_prompt

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Step 1: Self-Critique Prompt
# ---------------------------------------------------------------------------


def build_critique_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> PromptBuild | None:
    """Build Self-Critique prompt through the central PromptAssembler.

    让执行 Phase 的同一个 LLM 对照 gate checklist + bug cases 审视自己的输出，
    发现问题并生成修正版本。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    checklist = phase_def.get("approve_checklist", [])

    # 报告文件映射
    report_file = REPORT_MAP.get(phase_id)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not report_file or not json_file:
        return None

    goal = "\n\n".join(
        [
            f"# Self-Critique — Phase {phase_id}: {phase_def['name']}",
            "## 批评目标",
            "基于原始输入、Phase 产物、Gate Checklist、评估协议和已知失败案例，找出当前输出遗漏、错判、虚构或证据不足的问题。\n"
            "目标是生成可执行修正建议，而不是解释当前输出为什么合理。",
        ]
    )
    behavior_constraints = "\n".join(
        [
            "## 行为约束",
            "",
            "- 每个发现必须引用具体证据；没有证据的猜测不能作为问题输出",
            "- 重点检查隐式需求、跨模块依赖、异常分支和边界条件",
            "- 不重复 Judge 已经发现的问题，优先挖掘新增缺口",
            "- 不编造原始输入没有明示或暗示的需求",
            "",
            "## 批评规则",
            "",
            "1. 假设你的输出有遗漏和错误，你的任务是找出它们。",
            "2. 对照原始输入（PRD/技术方案/代码）逐条验证每个结论。",
            "3. 漏报比误报更严重 — 重点找遗漏的需求点、未识别的风险、未覆盖的异常。",
            "4. 不要为自己的输出辩护，不要解释为什么某个判断是合理的。",
            "5. 每个发现必须引用具体的原文位置作为证据。",
        ]
    )
    gate_checklist_lines = [
        "## Gate Checklist（逐项自检）",
        "",
    ]
    for item in checklist:
        gate_checklist_lines.append(f"- [ ] {item}")

    from dqg.quality.evaluation_protocols import get_protocol, render_protocol_for_prompt

    protocol = get_protocol(phase_id)
    evaluation_protocol = (
        render_protocol_for_prompt(protocol.critique)
        if protocol
        else "## 检查清单（必须逐条检查）\n\n## 行为红线（绝对不能做）"
    )

    # 已知判错模式
    relevance_text_parts: list[str] = []
    for filename in (report_file, json_file):
        path = pd / filename
        if path.exists():
            relevance_text_parts.append(read_relevance_excerpt(path))

    bug_cases_md = render_relevant_cases_for_prompt(phase_id, "\n".join(relevance_text_parts), max_cases=8)
    bug_cases = "\n\n".join(["## 已知判错模式（你最容易犯的错误）", bug_cases_md]) if bug_cases_md else ""
    inputs = "\n".join(
        [
            "## 批评输入",
            "",
            f"Phase 输出目录: `{pd}`",
            f"- 报告: `{pd / report_file}`",
            f"- JSON: `{pd / json_file}`",
        ]
    )
    critique_steps = "\n".join(
        [
            "## 批评步骤",
            "",
            "1. 重新读取原始输入（PRD/技术方案/代码）",
            f"2. 读取你的输出: `{pd / report_file}` 和 `{pd / json_file}`",
            "3. 逐条对照，找出以下问题：",
            "   - 遗漏：原始输入中有但输出中没有的内容",
            "   - 错判：输出中的判断与原始输入不一致",
            "   - 虚构：输出中有但原始输入中找不到依据的内容",
            "   - 模糊：输出中的结论缺少具体证据",
        ]
    )
    output_schema = "\n".join(
        [
            "## 输出格式",
            "",
            f"将批评结果保存到: `{pd / '_critique.json'}`",
            "",
            "```json",
            "{",
            f'  "phase": "{phase_id}",',
            f'  "project_id": "{project_id}",',
            '  "critiqued_at": "ISO8601",',
            '  "issues_found": [',
            "    {",
            '      "type": "FN/FP/WRONG/VAGUE",',
            '      "severity": "critical/high/medium/low",',
            '      "description": "具体问题描述",',
            '      "evidence": "原始输入中的原文引用",',
            '      "suggestion": "修正建议"',
            "    }",
            "  ],",
            '  "revision_needed": true,',
            '  "summary": "一句话总结发现的问题"',
            "}",
            "```",
        ]
    )
    revision_instructions = "\n".join(
        [
            "## 修正",
            "",
            "如果发现了需要修正的问题（`revision_needed: true`），请：",
            "1. 基于批评结果修正输出，生成 v2 版本",
            f"2. 修正后的报告保存为: `{pd / (report_file.replace('.md', '_v2.md'))}`",
            f"3. 修正后的 JSON 保存为: `{pd / (json_file.replace('.json', '_v2.json'))}`",
            "4. 只修正有问题的部分，不要重写整个输出",
        ]
    )

    spec = PromptSpec(
        prompt_id=f"critique.{phase_id}",
        prompt_type="critique",
        phase_id=phase_id,
        role="critique",
        output_schema="critique_result",
    )
    return PromptAssembler.for_role("critique").assemble(
        spec,
        {
            "goal": goal,
            "behavior_constraints": behavior_constraints,
            "gate_checklist": "\n".join(gate_checklist_lines),
            "evaluation_protocol": evaluation_protocol,
            "inputs": inputs,
            "bug_cases": bug_cases,
            "critique_steps": critique_steps,
            "output_schema": output_schema,
            "revision_instructions": revision_instructions,
        },
        section_sources={
            "gate_checklist": ("dqg.core.state_machine.PHASE_DEFS",),
            "evaluation_protocol": ("dqg.quality.evaluation_protocols",),
            "bug_cases": ("dqg.tracking.case_selector",),
        },
        project_id=project_id,
    )


def generate_critique_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """生成 Self-Critique prompt."""
    build = build_critique_prompt(output_dir, project_id, phase_id)
    return build.prompt if build else None


# ---------------------------------------------------------------------------
# Step 2: Preference Comparison Prompt
# ---------------------------------------------------------------------------


def build_preference_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> PromptBuild | None:
    """Build RLAIF Preference Comparison prompt through PromptAssembler.

    比较 v1（原始输出）和 v2（critique 修正后），判定哪个更好。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)
    checklist = phase_def.get("approve_checklist", [])

    report_file = REPORT_MAP.get(phase_id)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not report_file or not json_file:
        return None

    v2_report = report_file.replace(".md", "_v2.md")
    v2_json = json_file.replace(".json", "_v2.json")

    goal = "\n\n".join(
        [
            f"# Preference Comparison — Phase {phase_id}: {phase_def['name']}",
            "比较同一个 Phase 的两个输出版本，基于原始输入和 critique 记录判定哪个版本更好。",
        ]
    )
    behavior_constraints = "\n".join(
        [
            "## 评审规则",
            "",
            "1. 必须保持中立，不能偏向任何一个版本。",
            "2. 对照原始输入（PRD/技术方案/代码）评判，不是比较两个版本的自洽性。",
            "3. 完备性（不遗漏）比精确性（不误报）更重要。",
            "4. 如果两个版本质量相当，判定为 tie。",
        ]
    )
    gate_checklist_lines = [
        "## 通过标准",
        "",
    ]
    for item in checklist:
        gate_checklist_lines.append(f"- {item}")

    inputs = "\n".join(
        [
            "## 比较输入",
            "",
            "### Version 1（原始输出）",
            f"- 报告: `{pd / report_file}`",
            f"- 结构化: `{pd / json_file}`",
            "",
            "### Version 2（critique 修正后）",
            f"- 报告: `{pd / v2_report}`",
            f"- 结构化: `{pd / v2_json}`",
            "",
            "### Critique 记录",
            f"- `{pd / '_critique.json'}`",
        ]
    )
    comparison_steps = "\n".join(
        [
            "## 评审步骤",
            "",
            "1. 读取原始输入（PRD/技术方案/代码）",
            "2. 读取 v1 和 v2 的报告和结构化 JSON",
            "3. 读取 critique 记录，了解 v2 做了哪些修正",
            "4. 逐维度比较：",
            "   - 完备性：哪个版本覆盖了更多的需求点/风险/异常？",
            "   - 准确性：哪个版本的判断更准确？",
            "   - 证据性：哪个版本的结论有更充分的原文支撑？",
            "5. 给出总体偏好判定",
        ]
    )
    output_schema = "\n".join(
        [
            "## 输出格式",
            "",
            f"保存到: `{pd / '_preference.json'}`",
            "",
            "```json",
            "{",
            f'  "phase": "{phase_id}",',
            f'  "project_id": "{project_id}",',
            '  "compared_at": "ISO8601",',
            '  "preferred": "v1/v2/tie",',
            '  "confidence": "high/medium/low",',
            '  "dimensions": {',
            '    "completeness": {"preferred": "v1/v2/tie", "reason": "..."},',
            '    "accuracy": {"preferred": "v1/v2/tie", "reason": "..."},',
            '    "evidence": {"preferred": "v1/v2/tie", "reason": "..."}',
            "  },",
            '  "critique_effectiveness": [',
            "    {",
            '      "critique_issue": "critique 发现的问题描述",',
            '      "was_valid": true,',
            '      "impact": "high/medium/low/none",',
            '      "should_persist": true',
            "    }",
            "  ],",
            '  "summary": "一句话总结偏好判定理由"',
            "}",
            "```",
        ]
    )

    spec = PromptSpec(
        prompt_id=f"preference.{phase_id}",
        prompt_type="preference",
        phase_id=phase_id,
        role="preference",
        output_schema="preference_result",
    )
    return PromptAssembler.for_role("preference").assemble(
        spec,
        {
            "goal": goal,
            "behavior_constraints": behavior_constraints,
            "gate_checklist": "\n".join(gate_checklist_lines),
            "inputs": inputs,
            "comparison_steps": comparison_steps,
            "output_schema": output_schema,
        },
        section_sources={
            "gate_checklist": ("dqg.core.state_machine.PHASE_DEFS",),
            "inputs": ("dqg.constants.REPORT_MAP", "dqg.constants.STRUCTURED_JSON_MAP"),
        },
        project_id=project_id,
    )


def generate_preference_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """生成 RLAIF Preference Comparison prompt."""
    build = build_preference_prompt(output_dir, project_id, phase_id)
    return build.prompt if build else None


# ---------------------------------------------------------------------------
# Backward-compat re-export: feedback functions moved to critique_feedback.py
# ---------------------------------------------------------------------------
from dqg.quality.critique_feedback import (  # noqa: F401, E402
    get_cached_critique_result,
    get_cached_preference_result,
    load_critique_result,
    persist_preference,
)


def write_critique_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    prompt: str | None = None,
) -> Path | None:
    """生成 critique prompt 并写入 phase 目录."""
    build: PromptBuild | None = None
    if prompt is None:
        build = build_critique_prompt(output_dir, project_id, phase_id)
        prompt = build.prompt if build else None
    else:
        candidate = build_critique_prompt(output_dir, project_id, phase_id)
        if candidate and candidate.prompt == prompt:
            build = candidate
    if not prompt:
        return None
    phase_def = PHASE_DEFS[phase_id]
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_critique_prompt.md"
    path.write_text(prompt, encoding="utf-8")
    if build is not None:
        write_prompt_manifest(path, build.manifest)
    else:
        record_prompt_manifest(
            path,
            prompt=prompt,
            prompt_type="critique",
            phase_id=phase_id,
            project_id=project_id,
            output_schema="critique_result",
        )
    return path


def write_preference_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """生成 preference comparison prompt 并写入 phase 目录."""
    build = build_preference_prompt(output_dir, project_id, phase_id)
    prompt = build.prompt if build else None
    if not prompt:
        return None
    phase_def = PHASE_DEFS[phase_id]
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_preference_prompt.md"
    path.write_text(prompt, encoding="utf-8")
    write_prompt_manifest(path, build.manifest)
    return path
