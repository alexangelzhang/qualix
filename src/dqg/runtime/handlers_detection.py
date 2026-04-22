"""异构检测层 finalize handlers：弱断言 gate / Mock 巧合正确 / AI 产出标记."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from dqg.json_utils import save_json
from dqg.runtime.events import EventType

if TYPE_CHECKING:
    from pathlib import Path

    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


def _async_write_json(path: Path, data: object) -> None:
    from dqg.log import get_logger
    _log = get_logger(__name__)

    def _write():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_json(path, data)
        except Exception:
            _log.debug("_async_write_json failed: %s", path, exc_info=True)
    threading.Thread(target=_write, daemon=True).start()


def _emit_handler(ctx, event_type: EventType, message: str = "", **data) -> None:
    try:
        from dqg.store.events import insert_event
        insert_event(ctx.output_dir, ctx.project_id, ctx.phase_id,
                     event_type.value, action="finalize", message=message, data=data if data else None)
    except Exception:
        from dqg.log import get_logger
        get_logger(__name__).debug(
            "_emit_handler failed: %s/%s event=%s",
            ctx.project_id, ctx.phase_id, event_type.value, exc_info=True,
        )


def handle_weak_assert_gate(ctx: ExecutionContext, result: PhaseResult) -> None:
    """弱断言 gate 阻断：读取 execute 阶段的 _weak_assert_context.json，超阈值时 WARNING."""
    from dqg.constants import WEAK_ASSERT_HIGH_RISK_WARN, WEAK_ASSERT_RATIO_WARN
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

    issues: list[str] = []
    if high_risk >= WEAK_ASSERT_HIGH_RISK_WARN:
        issues.append(f"high-risk 弱断言 {high_risk} 个（阈值 {WEAK_ASSERT_HIGH_RISK_WARN}）")
    if weak_ratio >= WEAK_ASSERT_RATIO_WARN:
        issues.append(f"弱断言比例 {weak_ratio:.0%}（阈值 {WEAK_ASSERT_RATIO_WARN:.0%}）")

    if issues:
        msg = f"弱断言检测: {'; '.join(issues)}"
        result.add_warning(msg)
        _emit_handler(ctx, EventType.WEAK_ASSERT_GATE, msg,
                      high_risk=high_risk, weak_ratio=round(weak_ratio, 2),
                      total_methods=total_methods, weak_methods=weak_methods)

    gate_result = {
        "high_risk": high_risk,
        "weak_ratio": round(weak_ratio, 3),
        "total_methods": total_methods,
        "weak_methods": weak_methods,
        "triggered": bool(issues),
        "issues": issues,
    }
    _async_write_json(ctx.internal_dir / "_weak_assert_gate.json", gate_result)


def handle_mock_coincidence_check(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Mock 巧合正确检测：检测 Mock 返回值与真实 API 行为的偏差模式."""
    import re

    from dqg.constants import MOCK_COINCIDENCE_KEYWORDS
    from dqg.text_utils import REPORT_MAP

    report_file = REPORT_MAP.get(ctx.phase_id)
    if not report_file:
        return

    report_path = ctx.phase_root / report_file
    if not report_path.exists():
        return

    report = report_path.read_text(encoding="utf-8")

    reality_kw = ["Mock 真实", "mock.*真实", "BigDecimal", "email", "RpcContext", "Mock 数据", "贴近业务"]
    reality_found = sum(1 for kw in reality_kw if kw.lower() in report.lower() or kw in report)

    coincidence_hits: list[str] = []
    for pattern in MOCK_COINCIDENCE_KEYWORDS:
        if re.search(pattern, report, re.IGNORECASE):
            coincidence_hits.append(pattern)

    has_mock = bool(re.search(r"\bmock\b", report, re.IGNORECASE))
    has_real_data = bool(re.search(r"(真实数据|生产数据|线上数据|实际.*返回|real.*data)", report, re.IGNORECASE))
    mock_without_real = has_mock and not has_real_data

    issues: list[str] = []
    if coincidence_hits:
        issues.append(f"Mock 巧合正确风险: 检测到 {len(coincidence_hits)} 个偏差模式 ({', '.join(coincidence_hits[:3])})")
    if mock_without_real:
        issues.append("Mock 覆盖但未提及真实数据验证")
    if reality_found == 0 and has_mock:
        issues.append("有 Mock 使用但未评估 Mock 数据真实性")

    if issues:
        for issue in issues:
            result.add_warning(f"Mock 检测: {issue}")
        _emit_handler(ctx, EventType.MOCK_COINCIDENCE_DETECTED,
                      f"Mock coincidence: {len(issues)} issues",
                      coincidence_hits=coincidence_hits[:5],
                      mock_without_real=mock_without_real,
                      reality_score=reality_found)

    check_result = {
        "reality_keywords_found": reality_found,
        "coincidence_hits": coincidence_hits,
        "mock_without_real_data": mock_without_real,
        "triggered": bool(issues),
        "issues": issues,
    }
    _async_write_json(ctx.internal_dir / "_mock_coincidence_check.json", check_result)


def handle_ai_origin_detection(ctx: ExecutionContext, result: PhaseResult) -> None:
    """AI 产出标记检测：通过 git blame + Co-Authored-By 推断代码来源."""
    import re
    import subprocess
    from pathlib import Path

    from dqg.constants import AI_ORIGIN_CO_AUTHOR_PATTERNS

    code_repo = ctx.code_repo
    if not code_repo:
        return

    repo_path = Path(code_repo)
    if not repo_path.exists():
        return

    try:
        git_log = subprocess.run(
            ["git", "log", "--format=%b", "-50"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=10,
        )
        log_text = git_log.stdout if git_log.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        log_text = ""

    ai_commits = 0
    for pattern in AI_ORIGIN_CO_AUTHOR_PATTERNS:
        ai_commits += len(re.findall(pattern, log_text, re.IGNORECASE))

    diff_ctx = ctx.shared.get("diff_context")
    ai_files: list[str] = []
    if diff_ctx:
        changed_files = getattr(diff_ctx, "changed_files", lambda: [])()
        for f in changed_files:
            file_path = repo_path / f
            if not file_path.exists():
                continue
            try:
                blame = subprocess.run(
                    ["git", "blame", "--porcelain", "-L", "1,5", str(f)],
                    cwd=str(repo_path), capture_output=True, text=True, timeout=10,
                )
                if blame.returncode == 0:
                    for pattern in AI_ORIGIN_CO_AUTHOR_PATTERNS:
                        if re.search(pattern, blame.stdout, re.IGNORECASE):
                            ai_files.append(f)
                            break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    if ai_commits > 0 or ai_files:
        msg = f"AI 产出检测: {ai_commits} 个 AI co-authored commits"
        if ai_files:
            msg += f", {len(ai_files)} 个 AI 生成文件"
        result.add_event(EventType.AI_ORIGIN_DETECTED, msg,
                         ai_commits=ai_commits, ai_files=ai_files[:10])

    detection_result = {
        "ai_commits": ai_commits,
        "ai_files": ai_files,
        "total_checked_files": len(getattr(diff_ctx, "changed_files", lambda: [])()) if diff_ctx else 0,
        "detected": ai_commits > 0 or bool(ai_files),
    }
    _async_write_json(ctx.internal_dir / "_ai_origin_detection.json", detection_result)
