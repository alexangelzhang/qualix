#!/usr/bin/env python3
"""T8: Pydantic 必填字段须在对应 SKILL 文档节中出现（防 prompt/schema 漂移）."""

from __future__ import annotations

import sys
from pathlib import Path


def _repo_root() -> Path:
    p = Path(__file__).resolve().parent.parent
    if (p / "src" / "qualix").is_dir():
        return p
    return p.parent


def _required_fields(model: type) -> list[str]:
    from pydantic import BaseModel

    if not issubclass(model, BaseModel):
        return []
    return [name for name, finfo in model.model_fields.items() if finfo.is_required()]


def _slice(text: str, start: str, end: str | None) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    if not end:
        return text[i:]
    j = text.find(end, i)
    return text[i:j] if j >= i else text[i:]


def _check_q03(skill_text: str) -> list[str]:
    from qualix.schemas.phase_q03 import FailureModeItem, QualityIssue

    errs: list[str] = []
    start = "**`failure_modes[]` 每条必填字段"
    section = _slice(skill_text, start, "### Step 7")
    if not section.strip():
        errs.append(f"Q03 SKILL 缺少片段起始标记: {start!r}")
        return errs
    for field in _required_fields(FailureModeItem):
        if field not in section:
            errs.append(f"Q03 SKILL failure_modes 节未覆盖 schema 必填字段 {field!r}")

    start2 = "### `phase_a6_structured.json` 格式"
    sec2 = _slice(skill_text, start2, "## 通过标准")
    if not sec2.strip():
        errs.append("Q03 SKILL 缺少 phase_a6_structured 格式节")
        return errs
    for field in _required_fields(QualityIssue):
        if field not in sec2:
            errs.append(f"Q03 SKILL issues 示例节未覆盖 schema 必填字段 {field!r}")
    return errs


def _check_q06(skill_text: str) -> list[str]:
    from qualix.schemas.phase_q06 import EutAuditItem, FindingItem

    errs: list[str] = []
    start = "**`findings[]` 每条必填"
    section = _slice(skill_text, start, "## 通过标准")
    if not section.strip():
        errs.append(f"Q06 SKILL 缺少片段起始标记: {start!r}")
    else:
        for field in _required_fields(FindingItem):
            if field not in section:
                errs.append(f"Q06 SKILL findings 节未覆盖 schema 必填字段 {field!r}")

    start2 = "## phase_c_structured.json 产出"
    sec2 = _slice(skill_text, start2, "## 通过标准")
    if not sec2.strip():
        errs.append("Q06 SKILL 缺少 phase_c_structured 产出格式节")
    else:
        for field in _required_fields(EutAuditItem):
            if field not in sec2:
                errs.append(f"Q06 SKILL audit_items 节未覆盖 schema 必填字段 {field!r}")
    return errs


def main() -> int:
    root = _repo_root()
    checks = [
        (root / "skills" / "tech-quality-review" / "SKILL.md", _check_q03),
        (root / "skills" / "unit-test-audit" / "SKILL.md", _check_q06),
    ]
    all_errs: list[str] = []
    for path, fn in checks:
        if not path.is_file():
            all_errs.append(f"Missing skill file: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for e in fn(text):
            all_errs.append(f"{path.relative_to(root)}: {e}")

    if all_errs:
        print("Schema↔Prompt sync failures:\n", file=sys.stderr)
        for e in all_errs:
            print(e, file=sys.stderr)
        return 1
    print("Schema↔Prompt sync: OK (Q03 + Q06 contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
