"""Execute 阶段的 lifecycle handler：从 cmd_execute 下沉的 sidecar 逻辑."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qualix.runtime.lifecycle import register_handler, register_pre_check

if TYPE_CHECKING:
    from qualix.runtime.execution_context import ExecutionContext
    from qualix.runtime.result import PhaseResult


def handle_persist_inputs(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 持久化 CLI 输入到 _inputs.json，供 finalize 阶段读取."""
    if not ctx.internal_dir:
        return
    from qualix.json_utils import save_json

    inputs: dict = {}
    if ctx.code_repo:
        inputs["code_repo"] = ctx.code_repo
    if ctx.code_repos:
        inputs["code_repos"] = ctx.code_repos
    if ctx.base_branch != "master":
        inputs["base_branch"] = ctx.base_branch
    if ctx.feature_branch != "HEAD":
        inputs["feature_branch"] = ctx.feature_branch
    if ctx.coverage_report:
        inputs["coverage_report"] = ctx.coverage_report

    if inputs:
        ctx.internal_dir.mkdir(parents=True, exist_ok=True)
        inputs_path = ctx.internal_dir / "_inputs.json"
        # 合并已有内容（auto 模式可能已写入）
        if inputs_path.exists():
            from qualix.json_utils import load_json

            existing = load_json(inputs_path) or {}
            existing.update(inputs)
            inputs = existing
        save_json(inputs_path, inputs)


def handle_language_detect(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 检测代码仓库语言，将 Provider 存入 shared."""
    if not ctx.code_repo:
        return

    from pathlib import Path as _Path

    from qualix.languages import get_registry

    registry = get_registry()
    repo_root = _Path(ctx.code_repo).resolve()
    provider = registry.detect(repo_root)
    if provider:
        ctx.shared["language_provider"] = provider
        ctx.shared["language_id"] = provider.language_id


def handle_upstream_quality(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 检查上游产物内容质量（不只是文件存在性）."""
    from qualix.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(ctx.phase_id, {})
    deps = phase_def.get("depends_on", [])
    if not deps:
        return

    from qualix.runtime.preflight import _check_upstream_quality

    quality_check = _check_upstream_quality(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if quality_check["status"] == "FAIL":
        result.warnings.append(f"Upstream quality: {quality_check['detail']}")
        ctx.shared["upstream_quality_warning"] = quality_check["detail"]


def handle_diff_context(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C/D: 收集增量 diff 上下文（支持多 repo）."""
    if ctx.phase_id not in ("Q06", "Q07"):
        return
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from qualix.context.diff_context import collect_diff_context, write_diff_context

    # 多 repo 时合并 diff 结果
    merged_diff = None
    for repo in repos:
        diff_ctx = collect_diff_context(repo, ctx.base_branch, ctx.feature_branch)
        if diff_ctx.has_changes:
            if merged_diff is None:
                merged_diff = diff_ctx
            else:
                merged_diff.changed_files.extend(diff_ctx.changed_files)
                merged_diff.added_files.extend(diff_ctx.added_files)
                merged_diff.modified_files.extend(diff_ctx.modified_files)
                merged_diff.deleted_files.extend(diff_ctx.deleted_files)
                merged_diff.total_additions += diff_ctx.total_additions
                merged_diff.total_deletions += diff_ctx.total_deletions
                merged_diff.diff_text += f"\n\n# --- {repo} ---\n" + diff_ctx.diff_text
        elif diff_ctx.error:
            result.add_warning(f"Diff analysis failed for {repo}: {diff_ctx.error}")

    if merged_diff and merged_diff.has_changes:
        diff_path = write_diff_context(
            ctx.output_dir,
            ctx.project_id,
            ctx.phase_def["dir_suffix"],
            merged_diff,
        )
        if diff_path:
            result.add_artifact("diff_context", str(diff_path))
            ctx.shared["diff_context"] = merged_diff


def handle_weak_assert(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 收集弱断言上下文（支持多 repo）."""
    if ctx.phase_id != "Q06":
        return
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from qualix.context.weak_assert_context import collect_weak_assert_context, write_weak_assert_context

    diff_ctx = ctx.shared.get("diff_context")
    provider = ctx.shared.get("language_provider")
    # 使用第一个 repo 作为主 repo（weak_assert 分析基于 diff 结果）
    payload = collect_weak_assert_context(repos[0], diff_ctx, language_provider=provider)
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
    from qualix.quality.coverage_matrix import write_coverage_matrix

    matrix_path = write_coverage_matrix(ctx.output_dir, ctx.project_id)
    if matrix_path:
        result.add_artifact("coverage_matrix", str(matrix_path))


def handle_business_mutations(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 自动推导业务域变异规则."""
    from qualix.quality.business_mutations import write_business_mutations

    mutations_path = write_business_mutations(ctx.output_dir, ctx.project_id)
    if mutations_path:
        result.add_artifact("business_mutations", str(mutations_path))


def handle_jacoco_report(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 对每个 code_repo 自动运行 mvn jacoco:report 生成 XML 报告."""
    import contextlib
    import subprocess
    from pathlib import Path

    from qualix.quality.compile_check import _build_env_for_java, detect_build_tool
    from qualix.quality.coverage_gate import find_jacoco_report

    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    for repo in repos:
        repo_path = Path(repo).resolve()
        if not repo_path.is_dir():
            continue
        if detect_build_tool(repo_path) != "maven":
            continue
        if not list(repo_path.rglob("jacoco.exec")):
            continue
        if find_jacoco_report(repo_path):
            continue
        env = _build_env_for_java(repo_path)
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            subprocess.run(
                "mvn jacoco:report -q --batch-mode",
                cwd=str(repo_path),
                shell=True,
                env=env,
                timeout=120,
                capture_output=True,
            )


def handle_blast_radius(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase C: 代码改动影响范围分析（支持多 repo）."""
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from qualix.quality.blast_radius import write_blast_radius

    for repo in repos:
        radius_path = write_blast_radius(
            ctx.output_dir,
            ctx.project_id,
            repo,
            ctx.base_branch,
            ctx.feature_branch,
        )
        if radius_path:
            result.add_artifact("blast_radius", str(radius_path))


def handle_data_patterns(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase B/C: 注入历史故障数据模式."""
    from qualix.tracking.data_patterns import write_data_patterns

    path = write_data_patterns(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("data_patterns", str(path))


def handle_se_code_mapping(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase A.3/B/C/D: SE→Code 自动映射（支持多 repo，结果合并）."""
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from qualix.cache.code_semantic_search import write_se_code_mapping

    # 多 repo 时逐个调用，最后一个的结果文件会覆盖前一个
    # 但 map_se_to_code 内部会搜索 repo 中的代码，多 repo 需要合并
    # 当前实现：逐 repo 调用，后续可优化为合并模式
    last_path = None
    for repo in repos:
        path = write_se_code_mapping(
            ctx.output_dir,
            ctx.project_id,
            repo,
            ctx.phase_id,
        )
        if path:
            last_path = path
    if last_path:
        result.add_artifact("se_code_mapping", str(last_path))


def handle_bootstrap_context(ctx: ExecutionContext, result: PhaseResult) -> None:
    """所有 Phase: 生成启动上下文，减少 Agent 自探索 LLM 调用."""
    from qualix.context.bootstrap_context import write_bootstrap_context

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
    from qualix.runtime.phase_contract import generate_phase_contract

    path = generate_phase_contract(ctx.output_dir, ctx.project_id, ctx.phase_id)
    if path:
        result.add_artifact("phase_contract", str(path))


def handle_requirement_smell(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q01: 需求异味检测（在结构化提取前运行）."""
    from qualix.constants import PHASE_DIR_MAP
    from qualix.path_utils import resolve_ingest_file

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

    from qualix.quality.requirement_smell import write_requirement_smells

    smell_path = write_requirement_smells(ctx.output_dir, ctx.project_id, text)
    if smell_path:
        result.add_artifact("requirement_smells", str(smell_path))


def handle_demand_trace(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q07: 需求驱动代码路径追踪（支持多 repo）."""
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from qualix.quality.demand_trace import write_demand_trace

    for repo in repos:
        path = write_demand_trace(
            ctx.output_dir,
            ctx.project_id,
            repo,
            ctx.base_branch,
            ctx.feature_branch,
        )
        if path:
            result.add_artifact("demand_trace", str(path))


def handle_code_skeleton(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Phase Q07: TREEFRAG 代码骨架压缩 + Oracle 标注（支持多 repo）."""
    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    from pathlib import Path as _Path

    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json, save_json
    from qualix.languages.registry import get_registry

    lang_id = ctx.shared.get("language_id", "java")
    dir_suffix = PHASE_DIR_MAP.get("Q07", "phaseD")
    int_dir = ctx.output_dir / ctx.project_id / dir_suffix / "_internal"

    target_files: list[_Path] = []
    se_code_mapping: dict[str, list[str]] = {}

    trace_path = int_dir / "_demand_trace.json"
    if trace_path.exists():
        trace_data = load_json(trace_path)
        if trace_data:
            # 尝试在所有 repo 中解析文件路径
            for f in trace_data.get("traced_files", []):
                for repo in repos:
                    fp = _Path(repo).resolve() / f
                    if fp.exists():
                        target_files.append(fp)
                        break
            for t in trace_data.get("traced_methods", []):
                method = t.get("method", "")
                file_path = t.get("file", "")
                if method and file_path:
                    for repo in repos:
                        full = str(_Path(repo).resolve() / file_path)
                        if _Path(full).exists():
                            method_name = method.split(".")[-1] if "." in method else method
                            se_code_mapping.setdefault(full, []).append(method_name)
                            break

    if not target_files:
        return
    target_files = target_files[:30]

    provider = get_registry().get(lang_id)
    if provider is not None and hasattr(provider, "extract_skeleton"):
        from qualix.context.code_skeleton import SkeletonResult

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
        from qualix.context.code_skeleton import extract_skeleton_for_files

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


def _q06_compile_precheck(ctx: ExecutionContext, result: PhaseResult) -> bool:
    """Q06 pre-execute：测试代码不编译则跳过 LLM 审计，节省 token. 返回 True = abort."""
    from pathlib import Path

    from qualix.runtime.events import EventType

    if not ctx.code_repos:
        return False
    from qualix.languages.java.provider import JavaProvider

    java_provider = JavaProvider()
    for repo in ctx.code_repos:
        cr = java_provider.compile_check(Path(repo))
        if not cr.passed and not cr.skipped:
            result.add_error(f"Q06 pre-check: 测试编译失败，跳过 LLM 审计 ({repo}): {cr.error_summary}")
            result.add_event(
                EventType.EXECUTE_COMPLETED,
                f"Q06 pre-check compile failed: {cr.error_summary}",
            )
            return True
    return False


def register_execute_handlers() -> None:
    """注册所有 execute 阶段的 handler."""
    register_pre_check("Q06", _q06_compile_precheck)
    register_handler(
        "persist_inputs",
        handle_persist_inputs,
        stage="execute",
        order=-1,
    )
    register_handler(
        "language_detect",
        handle_language_detect,
        stage="execute",
        order=0,
    )
    register_handler(
        "upstream_quality",
        handle_upstream_quality,
        stage="execute",
        order=2,
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
        phases={"Q05a", "Q05b", "Q06"},
        order=50,
        depends_on=["diff_context"],
    )
    register_handler(
        "jacoco_report",
        handle_jacoco_report,
        stage="execute",
        phases={"Q06"},
        order=45,
    )
    register_handler(
        "data_patterns",
        handle_data_patterns,
        stage="execute",
        phases={"Q05a", "Q05b", "Q06"},
        order=60,
    )
    register_handler(
        "se_code_mapping",
        handle_se_code_mapping,
        stage="execute",
        phases={"Q02", "Q05a", "Q05b", "Q06", "Q07"},
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
