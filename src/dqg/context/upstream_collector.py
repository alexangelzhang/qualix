"""Upstream Collector: 并行加载上游 Phase 产物、sidecar 文件（diff/memory/bug cases）."""

from __future__ import annotations

from pathlib import Path

from dqg.context.chunk_processor import (
    _collect_current_phase_inputs,
    _collect_phase_artifacts,
)
from dqg.context.chunk_summarizer import summarize_upstream_chunk
from dqg.core.model_registry import estimate_tokens
from dqg.core.profiles import get_profile, load_profile_context_l1
from dqg.core.state_machine import PHASE_DEFS, PhaseStatus
from dqg.log import get_logger
from dqg.path_utils import resolve_internal_file
from dqg.skill_tracker import render_relevant_cases_for_prompt

log = get_logger(__name__)

# Avoid circular import — ContextChunk is imported lazily or passed as type
_FACT_SUMMARY_THRESHOLD = 5000


def _collect_upstream_results(
    futures: dict,
    chunks: list,
) -> bool:
    """从并行 futures 中收集结果，追加到 chunks. 返回 force_summary 标志."""
    from dqg.context.context_loader import ContextChunk

    current_phase_chunks = futures["current"].result()
    if current_phase_chunks:
        chunks.extend(current_phase_chunks)

    if futures.get("gap") is not None:
        checklist = futures["gap"].result()
        if checklist and checklist.strip():
            chunks.append(
                ContextChunk(
                    source="Historical GAP Patterns (auto-extracted from RSM)",
                    content=checklist,
                    token_estimate=estimate_tokens(checklist),
                    priority=1,
                )
            )

    if futures.get("profile") is not None:
        profile_id, profile_context = futures["profile"].result()
        chunks.append(
            ContextChunk(
                source=f"Profile {profile_id} baseline and thresholds",
                content=profile_context,
                token_estimate=estimate_tokens(profile_context),
                priority=-1,
            )
        )

    fact_count = futures["fact_count"].result()
    force_summary = fact_count >= _FACT_SUMMARY_THRESHOLD

    if futures.get("rsm") is not None:
        rsm_summary = futures["rsm"].result()
        if rsm_summary:
            chunks.append(
                ContextChunk(
                    source="RSM Coverage Summary (global)",
                    content=rsm_summary,
                    token_estimate=estimate_tokens(rsm_summary),
                    priority=-2,
                )
            )

    for dep_id, fut in futures.get("upstreams", {}).items():
        upstream_chunks = fut.result()
        upstream_chunks = [summarize_upstream_chunk(c, dep_id, force=force_summary) for c in upstream_chunks]
        chunks.extend(upstream_chunks)

    return force_summary


def load_upstream_context(
    output_dir: Path,
    project_id: str,
    target_phase: str,
    phase_root: Path,
    state: object,
    upstream_phases: list[str],
) -> tuple[list, bool]:
    """并行加载上游 Phase 产物、当前 Phase 输入、Profile、RSM、GAP 等.

    Returns:
        (chunks, force_summary) — 收集到的 chunks 和是否需要强制摘要。
    """
    from concurrent.futures import ThreadPoolExecutor

    from dqg.memory.memory_layer import MemoryLayer

    chunks: list = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures: dict = {}

        futures["current"] = pool.submit(_collect_current_phase_inputs, phase_root, target_phase)

        # GAP 模式（仅 Q01）
        if target_phase == "Q01":

            def _load_gap():
                from dqg.memory.rsm_patterns import extract_gap_patterns, format_patterns_as_checklist

                patterns = extract_gap_patterns(output_dir)
                return format_patterns_as_checklist(patterns)

            futures["gap"] = pool.submit(_load_gap)

        # Profile context（Q03-Q07）— 使用 L1 Phase 感知压缩减少 token 消耗
        if target_phase in {"Q04", "Q03", "Q05", "Q06", "Q07"}:

            def _load_profile():
                profile = get_profile(getattr(state, "profile_id", None))
                return profile.profile_id, load_profile_context_l1(profile, target_phase)

            futures["profile"] = pool.submit(_load_profile)

        # Fact count
        futures["fact_count"] = pool.submit(MemoryLayer(output_dir).get_fact_count, project_id)

        # RSM 覆盖率
        if target_phase not in {"Q01"}:
            from dqg.schemas.rsm import _rsm_path

            if _rsm_path(output_dir, project_id).exists():

                def _load_rsm():
                    from dqg.schemas.rsm import compute_coverage, load_rsm

                    rsm_lifecycle = load_rsm(output_dir, project_id)
                    if rsm_lifecycle:
                        return compute_coverage(rsm_lifecycle, project_id).summary()
                    return None

                futures["rsm"] = pool.submit(_load_rsm)

        # 上游 Phase 产物（每个 dep 并行，带增量检测）
        approved_deps = [
            dep_id
            for dep_id in upstream_phases
            if (dep_state := state.phases.get(dep_id))
            and dep_state.status in (PhaseStatus.APPROVED, PhaseStatus.PENDING_REVIEW)
        ]

        # 增量检测：比对上游产物快照，跳过未变更的 Phase
        from dqg.constants import REPORT_MAP, STRUCTURED_JSON_MAP
        from dqg.context.file_snapshot import diff_snapshot, load_snapshot, save_snapshot, take_snapshot

        snapshot_dir = phase_root / "_internal"
        old_snapshot = load_snapshot(snapshot_dir)
        deps_to_load: list[str] = []
        all_upstream_files: list[Path] = []

        for dep_id in approved_deps:
            dep_def = PHASE_DEFS.get(dep_id)
            if not dep_def:
                continue
            dep_dir = output_dir / project_id / dep_def["dir_suffix"]
            dep_files = []
            json_file = STRUCTURED_JSON_MAP.get(dep_id)
            if json_file:
                dep_files.append(dep_dir / json_file)
            report_file = REPORT_MAP.get(dep_id)
            if report_file:
                dep_files.append(dep_dir / report_file)
            img_sem = dep_dir / "image_semantics.md"
            if img_sem.exists():
                dep_files.append(img_sem)

            all_upstream_files.extend(dep_files)
            changed, _ = diff_snapshot(old_snapshot, dep_files)
            if changed:
                deps_to_load.append(dep_id)
            else:
                log.debug("Upstream %s unchanged, skipping reload", dep_id)

        # 如果没有旧快照（首次运行），加载全部
        if not old_snapshot:
            deps_to_load = approved_deps

        futures["upstreams"] = {
            dep_id: pool.submit(_collect_phase_artifacts, output_dir, project_id, dep_id) for dep_id in deps_to_load
        }

        # 收集所有 future 结果
        force_summary = _collect_upstream_results(futures, chunks)

    # 更新快照
    if all_upstream_files:
        new_snapshot = take_snapshot(all_upstream_files)
        save_snapshot(snapshot_dir, new_snapshot)

    return chunks, force_summary


def load_sidecar_context(
    output_dir: Path,
    project_id: str,
    target_phase: str,
    phase_root: Path,
    all_chunks: list,
) -> None:
    """加载 sidecar 文件（diff context、memory、bug cases），原地追加到 all_chunks."""
    from dqg.context.context_loader import ContextChunk

    # Diff context（Q06/Q07）— 直接串行读取，两个小文件不值得开线程池
    if target_phase in ("Q06", "Q07"):
        diff_path = resolve_internal_file(phase_root, "_diff_context.md")
        if diff_path.exists():
            diff_text = diff_path.read_text(encoding="utf-8")
            all_chunks.append(
                ContextChunk(
                    source=f"Diff context for Phase {target_phase} (incremental)",
                    content=diff_text,
                    token_estimate=estimate_tokens(diff_text),
                    priority=-2,
                )
            )

    # Memory 文件
    mem_file = Path(".dqg/MEMORY.md")
    if mem_file.exists():
        mem_text = mem_file.read_text(encoding="utf-8")
        if mem_text and mem_text.strip():
            from dqg.memory.memory_filter import filter_memory_for_phase, parse_memory_entries

            entries = parse_memory_entries(mem_text)
            filtered_mem = filter_memory_for_phase(entries, project_id, target_phase)
            if filtered_mem.strip():
                all_chunks.append(
                    ContextChunk(
                        source="Persistent Memory (.dqg/MEMORY.md)",
                        content=filtered_mem,
                        token_estimate=estimate_tokens(filtered_mem),
                        priority=-3,
                    )
                )

    # Bug cases 依赖前面所有 chunks 的 relevance_seed（串行）
    inject_bug_cases = target_phase in {"Q01", "Q04", "Q03", "Q05", "Q06", "Q07"}
    if inject_bug_cases:
        from dqg.context.context_loader import _build_relevance_seed

        relevance_input = _build_relevance_seed(all_chunks)
        if relevance_input.strip():
            bug_cases_md = render_relevant_cases_for_prompt(target_phase, relevance_input)
            if bug_cases_md:
                all_chunks.append(
                    ContextChunk(
                        source=f"Bug cases for Phase {target_phase} (relevance-matched)",
                        content=bug_cases_md,
                        token_estimate=estimate_tokens(bug_cases_md),
                        priority=0,
                    )
                )

    # Gene 匹配注入：从历史 Critique 结晶中匹配相关评审基因
    try:
        from dqg.quality.gene_store import load_genes_for_phase, match_genes, render_genes_for_prompt

        # base_dir 为项目根目录（output_dir 的父目录）
        base_dir = output_dir.parent if output_dir.name == "output" else output_dir
        genes = load_genes_for_phase(base_dir, target_phase)
        if genes:
            from dqg.context.context_loader import _build_relevance_seed

            seed = _build_relevance_seed(all_chunks)
            matched = match_genes(genes, seed)
            if matched:
                gene_text = render_genes_for_prompt(matched)
                all_chunks.append(
                    ContextChunk(
                        source=f"Critique Genes for Phase {target_phase} ({len(matched)} matched)",
                        content=gene_text,
                        token_estimate=estimate_tokens(gene_text),
                        priority=-1,
                    )
                )
    except Exception:
        from dqg.log import get_logger

        get_logger(__name__).debug("Gene matching skipped", exc_info=True)

    # Crystal 注入：从历史高分执行中注入成功模式
    try:
        from dqg.context.skill_crystal import load_crystals_for_phase, render_crystals_for_prompt

        base_dir = output_dir.parent if output_dir.name == "output" else output_dir
        crystals = load_crystals_for_phase(base_dir, target_phase)
        if crystals:
            crystal_text = render_crystals_for_prompt(crystals)
            all_chunks.append(
                ContextChunk(
                    source=f"Skill Crystals for Phase {target_phase} ({len(crystals)} patterns)",
                    content=crystal_text,
                    token_estimate=estimate_tokens(crystal_text),
                    priority=-1,
                )
            )
    except Exception:
        from dqg.log import get_logger

        get_logger(__name__).debug("Crystal loading skipped", exc_info=True)
