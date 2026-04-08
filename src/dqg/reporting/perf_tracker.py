"""Phase 执行性能追踪.

记录每个 Phase 的 token 消耗估算、执行时间、产物大小，
输出性能报告和改进建议。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.constants import (
    PRICING_CACHE_READ_PER_M,
    PRICING_CACHE_WRITE_PER_M,
    PRICING_INPUT_PER_M,
    PRICING_OUTPUT_PER_M,
    REPORT_MAP,
    STRUCTURED_JSON_MAP,
    PERF_DURATION_WARNING,
    PERF_OUTPUT_TOKEN_WARNING,
    PERF_TOKEN_WARNING,
)
from dqg.core.model_registry import estimate_tokens
from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.path_utils import resolve_effective_context_files, resolve_internal_file
from dqg.store import insert_metric

_FILE_TOKEN_CACHE: dict[tuple[str, int, int], int] = {}


def _estimate_file_tokens(path: Path) -> int:
    """按路径 + mtime + size 缓存文件 token 估算，避免重复读取相同文件。"""
    try:
        stat = path.stat()
    except OSError:
        return 0

    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    cached = _FILE_TOKEN_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0

    tokens = estimate_tokens(text)
    _FILE_TOKEN_CACHE[key] = tokens
    return tokens


def _count_file_tokens(path: Path) -> int:
    """按文件路径复用 token 估算缓存。"""
    return _estimate_file_tokens(path)


def collect_phase_metrics(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """收集 Phase 执行的性能指标."""
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return {}

    pd = _phase_dir(output_dir, project_id, phase_def)
    if not pd.exists():
        return {}

    metrics: dict[str, Any] = {
        "project_id": project_id,
        "phase_id": phase_id,
        "timestamp": datetime.now().isoformat(),
        "duration_seconds": duration_seconds,
    }

    # 输入 token 估算
    input_tokens = 0
    input_files: dict[str, int] = {}

    # 上下文文件：兼容旧布局（phase 根目录）和新布局（_internal/、ingest/）
    context_files = resolve_effective_context_files(pd)
    context_metrics: dict[str, int] = {}
    for path in context_files:
        tokens = _count_file_tokens(path)
        context_metrics[path.name] = tokens
        input_tokens += tokens

    if "_upstream_context.md" in context_metrics:
        input_files["upstream_context"] = context_metrics["_upstream_context.md"]
    if "_profile_context.md" in context_metrics:
        input_files["profile_context"] = context_metrics["_profile_context.md"]
    if "_bug_cases.md" in context_metrics:
        input_files["bug_cases"] = context_metrics["_bug_cases.md"]
    if "_diff_context.md" in context_metrics:
        input_files["diff_context"] = context_metrics["_diff_context.md"]
    if "image_semantics.md" in context_metrics:
        input_files["image_semantics"] = context_metrics["image_semantics.md"]
    if "plain_text_summary.md" in context_metrics:
        input_files["plain_text_summary"] = context_metrics["plain_text_summary.md"]
    if "plain_text.txt" in context_metrics:
        input_files["plain_text"] = context_metrics["plain_text.txt"]

    # Skill 文件
    skill_path = Path(phase_def.get("skill", ""))
    if skill_path.exists():
        tokens = _count_file_tokens(skill_path)
        input_files["skill_prompt"] = tokens
        input_tokens += tokens

    metrics["input_tokens"] = input_tokens
    metrics["input_files"] = input_files

    # 输出 token 估算
    output_tokens = 0
    output_files: dict[str, int] = {}

    # 构建 phase 产物文件列表
    phase_output_files = []
    report_file = REPORT_MAP.get(phase_id)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if report_file:
        phase_output_files.append(report_file)
    if json_file:
        phase_output_files.append(json_file)

    for filename in phase_output_files:
        filepath = pd / filename
        if filepath.exists():
            tokens = _count_file_tokens(filepath)
            output_files[filename] = tokens
            output_tokens += tokens

    metrics["output_tokens"] = output_tokens
    metrics["output_files"] = output_files
    metrics["total_tokens"] = input_tokens + output_tokens

    # 产物文件大小：统计 phase 根目录、_internal/、ingest/ 三层，避免漏算新布局
    total_size = 0
    file_count = 0
    counted: set[Path] = set()
    for folder in (pd, pd / "_internal", pd / "ingest"):
        if not folder.exists():
            continue
        for f in folder.rglob("*"):
            if f.is_file() and not f.name.startswith(".") and f not in counted:
                counted.add(f)
                total_size += f.stat().st_size
                file_count += 1

    metrics["output_dir_size_kb"] = round(total_size / 1024, 1)
    metrics["output_file_count"] = file_count

    # 效率指标
    if duration_seconds and duration_seconds > 0:
        metrics["tokens_per_second"] = round(output_tokens / duration_seconds, 1)
        metrics["cost_estimate_usd"] = _estimate_cost(input_tokens, output_tokens)

    # 质量密度指标（每千 token 输入产出多少结构化条目）
    structured_file = _get_structured_json(pd, phase_id)
    if structured_file:
        quality = _compute_quality_density(structured_file, input_tokens)
        metrics["quality_density"] = quality

    # 重跑率（同一 Phase 被执行的次数）
    try:
        from dqg.store import query_telemetry
        runs = query_telemetry(output_dir, project_id=project_id, phase_id=phase_id, action="execute", limit=100)
        metrics["run_count"] = len(runs)
        metrics["first_pass"] = len(runs) <= 1
    except Exception:
        pass

    return metrics


def _get_structured_json(pd: Path, phase_id: str) -> dict[str, Any] | None:
    """读取 Phase 的结构化 JSON."""
    filename = STRUCTURED_JSON_MAP.get(phase_id)
    if not filename:
        return None
    path = pd / filename
    if not path.exists():
        path = resolve_internal_file(pd, filename)
    if not path.exists():
        return None
    return load_json(path)


def _compute_quality_density(structured: dict[str, Any], input_tokens: int) -> dict[str, Any]:
    """计算质量密度指标."""
    density: dict[str, Any] = {}
    per_k = max(input_tokens / 1000, 1)

    # Phase A
    reqs = structured.get("requirements", [])
    ses = structured.get("semantic_expectations", [])
    gaps = structured.get("gaps", [])
    opens = structured.get("open_items", [])

    if reqs:
        req_count = len([r for r in reqs if r.get("req_id", "").startswith("REQ-")])
        br_count = len([r for r in reqs if r.get("req_id", "").startswith("BR-")])
        density["req_per_k_tokens"] = round(req_count / per_k, 2)
        density["br_per_k_tokens"] = round(br_count / per_k, 2)
        density["total_items"] = req_count + br_count + len(ses) + len(gaps) + len(opens)

    if ses:
        density["se_per_k_tokens"] = round(len(ses) / per_k, 2)
    if gaps:
        density["gap_per_k_tokens"] = round(len(gaps) / per_k, 2)

    # Phase A.5
    for key in ("req_coverage", "br_coverage", "se_coverage"):
        items = structured.get(key, [])
        if items:
            covered = len([i for i in items if i.get("status") in ("COVERED", "covered")])
            density[f"{key}_rate"] = round(covered / max(len(items), 1), 2)

    # Phase C
    audit_items = structured.get("audit_items", [])
    if audit_items:
        covered = len([i for i in audit_items if i.get("status") == "COVERED"])
        wrong = len([i for i in audit_items if i.get("status") == "WRONG_TARGET"])
        density["audit_covered_rate"] = round(covered / max(len(audit_items), 1), 2)
        density["wrong_target_rate"] = round(wrong / max(len(audit_items), 1), 2)

    return density


def _estimate_cost(input_tokens: int, output_tokens: int, cache_creation_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    """粗略估算 API 成本（基于 Claude Opus 4 及其缓存定价体系估算）."""
    base_input = max(0, input_tokens - cache_creation_tokens - cache_read_tokens)

    base_input_cost = base_input * PRICING_INPUT_PER_M / 1_000_000
    cache_write_cost = cache_creation_tokens * PRICING_CACHE_WRITE_PER_M / 1_000_000
    cache_read_cost = cache_read_tokens * PRICING_CACHE_READ_PER_M / 1_000_000

    input_cost = base_input_cost + cache_write_cost + cache_read_cost
    output_cost = output_tokens * PRICING_OUTPUT_PER_M / 1_000_000
    return round(input_cost + output_cost, 4)


def persist_phase_metrics(output_dir: Path, metrics: dict[str, Any]) -> None:
    """将性能指标持久化到 SQLite."""
    for key in ("input_tokens", "output_tokens", "total_tokens",
                "tokens_per_second", "cost_estimate_usd",
                "output_dir_size_kb", "output_file_count"):
        value = metrics.get(key)
        if value is not None:
            insert_metric(output_dir, {
                "project_id": metrics.get("project_id", ""),
                "phase_id": metrics.get("phase_id", ""),
                "metric_name": key,
                "metric_value": value,
                "period": "phase_run",
                "timestamp": metrics.get("timestamp", datetime.now().isoformat()),
            })


def generate_improvement_suggestions(metrics: dict[str, Any]) -> list[str]:
    """根据性能指标生成改进建议."""
    suggestions: list[str] = []

    input_tokens = metrics.get("input_tokens", 0)
    output_tokens = metrics.get("output_tokens", 0)
    total = metrics.get("total_tokens", 0)
    duration = metrics.get("duration_seconds", 0)
    input_files = metrics.get("input_files", {})

    # Token 消耗分析
    if total > PERF_TOKEN_WARNING:
        suggestions.append(f"总 token 消耗较高 ({total:,})，建议检查输入是否可以精简")

    # 输入占比分析
    if input_tokens > 0:
        upstream = input_files.get("upstream_context", 0)
        if upstream > input_tokens * 0.6:
            suggestions.append(
                f"上游产物占输入 token 的 {upstream/input_tokens:.0%}，"
                "建议使用摘要模式或增量加载减少 token"
            )

        bug_cases = input_files.get("bug_cases", 0)
        if bug_cases > input_tokens * 0.3:
            suggestions.append(
                f"Bug 案例注入占输入 token 的 {bug_cases/input_tokens:.0%}，"
                "建议提高相关性匹配阈值减少注入数量"
            )

    # 执行时间分析
    if duration and duration > PERF_DURATION_WARNING:
        suggestions.append(f"执行时间 {duration:.0f}s (>{PERF_DURATION_WARNING}s)，建议拆分为更小的子任务")

    # 成本分析
    cost = metrics.get("cost_estimate_usd", 0)
    if cost > 1.0:
        suggestions.append(f"预估成本 ${cost:.2f}，建议考虑使用更小的模型或减少输入")

    # 输出质量信号
    if output_tokens < PERF_OUTPUT_TOKEN_WARNING and input_tokens > 10_000:
        suggestions.append("输出 token 远小于输入，可能存在内容丢失，建议检查输出完整性")

    if not suggestions:
        suggestions.append("性能指标正常，无需特别优化")

    return suggestions


def format_metrics_report(metrics: dict[str, Any]) -> str:
    """格式化性能报告."""
    lines = [
        f"Phase {metrics.get('phase_id', '?')} 性能报告 — {metrics.get('project_id', '?')}",
        "",
    ]

    # Token 消耗
    input_t = metrics.get("input_tokens", 0)
    output_t = metrics.get("output_tokens", 0)
    total_t = metrics.get("total_tokens", 0)
    lines.append(f"  Token 消耗: {total_t:,} (输入 {input_t:,} + 输出 {output_t:,})")

    # 输入明细
    input_files = metrics.get("input_files", {})
    if input_files:
        lines.append("  输入明细:")
        for name, tokens in sorted(input_files.items(), key=lambda x: -x[1]):
            pct = tokens / max(input_t, 1) * 100
            lines.append(f"    {name}: {tokens:,} ({pct:.0f}%)")

    # 输出明细
    output_files = metrics.get("output_files", {})
    if output_files:
        lines.append("  输出明细:")
        for name, tokens in sorted(output_files.items(), key=lambda x: -x[1]):
            lines.append(f"    {name}: {tokens:,}")

    # 执行时间
    duration = metrics.get("duration_seconds")
    if duration:
        lines.append(f"  执行时间: {duration:.0f}s")
        tps = metrics.get("tokens_per_second")
        if tps:
            lines.append(f"  输出速度: {tps:.1f} tokens/s")

    # 成本
    cost = metrics.get("cost_estimate_usd")
    if cost:
        lines.append(f"  预估成本: ${cost:.4f}")

    # 产物大小
    size = metrics.get("output_dir_size_kb")
    count = metrics.get("output_file_count")
    if size:
        lines.append(f"  产物大小: {size:.1f} KB ({count} 个文件)")

    # 改进建议
    suggestions = generate_improvement_suggestions(metrics)
    if suggestions:
        lines.append("")
        lines.append("  改进建议:")
        for s in suggestions:
            lines.append(f"    - {s}")

    return "\n".join(lines)
