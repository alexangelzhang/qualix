"""Bug 案例库管理：扫描、归因统计、修复路径建议."""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from dqg.constants import CASES_DIR, KNOWLEDGE_FILE_MAP, PHASE_DIR_MAP, SKILL_FILE_MAP
from dqg.json_utils import dump_json_str, load_json
from dqg.log import get_logger
from dqg.core.state_machine import PHASE_DEFS

log = get_logger(__name__)

# 从 PHASE_DEFS 动态生成，避免与 state_machine.py 重复维护
PHASE_DIRS = [v["dir_suffix"] for v in PHASE_DEFS.values()]

ROOT_CAUSE_FIX_MAP: Final = MappingProxyType({
    "SKILL_RULE": MappingProxyType({
        "action": "修改 skill prompt 规则",
        "targets": SKILL_FILE_MAP,
    }),
    "KNOWLEDGE": MappingProxyType({
        "action": "补充领域知识",
        "targets": KNOWLEDGE_FILE_MAP,
    }),
    "CONTEXT": MappingProxyType({
        "action": "改进输入解析",
        "targets": MappingProxyType({
            "Q01": "src/dqg/ingest/feishu/",
            "Q04": "src/dqg/context_loader.py",
            "Q03": "src/dqg/context_loader.py",
            "Q06": "src/dqg/context_loader.py",
        }),
    }),
    "SCHEMA": MappingProxyType({
        "action": "修改结构化输出 schema",
        "targets": MappingProxyType({
            "Q01": "src/dqg/schemas/phase_a.py",
            "Q04": "src/dqg/schemas/phase_a5.py",
            "Q03": "src/dqg/schemas/phase_a6.py",
            "Q06": "src/dqg/schemas/phase_c.py",
        }),
    }),
})


def load_cases(base_dir: Path | None = None, *, exclude_holdout: bool = False, holdout_only: bool = False) -> list[dict[str, Any]]:
    """加载所有 bug 案例.

    Args:
        exclude_holdout: 排除 holdout 案例（用于训练/规则生成）
        holdout_only: 只加载 holdout 案例（用于验证）
    """
    root = base_dir or Path(CASES_DIR)
    cases: list[dict[str, Any]] = []
    for phase_dir in PHASE_DIRS:
        phase_path = root / phase_dir
        if not phase_path.is_dir():
            continue
        for case_dir in sorted(phase_path.iterdir()):
            data = _load_case(case_dir)
            if data is not None:
                cases.append(data)
    if exclude_holdout:
        cases = [c for c in cases if not c.get("holdout", False)]
    elif holdout_only:
        cases = [c for c in cases if c.get("holdout", False)]
    return cases


@lru_cache(maxsize=16)
def _load_cases_by_phase_cached(phase: str, base_dir_str: str, exclude_holdout: bool, holdout_only: bool) -> tuple[dict[str, Any], ...]:
    """缓存版本：返回 tuple 以支持 lru_cache hashable 要求."""
    root = Path(base_dir_str)
    dir_suffix = PHASE_DIR_MAP.get(phase)
    if not dir_suffix:
        cases = [c for c in load_cases(root) if c.get("phase") == phase]
    else:
        phase_path = root / dir_suffix
        if not phase_path.is_dir():
            return ()
        cases = []
        for case_dir in sorted(phase_path.iterdir()):
            data = _load_case(case_dir)
            if data is not None:
                cases.append(data)

    if exclude_holdout:
        cases = [c for c in cases if not c.get("holdout", False)]
    elif holdout_only:
        cases = [c for c in cases if c.get("holdout", False)]
    return tuple(cases)


def load_cases_by_phase(phase: str, base_dir: Path | None = None, *, exclude_holdout: bool = False, holdout_only: bool = False) -> list[dict[str, Any]]:
    """加载指定 Phase 的 bug 案例（带缓存）.

    Args:
        exclude_holdout: 排除 holdout 案例（用于训练/规则生成）
        holdout_only: 只加载 holdout 案例（用于验证）
    """
    root = base_dir or Path(CASES_DIR)
    return list(_load_cases_by_phase_cached(phase, str(root), exclude_holdout, holdout_only))


def _load_case(case_dir: Path) -> dict[str, Any] | None:
    """加载单个案例目录，并预载常用元信息。"""
    if not case_dir.is_dir():
        return None

    case_file = case_dir / "case.json"
    if not case_file.exists():
        return None

    data = load_json(case_file)
    if data is None:
        return None

    input_path = case_dir / "input.md"
    data["_dir"] = str(case_dir)
    data["_has_input"] = input_path.exists()
    data["_input_excerpt"] = _load_input_excerpt(input_path)
    return data


def _load_input_excerpt(input_path: Path, limit: int = 500) -> str:
    """读取 input.md 摘要，供 prompt 注入和相关性计算复用。"""
    if not input_path.exists():
        return ""

    try:
        input_text = input_path.read_text(encoding="utf-8").strip()
    except OSError:
        log.warning("Failed to read bug case input: %s", input_path)
        return ""

    if len(input_text) > limit:
        return input_text[:limit] + "\n...(截断)"
    return input_text


def render_cases_for_prompt(phase: str, base_dir: Path | None = None, max_cases: int = 10) -> str:
    """将指定 Phase 的 open bug 案例渲染为 markdown，用于注入 skill prompt.

    只包含 open 状态的案例，按 severity 排序（critical > high > medium > low）。
    """
    cases = [c for c in load_cases_by_phase(phase, base_dir) if c.get("status") == "open"]
    if not cases:
        return ""

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    cases.sort(key=lambda c: severity_order.get(c.get("severity", "low"), 9))
    cases = cases[:max_cases]

    lines = [
        "## BUG_CASES — 已知判错案例（务必避免重犯）",
        "",
        f"以下是 Phase {phase} 历史上出现过的判错案例。执行时请特别注意避免同类错误。",
        "",
    ]

    for i, c in enumerate(cases, 1):
        error_label = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(c.get("error_type", ""), c.get("error_type", ""))
        lines.append(f"### 反例 {i}: {c.get('title', '')} [{error_label}]")
        lines.append("")

        input_text = c.get("_input_excerpt", "")
        if input_text:
            lines.append(input_text)
            lines.append("")

        lesson = c.get("lesson", "")
        if lesson:
            lines.append(f"**教训**: {lesson}")
            lines.append("")

    return "\n".join(lines)


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """按 Phase、error_type、root_cause 汇总."""
    by_phase: dict[str, list] = defaultdict(list)
    by_error_type: dict[str, int] = defaultdict(int)
    by_root_cause: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    open_count = 0
    fixed_count = 0

    for c in cases:
        phase = c.get("phase", "?")
        by_phase[phase].append(c)
        by_error_type[c.get("error_type", "?")] += 1
        by_root_cause[c.get("root_cause", "?")] += 1
        by_severity[c.get("severity", "?")] += 1
        if c.get("status") == "open":
            open_count += 1
        elif c.get("status") == "fixed":
            fixed_count += 1

    return {
        "total": len(cases),
        "open": open_count,
        "fixed": fixed_count,
        "by_phase": {k: len(v) for k, v in by_phase.items()},
        "by_error_type": dict(by_error_type),
        "by_root_cause": dict(by_root_cause),
        "by_severity": dict(by_severity),
    }


def suggest_fixes(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """根据 open 案例的归因，生成修复建议."""
    open_cases = [c for c in cases if c.get("status") == "open"]
    if not open_cases:
        return []

    # 按 fix_target 聚合
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in open_cases:
        target = c.get("fix_target", "")
        if not target:
            root_cause = c.get("root_cause", "")
            phase = c.get("phase", "")
            mapping = ROOT_CAUSE_FIX_MAP.get(root_cause, {})
            target = mapping.get("targets", {}).get(phase, f"unknown ({root_cause}/{phase})")
        by_target[target].append(c)

    suggestions: list[dict[str, Any]] = []
    for target, target_cases in sorted(by_target.items(), key=lambda x: -len(x[1])):
        root_causes = list({c.get("root_cause", "") for c in target_cases})
        action = ROOT_CAUSE_FIX_MAP.get(root_causes[0], {}).get("action", "排查修复") if len(root_causes) == 1 else "综合排查"
        suggestions.append({
            "fix_target": target,
            "action": action,
            "case_count": len(target_cases),
            "cases": [
                {
                    "case_id": c.get("case_id"),
                    "title": c.get("title"),
                    "error_type": c.get("error_type"),
                    "severity": c.get("severity"),
                    "lesson": c.get("lesson", ""),
                }
                for c in target_cases
            ],
        })
    return suggestions


def format_report(cases: list[dict[str, Any]]) -> str:
    """生成可读的案例库报告."""
    summary = summarize_cases(cases)
    fixes = suggest_fixes(cases)

    lines = [
        "# Bug 案例库报告",
        "",
        f"总计: {summary['total']} 个案例, {summary['open']} open, {summary['fixed']} fixed",
        "",
        "## 按 Phase 分布",
    ]
    for phase, count in sorted(summary["by_phase"].items()):
        lines.append(f"  - Phase {phase}: {count}")

    lines.extend(["", "## 按错误类型"])
    for et, count in sorted(summary["by_error_type"].items()):
        label = {"FN": "漏报", "FP": "误报", "WRONG": "错判"}.get(et, et)
        lines.append(f"  - {label} ({et}): {count}")

    lines.extend(["", "## 按归因"])
    for rc, count in sorted(summary["by_root_cause"].items()):
        lines.append(f"  - {rc}: {count}")

    if fixes:
        lines.extend(["", "## 修复建议（按优先级）"])
        for i, fix in enumerate(fixes, 1):
            lines.append(f"")
            lines.append(f"### {i}. {fix['fix_target']} ({fix['case_count']} 个案例)")
            lines.append(f"   动作: {fix['action']}")
            for c in fix["cases"]:
                sev = c.get("severity", "")
                lines.append(f"   - [{sev}] {c['case_id']}: {c['title']}")
                if c.get("lesson"):
                    lines.append(f"     教训: {c['lesson']}")

    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Bug 案例库管理")
    parser.add_argument("--phase", help="只看指定 Phase (A/A.5/A.6/C)")
    parser.add_argument("--status", default="all", choices=["all", "open", "fixed"], help="按状态过滤")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--base-dir", default=CASES_DIR, help="案例库根目录")
    args = parser.parse_args()

    cases = load_cases(Path(args.base_dir))
    if args.phase:
        cases = [c for c in cases if c.get("phase") == args.phase]
    if args.status != "all":
        cases = [c for c in cases if c.get("status") == args.status]

    if args.json:
        print(dump_json_str({"summary": summarize_cases(cases), "fixes": suggest_fixes(cases)}))
    else:
        print(format_report(cases))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
