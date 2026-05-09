"""从飞书 Bitable bug 表批量导入案例到 failure-library.

用法:
    python -m dqg.tracking.import_bug_cases /tmp/dqg_bitable_test/ingest.json
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

from dqg.constants import PHASE_DIR_MAP
from dqg.json_utils import dump_json_str, load_json_strict

# 二级分类 → (phase, error_type, root_cause, fix_target)
CATEGORY_MAPPING: Final = MappingProxyType(
    {
        # 单测相关
        "函数未覆盖": {
            "phase": "Q06",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        "函数正常分支未覆盖": {
            "phase": "Q06",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        "函数异常分支未覆盖": {
            "phase": "Q06",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        "函数覆盖assert不对": {
            "phase": "Q06",
            "error_type": "WRONG",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        "有单测未运行": {
            "phase": "Q06",
            "error_type": "FN",
            "root_cause": "CONTEXT",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        "提测前无单测": {
            "phase": "Q06",
            "error_type": "FN",
            "root_cause": "CONTEXT",
            "fix_target": "skills/unit-test-audit/SKILL.md",
        },
        # 需求分析相关
        "需求实现遗漏": {
            "phase": "Q01",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/requirement-structuring/SKILL.md",
        },
        "需求遗漏": {
            "phase": "Q01",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/requirement-structuring/SKILL.md",
        },
        "需求理解未对齐": {
            "phase": "Q01",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/requirement-structuring/SKILL.md",
        },
        "产品需求不明确": {
            "phase": "Q01",
            "error_type": "FN",
            "root_cause": "CONTEXT",
            "fix_target": "skills/requirement-structuring/SKILL.md",
        },
        # 技术方案相关
        "技术方案不清晰": {
            "phase": "Q03",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/tech-quality-review/SKILL.md",
        },
        "技术实现遗漏": {
            "phase": "Q03",
            "error_type": "FN",
            "root_cause": "SKILL_RULE",
            "fix_target": "skills/tech-quality-review/SKILL.md",
        },
        # 安全/性能/幂等
        "安全问题": {
            "phase": "Q01",
            "error_type": "FN",
            "root_cause": "KNOWLEDGE",
            "fix_target": "references/risk-and-exception-catalog.md",
        },
        "性能问题": {
            "phase": "Q03",
            "error_type": "FN",
            "root_cause": "KNOWLEDGE",
            "fix_target": "references/risk-and-exception-catalog.md",
        },
        "幂等": {
            "phase": "Q03",
            "error_type": "FN",
            "root_cause": "KNOWLEDGE",
            "fix_target": "references/risk-and-exception-catalog.md",
        },
    }
)

# 二级分类 → severity
SEVERITY_MAP: Final = MappingProxyType(
    {
        "函数未覆盖": "high",
        "函数正常分支未覆盖": "high",
        "函数异常分支未覆盖": "high",
        "函数覆盖assert不对": "high",
        "需求实现遗漏": "high",
        "需求遗漏": "critical",
        "安全问题": "critical",
        "幂等": "critical",
        "性能问题": "medium",
        "技术方案不清晰": "medium",
        "技术实现遗漏": "high",
        "需求理解未对齐": "medium",
        "产品需求不明确": "medium",
    }
)


def _sanitize_dirname(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", s).strip("._")[:60]


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_flatten(v) for v in value)
    if isinstance(value, dict):
        return value.get("text", "") or value.get("name", "") or dump_json_str(value, indent=None)
    return str(value)


def _ts_to_date(ts: Any) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return ""


def convert_record(record: dict[str, Any], idx: int) -> dict[str, Any] | None:
    """将一条 bitable 记录转为案例库格式。返回 None 表示跳过."""
    fields = record.get("fields", {})
    bug_type = _flatten(fields.get("BUG分类", ""))
    if bug_type != "后端":
        return None

    cat1 = _flatten(fields.get("一级分类", ""))
    cat2 = _flatten(fields.get("二级分类", ""))

    mapping = CATEGORY_MAPPING.get(cat2)
    if not mapping:
        return None

    bug_title = _flatten(fields.get("Bug链接", ""))
    analysis = _flatten(fields.get("分析结果", ""))
    ut_fix = _flatten(fields.get("单测改进措施", ""))
    other_fix = _flatten(fields.get("其他改进措施", ""))
    requirement = _flatten(fields.get("所属需求", ""))
    tags = fields.get("标签", [])
    if isinstance(tags, list):
        tags = [_flatten(t) for t in tags]
    else:
        tags = [_flatten(tags)]
    date = _ts_to_date(fields.get("提出日期"))
    record_id = record.get("record_id", "")
    phase_dir = PHASE_DIR_MAP.get(mapping["phase"], "")

    case_id = f"{mapping['error_type']}-{phase_dir}-bitable-{idx:03d}"
    severity = SEVERITY_MAP.get(cat2, "medium")

    case_json = {
        "case_id": case_id,
        "phase": mapping["phase"],
        "error_type": mapping["error_type"],
        "severity": severity,
        "title": bug_title[:100] if bug_title else f"{cat2} (record {record_id})",
        "root_cause": mapping["root_cause"],
        "fix_target": mapping["fix_target"],
        "tags": [t for t in tags if t] + [cat2],
        "created_at": date or "2026-04-02",
        "status": "open",
        "source": {
            "bitable_record_id": record_id,
            "category1": cat1,
            "category2": cat2,
            "requirement": requirement,
        },
        "expected": {
            "content": ut_fix or other_fix or "（需人工补充）",
        },
        "actual": {
            "content": analysis or "（需人工补充）",
        },
        "lesson": ut_fix if ut_fix and ut_fix != "无需改进" else (other_fix or ""),
    }

    input_md_lines = [
        f"# {bug_title}",
        "",
        f"- 所属需求: {requirement}" if requirement else "",
        f"- 二级分类: {cat2}",
        f"- 提出日期: {date}" if date else "",
        "",
        "## 分析结果",
        "",
        analysis or "（无）",
        "",
    ]
    if ut_fix and ut_fix != "无需改进":
        input_md_lines.extend(["## 单测改进措施", "", ut_fix, ""])
    if other_fix:
        input_md_lines.extend(["## 其他改进措施", "", other_fix, ""])

    return {
        "case_json": case_json,
        "input_md": "\n".join(line for line in input_md_lines if line is not None),
        "phase_dir": phase_dir,
        "dirname": _sanitize_dirname(f"{case_id}"),
    }


def import_from_bitable(
    ingest_path: Path,
    output_base: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """从 bitable ingest.json 批量导入案例."""
    data = load_json_strict(ingest_path)
    tables = data.get("tables", [])

    imported = 0
    skipped = 0
    by_phase: dict[str, int] = {}

    for table in tables:
        records = table.get("records", [])
        for idx, record in enumerate(records, 1):
            result = convert_record(record, idx)
            if result is None:
                skipped += 1
                continue

            phase_dir = result["phase_dir"]
            dirname = result["dirname"]
            case_dir = output_base / phase_dir / dirname

            if dry_run:
                imported += 1
                by_phase[phase_dir] = by_phase.get(phase_dir, 0) + 1
                continue

            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "case.json").write_text(
                dump_json_str(result["case_json"]),
                encoding="utf-8",
            )
            (case_dir / "input.md").write_text(result["input_md"], encoding="utf-8")
            imported += 1
            by_phase[phase_dir] = by_phase.get(phase_dir, 0) + 1

    return {
        "imported": imported,
        "skipped": skipped,
        "by_phase": by_phase,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="从飞书 Bitable 批量导入 bug 案例")
    parser.add_argument("ingest_json", help="bitable ingest.json 路径")
    parser.add_argument(
        "--output",
        default="regression/failure-library/cases",
        help="案例库输出目录（默认 regression/failure-library/cases）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args()

    result = import_from_bitable(
        ingest_path=Path(args.ingest_json),
        output_base=Path(args.output),
        dry_run=args.dry_run,
    )

    print(f"导入: {result['imported']}, 跳过: {result['skipped']}")
    for phase, count in sorted(result["by_phase"].items()):
        print(f"  {phase}: {count}")

    if args.dry_run:
        print("\n(dry-run 模式，未实际写入)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
