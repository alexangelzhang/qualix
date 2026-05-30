"""Phase C 弱断言检测 sidecar：基于 diff 测试文件的静态分析.

优先使用 tree-sitter Java AST 解析（精确），不可用时降级到正则匹配。
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from qualix.json_utils import save_json
from qualix.log import get_logger

from .weak_assert_analysis import (
    analyze_test_method,
    analyze_with_ast,
    extract_test_methods_regex,
    is_ast_available,
)

log = get_logger(__name__)

# 尝试导入语义映射（可选）
with contextlib.suppress(ImportError):
    from .assert_semantic_mapper import (
        load_eut_from_phase_b,
        load_se_from_phase_a,
        map_asserts_to_semantics,
    )


def collect_weak_assert_context(
    repo_path: str | Path,
    diff_ctx: Any,
    output_dir: str | Path | None = None,
    project_id: str | None = None,
    language_provider: Any = None,
) -> dict[str, Any]:
    """扫描 diff 中的测试文件，提取弱断言候选.

    Args:
        output_dir: Qualix 产物目录（用于加载 SE/EUT 做语义映射，可选）
        project_id: 项目 ID（用于加载 SE/EUT，可选）
        language_provider: LanguageProvider 实例（可选，优先使用）
    """
    repo = Path(repo_path).expanduser()
    requested_files = list(dict.fromkeys(getattr(diff_ctx, "test_files", lambda: [])()))

    payload: dict[str, Any] = {
        "repo_path": str(repo_path),
        "diff_summary": getattr(diff_ctx, "summary", ""),
        "generated_from": "diff_test_files",
        "summary": {
            "requested_test_file_count": len(requested_files),
            "scanned_test_file_count": 0,
            "test_method_count": 0,
            "weak_method_count": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
        },
        "notes": [],
        "files": [],
    }

    if getattr(diff_ctx, "error", ""):
        payload["notes"].append(f"diff context error: {diff_ctx.error}")

    if not requested_files:
        payload["notes"].append("diff 中未检测到测试文件，未执行弱断言扫描。")
        return payload

    if not repo.exists() or not repo.is_dir():
        payload["notes"].append("code_repo 不是可读取的本地目录，弱断言扫描已跳过。")
        return payload

    def _analyze_one_file(rel_path: str) -> tuple[str, dict[str, Any] | None, str | None]:
        """分析单个测试文件，返回 (rel_path, file_result, note)."""
        file_path = repo / rel_path
        if not file_path.exists() or not file_path.is_file():
            return rel_path, None, f"测试文件不存在，已跳过: {rel_path}"

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Failed to read weak assert candidate file %s: %s", file_path, exc)
            return rel_path, None, f"测试文件读取失败，已跳过: {rel_path}"

        # Provider 优先路径
        if language_provider is not None:
            weak_results = language_provider.analyze_weak_asserts(content)
            analyzed_methods = [
                {
                    "method_name": r.method_name,
                    "line_start": r.line_start,
                    "line_end": r.line_end,
                    "risk_level": r.risk_level,
                    "signals": [{"code": s.code, "severity": s.severity, "reason": s.reason} for s in r.signals],
                    "evidence": r.evidence,
                    "suggestion": r.suggestion,
                }
                for r in weak_results
            ]
            # weak_results 已经只包含有 signal 的方法
            weak_methods = analyzed_methods
        elif is_ast_available():
            analyzed_methods = analyze_with_ast(content)
            weak_methods = [method for method in analyzed_methods if method["signals"]]
        else:
            methods = extract_test_methods_regex(content)
            analyzed_methods = [analyze_test_method(method) for method in methods]
            weak_methods = [method for method in analyzed_methods if method["signals"]]

        file_result = {
            "path": rel_path,
            "test_method_count": len(analyzed_methods),
            "weak_method_count": len(weak_methods),
            "methods": weak_methods,
            "all_method_count": len(analyzed_methods),
            "high_risk_count": sum(1 for m in weak_methods if m["risk_level"] == "high"),
            "medium_risk_count": sum(1 for m in weak_methods if m["risk_level"] == "medium"),
        }
        return rel_path, file_result, None

    # 并行分析所有测试文件
    from concurrent.futures import ThreadPoolExecutor

    if not payload.get("analysis_mode"):
        if language_provider is not None:
            payload["analysis_mode"] = f"provider-{language_provider.language_id}"
        elif is_ast_available():
            payload["analysis_mode"] = "tree-sitter-java"
        else:
            payload["analysis_mode"] = "regex-fallback"

    with ThreadPoolExecutor(max_workers=min(len(requested_files), 4)) as pool:
        results = list(pool.map(_analyze_one_file, requested_files))

    for _rel_path, file_result, note in results:
        if note:
            payload["notes"].append(note)
        if file_result:
            payload["summary"]["scanned_test_file_count"] += 1
            payload["summary"]["test_method_count"] += file_result["all_method_count"]
            payload["summary"]["weak_method_count"] += file_result["weak_method_count"]
            payload["summary"]["high_risk_count"] += file_result["high_risk_count"]
            payload["summary"]["medium_risk_count"] += file_result["medium_risk_count"]
            payload["files"].append(
                {
                    "path": file_result["path"],
                    "test_method_count": file_result["test_method_count"],
                    "weak_method_count": file_result["weak_method_count"],
                    "methods": file_result["methods"],
                }
            )

    if payload["summary"]["scanned_test_file_count"] == 0 and not payload["notes"]:
        payload["notes"].append("未扫描到可读取的 diff 测试文件。")

    # 语义映射：将弱断言与 Phase A SE / Phase B EUT 关联
    if output_dir and project_id and is_ast_available():
        try:
            se_list = load_se_from_phase_a(output_dir, project_id)
            eut_list = load_eut_from_phase_b(output_dir, project_id)
            if se_list or eut_list:
                all_methods = []
                for file_item in payload.get("files", []):
                    all_methods.extend(file_item.get("methods", []))
                if all_methods:
                    map_asserts_to_semantics(all_methods, se_list, eut_list)
                    mapped_count = sum(1 for m in all_methods if m.get("semantic_mapping", {}).get("matched_se"))
                    gap_count = sum(1 for m in all_methods if m.get("semantic_mapping", {}).get("coverage_gap"))
                    payload["summary"]["semantic_mapped_count"] = mapped_count
                    payload["summary"]["semantic_gap_count"] = gap_count
                    payload["summary"]["se_count"] = len(se_list)
                    payload["summary"]["eut_count"] = len(eut_list)
        except Exception as exc:
            log.warning("语义映射失败，不影响弱断言检测: %s", exc)

    return payload


def render_weak_assert_context_markdown(payload: dict[str, Any]) -> str:
    """将弱断言检测结果渲染为 markdown sidecar。"""
    summary = payload.get("summary", {})
    lines = [
        "# Weak Assert Context",
        "",
        "## Summary",
        f"- Diff Summary: {payload.get('diff_summary') or 'N/A'}",
        f"- Requested Test Files: {summary.get('requested_test_file_count', 0)}",
        f"- Scanned Test Files: {summary.get('scanned_test_file_count', 0)}",
        f"- Test Methods: {summary.get('test_method_count', 0)}",
        f"- Weak Methods: {summary.get('weak_method_count', 0)}",
        f"- High Risk: {summary.get('high_risk_count', 0)}",
        f"- Medium Risk: {summary.get('medium_risk_count', 0)}",
    ]

    notes = payload.get("notes", [])
    if notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in notes)

    files = payload.get("files", [])
    if not files:
        lines.extend(["", "## Findings", "（无可用测试文件或未发现弱断言候选）"])
        return "\n".join(lines) + "\n"

    lines.extend(["", "## Findings"])
    file_has_findings = False
    for file_item in files:
        methods = file_item.get("methods", [])
        if not methods:
            continue
        file_has_findings = True
        lines.extend(["", f"### {file_item.get('path', '')}"])
        for method in methods:
            signal_codes = ", ".join(signal["code"] for signal in method.get("signals", []))
            lines.append(
                f"- `{method.get('method_name', '?')}` [{method.get('risk_level', 'medium')}] "
                f"lines {method.get('line_start', 0)}-{method.get('line_end', 0)}"
            )
            lines.append(f"  - Signals: {signal_codes}")
            for evidence in method.get("evidence", [])[:3]:
                lines.append(f"  - Evidence: `{evidence}`")
            suggestion = method.get("suggestion")
            if suggestion:
                lines.append(f"  - Suggestion: {suggestion}")

    if not file_has_findings:
        lines.extend(["", "（已扫描 diff 测试文件，但未发现弱断言候选）"])

    return "\n".join(lines) + "\n"


def write_weak_assert_context(
    output_dir: Path,
    project_id: str,
    phase_dir_name: str,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    """写入弱断言 sidecar 到 phase 的 _internal 目录。"""
    internal_dir = output_dir / project_id / phase_dir_name / "_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)

    json_path = internal_dir / "_weak_assert_context.json"
    md_path = internal_dir / "_weak_assert_context.md"
    save_json(json_path, payload)
    md_path.write_text(render_weak_assert_context_markdown(payload), encoding="utf-8")
    return json_path, md_path
