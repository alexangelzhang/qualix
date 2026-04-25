"""Execute 阶段的 lifecycle handler：从 cmd_execute 下沉的 sidecar 逻辑."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.runtime.lifecycle import register_handler

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


def handle_language_detect(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 检测代码仓库语言，将 Provider 存入 shared."""
    if not ctx.code_repo:
        return

    from pathlib import Path as _Path

    from dqg.languages import get_registry

    registry = get_registry()
    repo_root = _Path(ctx.code_repo).resolve()
    provider = registry.detect(repo_root)
    if provider:
        ctx.shared["language_provider"] = provider
        ctx.shared["language_id"] = provider.language_id


def handle_diff_context(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C/D: 收集增量 diff 上下文."""
    if ctx.phase_id not in ("Q06", "Q07") or not ctx.code_repo:
        return

    from dqg.context.diff_context import collect_diff_context, write_diff_context

    diff_ctx = collect_diff_context(ctx.code_repo, ctx.base_branch, ctx.feature_branch)
    if diff_ctx.has_changes:
        diff_path = write_diff_context(
            ctx.output_dir,
            ctx.project_id,
            ctx.phase_def["dir_suffix"],
            diff_ctx,
        )
        if diff_path:
            result.add_artifact("diff_context", str(diff_path))
            ctx.shared["diff_context"] = diff_ctx
    elif diff_ctx.error:
        result.add_warning(f"Diff analysis failed: {diff_ctx.error}")


def handle_weak_assert(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 收集弱断言上下文."""
    if ctx.phase_id != "Q06" or not ctx.code_repo:
        return

    from dqg.context.weak_assert_context import collect_weak_assert_context, write_weak_assert_context

    diff_ctx = ctx.shared.get("diff_context")
    provider = ctx.shared.get("language_provider")
    payload = collect_weak_assert_context(ctx.code_repo, diff_ctx, language_provider=provider)
    json_path, md_path = write_weak_assert_context(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_def["dir_suffix"],
        payload,
    )
    result.add_artifact("weak_assert_json", str(json_path))
    result.add_artifact("weak_assert_md", str(md_path))


def handle_coverage_matrix(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase A.5: 自动生成覆盖度矩阵."""
    from dqg.quality.coverage_matrix import write_coverage_matrix

    matrix_path = write_coverage_matrix(ctx.output_dir, ctx.project_id)
    if matrix_path:
        result.add_artifact("coverage_matrix", str(matrix_path))


def handle_business_mutations(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 自动推导业务域变异规则."""
    from dqg.quality.business_mutations import write_business_mutations

    mutations_path = write_business_mutations(ctx.output_dir, ctx.project_id)
    if mutations_path:
        result.add_artifact("business_mutations", str(mutations_path))


def handle_blast_radius(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 代码改动影响范围分析."""
    if not ctx.code_repo:
        return

    from dqg.quality.blast_radius import write_blast_radius

    radius_path = write_blast_radius(
        ctx.output_dir,
        ctx.project_id,
        ctx.code_repo,
        ctx.base_branch,
        ctx.feature_branch,
    )
    if radius_path:
        result.add_artifact("blast_radius", str(radius_path))


def handle_data_patterns(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase B/C: 注入历史故障数据模式."""
    from dqg.tracking.data_patterns import write_data_patterns

    path = write_data_patterns(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("data_patterns", str(path))


def handle_se_code_mapping(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase A.3/B/C/D: SE→Code 自动映射."""
    if not ctx.code_repo:
        return

    from dqg.cache.code_semantic_search import write_se_code_mapping

    path = write_se_code_mapping(
        ctx.output_dir,
        ctx.project_id,
        ctx.code_repo,
        ctx.phase_id,
    )
    if path:
        result.add_artifact("se_code_mapping", str(path))


def handle_bootstrap_context(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 生成启动上下文，减少 Agent 自探索 LLM 调用."""
    from dqg.context.bootstrap_context import write_bootstrap_context

    path = write_bootstrap_context(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_id,
        code_repo=ctx.code_repo,
    )
    if path:
        result.add_artifact("bootstrap_context", str(path))
        ctx.shared["bootstrap_context_path"] = str(path)


def handle_phase_contract(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 生成执行合同."""
    from dqg.runtime.phase_contract import generate_phase_contract

    path = generate_phase_contract(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("phase_contract", str(path))


def handle_requirement_smell(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q01: 需求异味检测（在结构化提取前运行）."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.path_utils import resolve_ingest_file

    dir_suffix = PHASE_DIR_MAP.get("Q01", "phaseA")
    phase_root = ctx.output_dir / ctx.project_id / dir_suffix

    # 读取需求原文
    text = ""
    for filename in ("plain_text_summary.md", "plain_text.txt"):
        path = resolve_ingest_file(phase_root, filename)
        if path and path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if text.strip():
                break

    if not text.strip():
        return

    from dqg.quality.requirement_smell import write_requirement_smells

    smell_path = write_requirement_smells(ctx.output_dir, ctx.project_id, text)
    if smell_path:
        result.add_artifact("requirement_smells", str(smell_path))


def handle_demand_trace(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q07: 需求驱动代码路径追踪."""
    if not ctx.code_repo:
        return

    from dqg.quality.demand_trace import write_demand_trace

    path = write_demand_trace(
        ctx.output_dir,
        ctx.project_id,
        ctx.code_repo,
        ctx.base_branch,
        ctx.feature_branch,
    )
    if path:
        result.add_artifact("demand_trace", str(path))


def handle_code_skeleton(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q07: TREEFRAG 代码骨架压缩 + Oracle 标注（provider dispatch）."""
    if not ctx.code_repo:
        return

    from pathlib import Path as _Path

    from dqg.constants import PHASE_DIR_MAP
    from dqg.json_utils import load_json, save_json
    from dqg.languages.registry import get_registry

    lang_id = ctx.shared.get("language_id", "java")
    dir_suffix = PHASE_DIR_MAP.get("Q07", "phaseD")
    int_dir = ctx.output_dir / ctx.project_id / dir_suffix / "_internal"

    target_files: list[_Path] = []
    se_code_mapping: dict[str, list[str]] = {}

    trace_path = int_dir / "_demand_trace.json"
    if trace_path.exists():
        trace_data = load_json(trace_path)
        if trace_data:
            repo = _Path(ctx.code_repo).resolve()
            for f in trace_data.get("traced_files", []):
                fp = repo / f
                if fp.exists():
                    target_files.append(fp)
            for t in trace_data.get("traced_methods", []):
                method = t.get("method", "")
                file_path = t.get("file", "")
                if method and file_path:
                    full = str(repo / file_path)
                    method_name = method.split(".")[-1] if "." in method else method
                    se_code_mapping.setdefault(full, []).append(method_name)

    if not target_files:
        return
    target_files = target_files[:30]

    provider = get_registry().get(lang_id)
    if provider is not None and hasattr(provider, "extract_skeleton"):
        from dqg.context.code_skeleton import SkeletonResult

        results: dict[str, SkeletonResult] = {}
        for fp in target_files:
            try:
                source = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            expand = set(se_code_mapping.get(str(fp), []))
            skel = provider.extract_skeleton(source, expand)
            if skel is not None:
                results[str(fp)] = skel
    else:
        from dqg.context.code_skeleton import extract_skeleton_for_files

        results = extract_skeleton_for_files(target_files, se_code_mapping)

    if not results:
        return

    int_dir.mkdir(parents=True, exist_ok=True)
    skeleton_data = {
        "file_count": len(results),
        "total_lines": sum(r.total_lines for r in results.values()),
        "skeleton_lines": sum(r.skeleton_lines for r in results.values()),
        "expanded_methods": sum(len(r.expanded_methods) for r in results.values()),
        "files": {
            fp: {
                "total_lines": r.total_lines,
                "skeleton_lines": r.skeleton_lines,
                "compression_ratio": r.compression_ratio,
                "expanded_methods": r.expanded_methods,
            }
            for fp, r in results.items()
        },
    }
    save_json(int_dir / "_code_skeleton.json", skeleton_data)

    md_parts = ["## CODE_SKELETON — TREEFRAG 代码骨架（自动生成）\n"]
    for fp, r in results.items():
        filename = _Path(fp).name
        md_parts.append(f"### {filename} ({r.skeleton_lines}/{r.total_lines} lines, {r.compression_ratio}x)")
        md_parts.append(f"```{lang_id}\n{r.skeleton_text}\n```\n")
    md_path = int_dir / "_code_skeleton.md"
    md_path.write_text("\n".join(md_parts), encoding="utf-8")

    result.add_artifact("code_skeleton_json", str(int_dir / "_code_skeleton.json"))
    result.add_artifact("code_skeleton_md", str(md_path))


def register_execute_handlers() -> None:
    """注册所有 execute 阶段的 handler."""
    register_handler(
        "language_detect",
        handle_language_detect,
        stage="execute",
        order=0,
    )
    register_handler(
        "bootstrap_context",
        handle_bootstrap_context,
        stage="execute",
        order=1,
    )
    register_handler(
        "phase_contract",
        handle_phase_contract,
        stage="execute",
        order=5,
    )
    register_handler(
        "diff_context",
        handle_diff_context,
        stage="execute",
        phases={"Q06", "Q07"},
        order=10,
    )
    register_handler(
        "weak_assert",
        handle_weak_assert,
        stage="execute",
        phases={"Q06"},
        order=20,
        depends_on=["diff_context"],
    )
    register_handler(
        "coverage_matrix",
        handle_coverage_matrix,
        stage="execute",
        phases={"Q04"},
        order=30,
    )
    register_handler(
        "business_mutations",
        handle_business_mutations,
        stage="execute",
        phases={"Q06"},
        order=40,
    )
    register_handler(
        "blast_radius",
        handle_blast_radius,
        stage="execute",
        phases={"Q05", "Q06"},
        order=50,
        depends_on=["diff_context"],
    )
    register_handler(
        "data_patterns",
        handle_data_patterns,
        stage="execute",
        phases={"Q05", "Q06"},
        order=60,
    )
    register_handler(
        "se_code_mapping",
        handle_se_code_mapping,
        stage="execute",
        phases={"Q02", "Q05", "Q06", "Q07"},
        order=70,
    )
    register_handler(
        "requirement_smell",
        handle_requirement_smell,
        stage="execute",
        phases={"Q01"},
        order=3,
    )
    register_handler(
        "demand_trace",
        handle_demand_trace,
        stage="execute",
        phases={"Q07"},
        order=75,
        depends_on=["se_code_mapping"],
    )
    register_handler(
        "code_skeleton",
        handle_code_skeleton,
        stage="execute",
        phases={"Q07"},
        order=80,
        depends_on=["demand_trace"],
    )
