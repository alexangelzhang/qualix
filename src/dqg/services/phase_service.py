"""Phase 执行辅助服务：profile manifest 写入、上下文检查等纯业务逻辑.

从 commands/phase.py 下沉的业务函数，commands 层只做参数解析和 CLI 输出。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from dqg.constants import (
    BUG_CASE_RELEVANCE_EXCERPT_LIMIT,
    BUG_CASE_RELEVANCE_INTERNAL_FILES,
    BUG_CASE_RELEVANCE_MAX_CASES,
    BUG_CASE_RELEVANCE_SEED_LIMIT,
)
from dqg.core.state_machine import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.path_utils import resolve_ingest_file, resolve_internal_file
from dqg.text_utils import REPORT_MAP
from dqg.tracking.case_selector import render_relevant_cases_for_prompt

if TYPE_CHECKING:
    from pathlib import Path


def read_relevance_excerpt(path: Path, limit: int = BUG_CASE_RELEVANCE_EXCERPT_LIMIT) -> str:
    """读取用于相关性匹配的轻量摘录，避免把整份大文件再扫一遍。"""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if len(text) > limit:
        return text[:limit] + "\n...(截断)"
    return text


def _build_bug_case_relevance_text(phase_root: Path, seed_text: str | None = None) -> str:
    """构建 bug case relevance matching 所需的输入文本。"""
    parts: list[str] = []
    has_seed_text = bool(seed_text and seed_text.strip())
    if has_seed_text:
        parts.append(seed_text.strip()[:BUG_CASE_RELEVANCE_SEED_LIMIT])

    for filename in BUG_CASE_RELEVANCE_INTERNAL_FILES:
        if has_seed_text and filename == "_upstream_context.md":
            continue
        excerpt = read_relevance_excerpt(resolve_internal_file(phase_root, filename))
        if excerpt:
            parts.append(excerpt)

    image_excerpt = read_relevance_excerpt(phase_root / "image_semantics.md")
    if image_excerpt:
        parts.append(image_excerpt)

    summary_excerpt = read_relevance_excerpt(resolve_ingest_file(phase_root, "plain_text_summary.md"))
    if summary_excerpt:
        parts.append(summary_excerpt)
    else:
        raw_excerpt = read_relevance_excerpt(resolve_ingest_file(phase_root, "plain_text.txt"))
        if raw_excerpt:
            parts.append(raw_excerpt)

    return "\n\n".join(part for part in parts if part)


def _cleanup_bug_case_manifest(phase_root: Path) -> None:
    for path in (phase_root / "_internal" / "_bug_cases.md", phase_root / "_bug_cases.md"):
        if path.exists():
            path.unlink()


def write_phase_profile_manifest(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    profile_id: str,
    relevance_text: str | None = None,
) -> None:
    """写入 Phase 的 profile manifest（profile.json + profile_context.md + bug_cases.md）."""
    from dqg.core.profiles import get_profile, profile_to_payload, render_profile_context_markdown

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return

    phase_root = _phase_dir(output_dir, project_id, phase_def)
    phase_root.mkdir(parents=True, exist_ok=True)
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    int_dir.mkdir(parents=True, exist_ok=True)

    profile = get_profile(profile_id)
    payload = profile_to_payload(profile)
    (int_dir / "_profile.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (int_dir / "_profile_context.md").write_text(render_profile_context_markdown(profile), encoding="utf-8")

    relevance_input = _build_bug_case_relevance_text(phase_root, relevance_text)
    if not relevance_input.strip():
        _cleanup_bug_case_manifest(phase_root)
        return

    bug_cases_md = render_relevant_cases_for_prompt(
        phase_id,
        relevance_input,
        max_cases=BUG_CASE_RELEVANCE_MAX_CASES,
    )
    if bug_cases_md:
        (int_dir / "_bug_cases.md").write_text(bug_cases_md, encoding="utf-8")
        legacy_bug_cases = phase_root / "_bug_cases.md"
        if legacy_bug_cases.exists():
            legacy_bug_cases.unlink()
    else:
        _cleanup_bug_case_manifest(phase_root)

    # 跨项目知识自动注入：关联历史相似项目的 GAP/BUG/LESSON
    _inject_cross_project_insights(output_dir, project_id, phase_id, int_dir)


def profile_context_warnings(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """检查 phase 报告是否包含 PROFILE_CONTEXT 章节."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _phase_dir(output_dir, project_id, phase_def)
    report_file = REPORT_MAP.get(phase_id)
    if not report_file:
        return []
    warnings: list[str] = []
    profile_ctx_path = resolve_internal_file(pd, "_profile_context.md")
    if not profile_ctx_path.exists():
        warnings.append(f"缺少 profile 上下文文件: {profile_ctx_path}")
    report_path = pd / report_file
    if report_path.exists() and "## PROFILE_CONTEXT" not in report_path.read_text(encoding="utf-8"):
        warnings.append(f"报告未包含 PROFILE_CONTEXT: {report_path}")
    return warnings


def _inject_cross_project_insights(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    int_dir: Path,
) -> None:
    """将跨项目知识网络的相似经验注入到 Phase 上下文中.

    调用 knowledge_network 的 get_cross_project_insights()，
    格式化后写入 _cross_project_insights.md，供 skill prompt 引用。
    """
    try:
        from dqg.memory.knowledge_network import (
            build_cross_project_links,
            format_insights,
            get_cross_project_insights,
            index_bug_cases,
            index_project_facts,
        )

        # 确保当前项目的事实已索引
        index_project_facts(output_dir, project_id, phase_id)
        index_bug_cases(output_dir)
        build_cross_project_links(output_dir)

        insights = get_cross_project_insights(output_dir, project_id, phase_id)
        if not insights:
            # 清理旧文件
            old = int_dir / "_cross_project_insights.md"
            if old.exists():
                old.unlink()
            return

        formatted = format_insights(insights)
        md_lines = [
            "## CROSS_PROJECT_INSIGHTS — 跨项目历史经验（自动注入）",
            "",
            "以下是从历史项目中关联到的相似经验，请在执行时参考避免重犯。",
            "",
            formatted,
        ]
        (int_dir / "_cross_project_insights.md").write_text(
            "\n".join(md_lines), encoding="utf-8"
        )
    except Exception:
        from dqg.log import get_logger
        get_logger(__name__).warning("跨项目知识注入失败，不阻断主流程", exc_info=True)
