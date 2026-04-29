"""异构检测层 finalize handlers：弱断言 gate / Mock 巧合正确 / AI 产出标记 / 覆盖超集."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.runtime.events import EventType
from dqg.runtime.handler_utils import async_write_json as _async_write_json
from dqg.runtime.handler_utils import emit_handler_event as _emit_handler

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


def handle_weak_assert_gate(ctx: ExecutionContext, result: PhaseResult) -> None:
    """弱断言 gate 阻断：读取 _weak_assert_context.json，Q05 high-risk 触发 BLOCKED，Q06 触发 WARNING."""
    from dqg.constants import (
        WEAK_ASSERT_HIGH_RISK_BLOCK,
        WEAK_ASSERT_HIGH_RISK_WARN,
        WEAK_ASSERT_RATIO_WARN,
    )
    from dqg.json_utils import load_json

    json_path = ctx.internal_dir / "_weak_assert_context.json"
    if not json_path.exists():
        return

    payload = load_json(json_path)
    if not payload:
        return

    summary = payload.get("summary", {})
    high_risk = summary.get("high_risk_count", 0)
    total_methods = summary.get("test_method_count", 0)
    weak_methods = summary.get("weak_method_count", 0)
    weak_ratio = weak_methods / total_methods if total_methods > 0 else 0.0

    is_q05 = ctx.phase_id == "Q05"
    issues: list[str] = []
    blocked = False

    # Q05: high-risk 弱断言直接 BLOCKED（左移卡控）
    if is_q05 and high_risk >= WEAK_ASSERT_HIGH_RISK_BLOCK:
        issues.append(f"high-risk 弱断言 {high_risk} 个（BLOCKED 阈值 {WEAK_ASSERT_HIGH_RISK_BLOCK}）")
        blocked = True

    # Q06 / 通用: WARNING 级别
    if high_risk >= WEAK_ASSERT_HIGH_RISK_WARN:
        issues.append(f"high-risk 弱断言 {high_risk} 个（WARNING 阈值 {WEAK_ASSERT_HIGH_RISK_WARN}）")
    if weak_ratio >= WEAK_ASSERT_RATIO_WARN:
        issues.append(f"弱断言比例 {weak_ratio:.0%}（WARNING 阈值 {WEAK_ASSERT_RATIO_WARN:.0%}）")

    if issues:
        msg = f"弱断言检测: {'; '.join(issues)}"
        if blocked:
            result.add_error(f"BLOCKED: {msg}")
        else:
            result.add_warning(msg)
        _emit_handler(
            ctx,
            EventType.WEAK_ASSERT_GATE,
            msg,
            high_risk=high_risk,
            weak_ratio=round(weak_ratio, 2),
            total_methods=total_methods,
            weak_methods=weak_methods,
            blocked=blocked,
        )

    gate_result = {
        "high_risk": high_risk,
        "weak_ratio": round(weak_ratio, 3),
        "total_methods": total_methods,
        "weak_methods": weak_methods,
        "triggered": bool(issues),
        "blocked": blocked,
        "issues": issues,
    }
    _async_write_json(ctx.internal_dir / "_weak_assert_gate.json", gate_result)


def _collect_test_code_text(phase_root) -> str:
    """收集 Q05 supplemental_tests 目录下的测试代码文本."""
    from pathlib import Path

    test_dir = Path(phase_root) / "supplemental_tests"
    if not test_dir.exists():
        return ""
    parts: list[str] = []
    for f in sorted(test_dir.iterdir()):
        if f.is_file() and f.suffix in (".patch", ".java", ".kt", ".go", ".py"):
            parts.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def handle_mock_coincidence_check(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Mock 巧合正确检测：检测 Mock 返回值与真实 API 行为的偏差模式."""
    import re

    from dqg.constants import MOCK_COINCIDENCE_KEYWORDS, MOCK_REALITY_KEYWORDS
    from dqg.text_utils import REPORT_MAP

    is_q05 = ctx.phase_id == "Q05"

    if is_q05:
        report = _collect_test_code_text(ctx.phase_root)
        if not report:
            return
    else:
        report_file = REPORT_MAP.get(ctx.phase_id)
        if not report_file:
            return
        report_path = ctx.phase_root / report_file
        if not report_path.exists():
            return
        report = report_path.read_text(encoding="utf-8")

    reality_found = sum(1 for kw in MOCK_REALITY_KEYWORDS if kw.lower() in report.lower() or kw in report)

    coincidence_hits: list[str] = []
    for pattern in MOCK_COINCIDENCE_KEYWORDS:
        if re.search(pattern, report, re.IGNORECASE):
            coincidence_hits.append(pattern)

    has_mock = bool(re.search(r"\bmock\b", report, re.IGNORECASE))
    has_real_data = bool(re.search(r"(真实数据|生产数据|线上数据|实际.*返回|real.*data)", report, re.IGNORECASE))
    mock_without_real = has_mock and not has_real_data

    issues: list[str] = []
    blocked = False

    if coincidence_hits:
        issues.append(
            f"Mock 巧合正确风险: 检测到 {len(coincidence_hits)} 个偏差模式 ({', '.join(coincidence_hits[:3])})"
        )
        if is_q05:
            blocked = True
    if mock_without_real:
        issues.append("Mock 覆盖但未提及真实数据验证")
    if reality_found == 0 and has_mock:
        issues.append("有 Mock 使用但未评估 Mock 数据真实性")

    if issues:
        for issue in issues:
            if blocked:
                result.add_error(f"BLOCKED: Mock 检测: {issue}")
            else:
                result.add_warning(f"Mock 检测: {issue}")
        _emit_handler(
            ctx,
            EventType.MOCK_COINCIDENCE_DETECTED,
            f"Mock coincidence: {len(issues)} issues",
            coincidence_hits=coincidence_hits[:5],
            mock_without_real=mock_without_real,
            reality_score=reality_found,
            blocked=blocked,
        )

    check_result = {
        "reality_keywords_found": reality_found,
        "coincidence_hits": coincidence_hits,
        "mock_without_real_data": mock_without_real,
        "triggered": bool(issues),
        "blocked": blocked,
        "issues": issues,
    }
    _async_write_json(ctx.internal_dir / "_mock_coincidence_check.json", check_result)


def handle_weak_assert_scan_q05(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Q05 finalize: 扫描生成的测试文件，产出 _weak_assert_context.json 供 weak_assert_gate 消费（支持多 repo）."""
    from pathlib import Path

    from dqg.context.weak_assert_context import (
        collect_weak_assert_context,
        write_weak_assert_context,
    )
    from dqg.json_utils import load_json

    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    # 从 phase_b_structured.json 提取测试文件路径
    structured_path = ctx.phase_root / "phase_b_structured.json"
    if not structured_path.exists():
        return

    structured = load_json(structured_path)
    if not structured:
        return

    # 从 TCItem.covered_by (格式 TestClass#testMethod) 提取类名，搜索文件
    test_classes: set[str] = set()
    for tc in structured.get("test_cases", []):
        covered_by = tc.get("covered_by", "")
        if "#" in covered_by:
            class_name = covered_by.split("#")[0].strip()
            if class_name:
                test_classes.add(class_name)

    if not test_classes:
        return

    # 在所有 code_repos 中搜索测试文件
    test_files: list[str] = []
    primary_repo = None
    for repo_path in repos:
        repo = Path(repo_path).resolve()
        if not repo.exists():
            continue
        if primary_repo is None:
            primary_repo = repo_path
        for cls in test_classes:
            for suffix in (".java", ".kt"):
                matches = list(repo.rglob(f"{cls}{suffix}"))
                for m in matches:
                    rel = str(m.relative_to(repo))
                    if rel not in test_files:
                        test_files.append(rel)

    if not test_files or not primary_repo:
        return

    # 构造轻量 diff_ctx 替身，只提供 test_files 列表
    class _Q05DiffProxy:
        def __init__(self, files: list[str]) -> None:
            self._files = files
            self.summary = "Q05 generated test files"
            self.error = ""

        def test_files(self) -> list[str]:
            return self._files

    provider = ctx.shared.get("language_provider")
    payload = collect_weak_assert_context(
        primary_repo,
        _Q05DiffProxy(test_files),
        output_dir=ctx.output_dir,
        project_id=ctx.project_id,
        language_provider=provider,
    )
    write_weak_assert_context(
        ctx.output_dir,
        ctx.project_id,
        ctx.phase_def["dir_suffix"],
        payload,
    )


def handle_ai_origin_detection(ctx: ExecutionContext, result: PhaseResult) -> None:
    """AI 产出标记检测：通过 git blame + Co-Authored-By 推断代码来源（支持多 repo）."""
    import re
    import subprocess
    from pathlib import Path

    from dqg.constants import AI_ORIGIN_CO_AUTHOR_PATTERNS

    repos = ctx.code_repos or ([ctx.code_repo] if ctx.code_repo else [])
    if not repos:
        return

    total_ai_commits = 0
    all_ai_files: list[str] = []
    total_checked = 0

    for code_repo in repos:
        repo_path = Path(code_repo)
        if not repo_path.exists():
            continue

        try:
            git_log = subprocess.run(
                ["git", "log", "--format=%b", "-50"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            log_text = git_log.stdout if git_log.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            log_text = ""

        for pattern in AI_ORIGIN_CO_AUTHOR_PATTERNS:
            total_ai_commits += len(re.findall(pattern, log_text, re.IGNORECASE))

        diff_ctx = ctx.shared.get("diff_context")
        changed_files = getattr(diff_ctx, "changed_files", lambda: [])() if diff_ctx else []
        total_checked += len(changed_files)
        if diff_ctx:
            for f in changed_files:
                file_path = repo_path / f
                if not file_path.exists():
                    continue
                try:
                    blame = subprocess.run(
                        ["git", "blame", "--porcelain", "-L", "1,5", str(f)],
                        cwd=str(repo_path),
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if blame.returncode == 0:
                        for pattern in AI_ORIGIN_CO_AUTHOR_PATTERNS:
                            if re.search(pattern, blame.stdout, re.IGNORECASE):
                                all_ai_files.append(f)
                                break
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

    if total_ai_commits > 0 or all_ai_files:
        msg = f"AI 产出检测: {total_ai_commits} 个 AI co-authored commits"
        if all_ai_files:
            msg += f", {len(all_ai_files)} 个 AI 生成文件"
        result.add_event(EventType.AI_ORIGIN_DETECTED, msg, ai_commits=total_ai_commits, ai_files=all_ai_files[:10])

    detection_result = {
        "ai_commits": total_ai_commits,
        "ai_files": all_ai_files,
        "total_checked_files": total_checked,
        "detected": total_ai_commits > 0 or bool(all_ai_files),
    }
    _async_write_json(ctx.internal_dir / "_ai_origin_detection.json", detection_result)


def register_detection_handlers() -> None:
    """注册异构检测层的 finalize handler."""
    from dqg.runtime.lifecycle import register_handler

    register_handler(
        "weak_assert_scan_q05",
        handle_weak_assert_scan_q05,
        stage="finalize",
        phases={"Q05"},
        order=55,
    )
    register_handler(
        "weak_assert_gate",
        handle_weak_assert_gate,
        stage="finalize",
        phases={"Q05", "Q06"},
        order=56,
        depends_on=["weak_assert_scan_q05"],
    )
    register_handler(
        "mock_coincidence_check",
        handle_mock_coincidence_check,
        stage="finalize",
        phases={"Q05", "Q06"},
        order=57,
    )
    register_handler("ai_origin_detection", handle_ai_origin_detection, stage="finalize", order=58)

    from dqg.runtime.handlers_superset import handle_superset_gate

    register_handler(
        "superset_gate",
        handle_superset_gate,
        stage="finalize",
        phases={"Q05"},
        order=59,
    )
