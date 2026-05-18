"""Pipeline I/O: Worker 输出提取、报告渲染、Critique 反馈处理."""

from __future__ import annotations

import re
from pathlib import Path

from dqg.log import get_logger

log = get_logger(__name__)

_RE_JSON_BLOCK = re.compile(r"```json\s*\n([\s\S]*?)\n```")


def _extract_json_block(content: str) -> str | None:
    """从文本中提取 JSON 块（```json 或裸 JSON）."""
    json_match = _RE_JSON_BLOCK.search(content)
    if json_match:
        return json_match.group(1)
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return content[start : end + 1]
    return None


def extract_and_save_json(
    content: str,
    phase_dir: Path,
    phase_id: str,
    project_id: str,
) -> Path | None:
    """从 Worker 输出中提取结构化 JSON，校验后保存.

    Returns:
        保存的 JSON 文件路径，提取失败返回 None。
    """
    from dqg.agents.structured_retry import try_parse_structured_output
    from dqg.text_utils import STRUCTURED_JSON_MAP

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return None

    raw_json = _extract_json_block(content)
    if raw_json is None:
        log.warning("No JSON found in Worker output for Phase %s", phase_id)
        return None

    parsed, errors = try_parse_structured_output(raw_json)
    if parsed is None:
        log.warning("JSON parse failed for Phase %s: %s", phase_id, errors)
        (phase_dir / f"_raw_{json_file}").write_text(raw_json, encoding="utf-8")
        return None

    if "project_id" not in parsed:
        parsed["project_id"] = project_id

    json_path = phase_dir / json_file
    from dqg.json_utils import save_json

    save_json(json_path, parsed)
    return json_path


def render_report_from_json(
    json_path: Path,
    phase_dir: Path,
    phase_id: str,
) -> Path | None:
    """从结构化 JSON 渲染 md 报告（JSON 是 source of truth，md 是视图）."""
    from dqg.json_utils import load_json
    from dqg.reporting.render import render_report
    from dqg.text_utils import REPORT_MAP

    report_file = REPORT_MAP.get(phase_id)
    if not report_file:
        return None

    data = load_json(json_path)
    if data is None:
        return None
    md_content = render_report(phase_id, data)
    if not md_content:
        return None

    report_path = phase_dir / report_file
    report_path.write_text(md_content, encoding="utf-8")
    log.info("Rendered md report from JSON: %s -> %s", json_path.name, report_file)
    return report_path


def format_deterministic_report(errors: list[str], phase_id: str) -> str:
    """格式化 deterministic checker 结果为 md，供 LLM Judge 参考."""
    lines = [f"# Deterministic Check Results — Phase {phase_id}\n"]
    if not errors:
        lines.append("所有自动化校验通过（schema/交叉引用/覆盖率）。\n")
        lines.append("LLM Judge 请聚焦于语义层面的判断。")
    else:
        lines.append(f"发现 {len(errors)} 个自动化校验问题：\n")
        for i, err in enumerate(errors, 1):
            lines.append(f"{i}. {err}")
        lines.append("\n以上问题已由 deterministic checker 确认，LLM Judge 无需重复验证。")
        lines.append("请在此基础上补充语义层面的判断。")
    return "\n".join(lines)


def process_critique_feedback(content: str, phase_dir: Path, phase_id: str) -> None:
    """解析 Critique 的结构化反馈，生成 Worker 可消费的修正指令文件."""
    from dqg.agents.structured_retry import try_parse_structured_output

    raw = _extract_json_block(content)
    if raw is None:
        return

    parsed, _errors = try_parse_structured_output(raw)
    if not parsed:
        return

    try:
        from dqg.schemas.critique_feedback import CritiqueFeedback

        feedback = CritiqueFeedback.model_validate(parsed)
    except Exception:
        return

    # 生成 Worker 可消费的修正指令
    worker_instructions = feedback.render_for_worker()
    instructions_path = phase_dir / "_critique_instructions.md"
    instructions_path.write_text(worker_instructions, encoding="utf-8")

    # 保存结构化反馈（供 Adaptive Loop 消费）
    structured_path = phase_dir / "_critique_structured.json"
    from dqg.json_utils import save_json as _save_json

    _save_json(structured_path, parsed)
    log.info(
        "Critique feedback: %d actionable items (of %d total)",
        len(feedback.actionable_items),
        len(feedback.items),
    )

    # 闭环1: Critique -> RSM 自动回流
    from dqg.schemas.rsm import apply_mutations, load_rsm, mutations_from_critique, save_rsm

    mutations = mutations_from_critique(parsed)
    if mutations:
        output_dir = phase_dir.parent.parent
        project_id = phase_dir.parent.name
        lifecycle = load_rsm(output_dir, project_id)
        lifecycle, applied = apply_mutations(lifecycle, mutations)
        if applied:
            save_rsm(output_dir, project_id, lifecycle)
            log.info("RSM updated via Critique feedback: %s", applied)
