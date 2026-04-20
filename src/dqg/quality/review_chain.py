"""自动串联 Judge → Critique → Preference 的组合 prompt.

将三个独立的评审步骤合并为一个连续执行的 prompt，
AI IDE 读取后一次性完成全部评审流程。
"""

from __future__ import annotations

from pathlib import Path

from dqg.quality.critique import generate_critique_prompt
from dqg.quality.judge import generate_judge_prompt
from dqg.cache.llm_result_cache import get_cached_result
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.log import get_logger

log = get_logger(__name__)


def _strip_prompt_header(prompt: str) -> str:
    """移除独立 prompt 的标题段，便于串联复用。"""
    lines = prompt.split("\n")
    return "\n".join(lines[2:]) if len(lines) > 2 else prompt


def build_review_chain_payload(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, str] | None:
    """一次性构建 review chain 所需的各段 prompt.

    finalize 需要同时写出 Judge / Critique / Preference 三份文件，
    这里先统一生成并复用同一份内容，避免重复构造。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    pd = _phase_dir(output_dir, project_id, phase_def)

    # 检查缓存: 产物未变更时跳过 LLM 调用
    cached_judge = get_cached_result(output_dir, project_id, phase_id, "judge")
    cached_critique = get_cached_result(output_dir, project_id, phase_id, "critique")

    if cached_judge and cached_critique:
        log.info(
            "Review chain: judge + critique 均命中缓存，跳过 prompt 生成 (%s/%s)",
            project_id, phase_id,
        )
        return {
            "judge_prompt": "",
            "critique_prompt": "",
            "review_chain_prompt": "",
            "cached_judge": cached_judge,
            "cached_critique": cached_critique,
            "all_cached": True,
        }

    judge = generate_judge_prompt(output_dir, project_id, phase_id) if not cached_judge else None
    critique = generate_critique_prompt(output_dir, project_id, phase_id) if not cached_critique else None

    if not judge and not critique and not cached_judge and not cached_critique:
        return None

    lines = [
        f"# 自动评审链 — Phase {phase_id}: {phase_def['name']}",
        "",
        "本 prompt 包含三个连续执行的评审步骤。请按顺序完成，不要跳过。",
        "",
        "---",
        "",
        "## 步骤 1/3: 独立评审 (Judge)",
        "",
    ]

    if cached_judge:
        lines.append(f"（Judge 结果已缓存，产物未变更，跳过。缓存评分: {cached_judge.get('overall_score', '?')}/5）")
    elif judge:
        lines.append(_strip_prompt_header(judge))
    else:
        lines.append("（此 Phase 不支持 Judge 评审，跳过）")

    lines.extend([
        "",
        "---",
        "",
        "## 步骤 2/3: 自我批评 (Critique)",
        "",
    ])

    if cached_critique:
        lines.append(f"（Critique 结果已缓存，产物未变更，跳过。）")
    elif critique:
        lines.append(_strip_prompt_header(critique))
    else:
        lines.append("（此 Phase 不支持 Critique，跳过）")

    lines.extend([
        "",
        "---",
        "",
        "## 步骤 3/3: 偏好比较 (Preference)",
        "",
        "完成步骤 2 的修正后（如果有 v2 产物），执行偏好比较。",
        "",
    ])

    # Preference prompt 依赖 v2 产物，这里给出指引
    report_map = {
        "Q01": ("phase_a_report.md", "phase_a_structured.json"),
        "Q04": ("tech_design_coverage_review.md", "phase_a5_structured.json"),
        "Q03": ("tech_design_quality_review.md", "phase_a6_structured.json"),
        "Q06": ("ut_audit_report.md", "phase_c_structured.json"),
    }
    files = report_map.get(phase_id)
    if files:
        report_file, json_file = files
        v2_report = report_file.replace(".md", "_v2.md")
        v2_json = json_file.replace(".json", "_v2.json")

        lines.extend([
            "如果步骤 2 产出了 v2 修正版本，请比较：",
            f"- v1: `{pd / report_file}` + `{pd / json_file}`",
            f"- v2: `{pd / v2_report}` + `{pd / v2_json}`",
            "",
            "比较维度：完备性、准确性、证据性",
            "",
            f"将偏好结果保存到: `{pd / '_preference.json'}`",
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
            '    {"critique_issue": "...", "was_valid": true, "impact": "high/medium/low", "should_persist": true}',
            "  ],",
            '  "summary": "一句话总结"',
            "}",
            "```",
        ])
    else:
        lines.append("（此 Phase 不支持 Preference 比较）")

    lines.extend([
        "",
        "---",
        "",
        "## 完成",
        "",
        "三步评审完成后，请汇总：",
        "1. Judge 评分（1-5 各维度）",
        "2. Critique 发现的问题数量和修正情况",
        "3. Preference 偏好判定（v1/v2/tie）",
        "4. 总体建议：approve / 需要修改",
    ])

    return {
        "judge_prompt": judge or "",
        "critique_prompt": critique or "",
        "review_chain_prompt": "\n".join(lines),
        "cached_judge": cached_judge,
        "cached_critique": cached_critique,
        "all_cached": False,
    }


def generate_review_chain_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> str | None:
    """生成 Judge → Critique → Preference 串联 prompt.

    一个 prompt 完成三步评审，AI IDE 读取后连续执行。
    """
    payload = build_review_chain_payload(output_dir, project_id, phase_id)
    if not payload:
        return None
    return payload["review_chain_prompt"]


def write_review_chain_prompt(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    prompt: str | None = None,
) -> Path | None:
    """生成串联评审 prompt 并写入 phase 目录."""
    if prompt is None:
        prompt = generate_review_chain_prompt(output_dir, project_id, phase_id)
    if not prompt:
        return None

    phase_def = PHASE_DEFS[phase_id]
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)

    path = pd / "_review_chain.md"
    path.write_text(prompt, encoding="utf-8")
    return path
