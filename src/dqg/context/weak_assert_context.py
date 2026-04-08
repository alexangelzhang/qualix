"""Phase C 弱断言检测 sidecar：基于 diff 测试文件的轻量静态分析。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.json_utils import save_json
from dqg.log import get_logger

log = get_logger(__name__)

_TEST_ANNOTATION_PATTERN = re.compile(
    r"^\s*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b",
    re.MULTILINE,
)
_METHOD_NAME_PATTERN = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:throws[^{]+)?\{",
    re.MULTILINE,
)
_ASSERT_NOT_NULL_PATTERN = re.compile(r"\bassertNotNull\s*\(")
_CONSTANT_BOOL_ASSERT_PATTERN = re.compile(
    r"\bassert(?:True|False)\s*\(\s*(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\)"
)
_VERIFY_PATTERN = re.compile(r"\bverify\s*\(")
_TIMES_PATTERN = re.compile(r"\btimes\s*\(")
_ASSERT_THROWS_PATTERN = re.compile(r"\bassertThrows\s*\(")
_EXCEPTION_ASSIGN_PATTERN = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*assertThrows\s*\("
)
_ASSERT_THAT_PATTERN = re.compile(r"\bassertThat\s*\(")
_NON_CONSTANT_BOOL_ASSERT_PATTERN = re.compile(
    r"\bassert(?:True|False)\s*\(\s*(?!(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\))"
)
_STRONG_ASSERT_PATTERN = re.compile(
    r"\bassert(?:Equals|NotEquals|Same|NotSame|ArrayEquals|IterableEquals|LinesMatch|Null|DoesNotThrow|All)\s*\("
)


class WeakAssertSignal:
    ASSERT_NOT_NULL_ONLY = "ASSERT_NOT_NULL_ONLY"
    CONSTANT_BOOLEAN_ASSERT = "CONSTANT_BOOLEAN_ASSERT"
    VERIFY_ONLY_NO_BUSINESS_ASSERT = "VERIFY_ONLY_NO_BUSINESS_ASSERT"
    ASSERT_THROWS_NO_EFFECT_ASSERT = "ASSERT_THROWS_NO_EFFECT_ASSERT"


def collect_weak_assert_context(repo_path: str | Path, diff_ctx: Any) -> dict[str, Any]:
    """扫描 diff 中的测试文件，提取弱断言候选。"""
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

    for rel_path in requested_files:
        file_path = repo / rel_path
        if not file_path.exists() or not file_path.is_file():
            payload["notes"].append(f"测试文件不存在，已跳过: {rel_path}")
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Failed to read weak assert candidate file %s: %s", file_path, exc)
            payload["notes"].append(f"测试文件读取失败，已跳过: {rel_path}")
            continue

        methods = _extract_test_methods(content)
        analyzed_methods = [_analyze_test_method(method) for method in methods]
        weak_methods = [method for method in analyzed_methods if method["signals"]]

        payload["summary"]["scanned_test_file_count"] += 1
        payload["summary"]["test_method_count"] += len(analyzed_methods)
        payload["summary"]["weak_method_count"] += len(weak_methods)
        payload["summary"]["high_risk_count"] += sum(
            1 for method in weak_methods if method["risk_level"] == "high"
        )
        payload["summary"]["medium_risk_count"] += sum(
            1 for method in weak_methods if method["risk_level"] == "medium"
        )

        payload["files"].append(
            {
                "path": rel_path,
                "test_method_count": len(analyzed_methods),
                "weak_method_count": len(weak_methods),
                "methods": weak_methods,
            }
        )

    if payload["summary"]["scanned_test_file_count"] == 0 and not payload["notes"]:
        payload["notes"].append("未扫描到可读取的 diff 测试文件。")

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
            signal_codes = ", ".join(
                signal["code"] for signal in method.get("signals", [])
            )
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


def _extract_test_methods(content: str) -> list[dict[str, Any]]:
    lines = content.splitlines()
    methods: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        if not _TEST_ANNOTATION_PATTERN.match(lines[index]):
            index += 1
            continue

        annotation_start = index
        search_index = index + 1
        while search_index < len(lines):
            stripped = lines[search_index].strip()
            if not stripped or stripped.startswith("@"):
                search_index += 1
                continue
            break

        signature_lines: list[str] = []
        while search_index < len(lines):
            signature_lines.append(lines[search_index])
            if "{" in lines[search_index]:
                break
            search_index += 1

        if search_index >= len(lines):
            break

        signature_text = "\n".join(signature_lines)
        match = _METHOD_NAME_PATTERN.search(signature_text)
        if not match:
            index = search_index + 1
            continue

        method_name = match.group("name")
        brace_depth = lines[search_index].count("{") - lines[search_index].count("}")
        body_end = search_index
        while body_end + 1 < len(lines) and brace_depth > 0:
            body_end += 1
            brace_depth += lines[body_end].count("{") - lines[body_end].count("}")

        methods.append(
            {
                "method_name": method_name,
                "line_start": annotation_start + 1,
                "line_end": body_end + 1,
                "content": "\n".join(lines[annotation_start : body_end + 1]),
            }
        )
        index = body_end + 1

    return methods


def _analyze_test_method(method: dict[str, Any]) -> dict[str, Any]:
    content = method["content"]
    method_lines = _normalized_lines(content)
    not_null_lines = _matching_lines(method_lines, _ASSERT_NOT_NULL_PATTERN)
    constant_bool_lines = _matching_lines(method_lines, _CONSTANT_BOOL_ASSERT_PATTERN)
    verify_lines = _matching_lines(method_lines, _VERIFY_PATTERN)
    if _TIMES_PATTERN.search(content) and not verify_lines:
        verify_lines = _matching_lines(method_lines, _TIMES_PATTERN)
    strong_assert_lines = _strong_assert_lines(method_lines)

    signals: list[dict[str, str]] = []
    evidence: list[str] = []
    suggestion_parts: list[str] = []

    if (
        not_null_lines
        and not strong_assert_lines
        and not verify_lines
        and not _ASSERT_THROWS_PATTERN.search(content)
    ):
        signals.append(
            {
                "code": WeakAssertSignal.ASSERT_NOT_NULL_ONLY,
                "severity": "high",
                "reason": "仅看到 assertNotNull，未验证业务字段、状态或副作用。",
            }
        )
        evidence.extend(not_null_lines[:2])
        suggestion_parts.append("补充关键业务字段、状态迁移或副作用断言")

    if constant_bool_lines and not strong_assert_lines:
        signals.append(
            {
                "code": WeakAssertSignal.CONSTANT_BOOLEAN_ASSERT,
                "severity": "high",
                "reason": "存在常量布尔断言，未实际验证业务结果。",
            }
        )
        evidence.extend(constant_bool_lines[:2])
        suggestion_parts.append("移除常量布尔断言，改为断言真实业务表达式")

    if verify_lines and not strong_assert_lines:
        signals.append(
            {
                "code": WeakAssertSignal.VERIFY_ONLY_NO_BUSINESS_ASSERT,
                "severity": "high",
                "reason": "仅做交互校验，未看到业务结果断言。",
            }
        )
        evidence.extend(verify_lines[:2])
        suggestion_parts.append("在 verify 之外补充业务结果或副作用断言")

    if _ASSERT_THROWS_PATTERN.search(content) and _has_assert_throws_without_effect(
        content, method_lines
    ):
        signals.append(
            {
                "code": WeakAssertSignal.ASSERT_THROWS_NO_EFFECT_ASSERT,
                "severity": "medium",
                "reason": "只校验抛异常或异常对象，缺少失败后的业务效果断言。",
            }
        )
        evidence.extend(_matching_lines(method_lines, _ASSERT_THROWS_PATTERN)[:1])
        suggestion_parts.append("补充失败后的状态、数据或副作用断言")

    deduped_evidence = list(dict.fromkeys(evidence))
    suggestion = "；".join(dict.fromkeys(suggestion_parts)) if suggestion_parts else ""

    return {
        "method_name": method["method_name"],
        "line_start": method["line_start"],
        "line_end": method["line_end"],
        "risk_level": _risk_level_for_signals(signals),
        "signals": signals,
        "evidence": deduped_evidence[:4],
        "suggestion": suggestion,
    }


def _has_assert_throws_without_effect(content: str, method_lines: list[str]) -> bool:
    exception_vars = set(_EXCEPTION_ASSIGN_PATTERN.findall(content))
    business_effect_lines = []
    for line in _strong_assert_lines(method_lines):
        if exception_vars and any(
            re.search(rf"\\b{re.escape(name)}\\b", line) for name in exception_vars
        ):
            continue
        business_effect_lines.append(line)
    return not business_effect_lines


def _strong_assert_lines(method_lines: list[str]) -> list[str]:
    strong: list[str] = []
    for line in method_lines:
        if _ASSERT_NOT_NULL_PATTERN.search(line):
            continue
        if _CONSTANT_BOOL_ASSERT_PATTERN.search(line):
            continue
        if _ASSERT_THAT_PATTERN.search(line):
            strong.append(line)
            continue
        if _NON_CONSTANT_BOOL_ASSERT_PATTERN.search(line):
            strong.append(line)
            continue
        if _STRONG_ASSERT_PATTERN.search(line):
            strong.append(line)
    return strong


def _matching_lines(lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    return [line for line in lines if pattern.search(line)]


def _normalized_lines(content: str) -> list[str]:
    normalized: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue
        normalized.append(line)
    return normalized


def _risk_level_for_signals(signals: list[dict[str, str]]) -> str:
    if not signals:
        return ""
    if any(signal["severity"] == "high" for signal in signals):
        return "high"
    return "medium"
