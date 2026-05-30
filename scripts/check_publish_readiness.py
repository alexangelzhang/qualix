#!/usr/bin/env python3
"""Public-release readiness checks for Qualix.

This is intentionally conservative: it catches old branding, old repository
names, private-link hints, and common credential shapes before the repository is
made public.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build", ".venv", "venv"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".pyc", ".sqlite", ".db", ".tgz", ".zip"}

FORBIDDEN_TEXT = [
    "DQG",
    "dqg",
    "Dqg",
    ".dqg",
    "rd-gate",
    "your-org",
    "dqg-starter",
    "dqg_starter",
    "dqg.mdc",
    "mi.feishu",
    "xiaomi",
    "mi.com",
    "bytedance",
    "customer/",
    "团队数据上报",
    "共享看板",
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9][A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{24,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/-]{16,}"),
]

ALLOW_SECRET_FILES = {
    "SECURITY.md",
    "CONTRIBUTING.md",
    "ISSUE.md",
    "scripts/check_publish_readiness.py",
    "docs/superpowers/specs/2026-05-11-qualix-tool-distribution-design.md",
    "docs/superpowers/plans/2026-04-16-p0-skill-evolution-anti-rationalization.md",
    "tests/test_doctor_cmd.py",
    "tests/test_content_scanner.py",
    "tests/test_adaptive_loop_cache.py",
    "src/qualix/agents/agent.py",
    "src/qualix/tracking/import_bug_cases.py",
}

ALLOW_FORBIDDEN_TEXT_FILES = {
    "scripts/check_publish_readiness.py",
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        rel_parts = set(path.relative_to(ROOT).parts)
        if rel_parts & SKIP_DIRS:
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        files.append(path)
    return files


def check_names(files: list[Path]) -> list[str]:
    issues: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        lowered = rel.lower()
        if "dqg" in lowered or "rd-gate" in lowered:
            issues.append(f"filename contains legacy name: {rel}")
    return issues


def check_text(files: list[Path]) -> list[str]:
    issues: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if rel not in ALLOW_FORBIDDEN_TEXT_FILES:
            for needle in FORBIDDEN_TEXT:
                if needle in text:
                    issues.append(f"{rel}: contains forbidden text `{needle}`")

        if rel not in ALLOW_SECRET_FILES:
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    issues.append(f"{rel}: matches secret-like pattern `{pattern.pattern}`")
    return issues


def check_failure_library() -> list[str]:
    issues: list[str] = []
    cases = sorted((ROOT / "regression" / "failure-library" / "cases").rglob("case.json"))
    if len(cases) > 5:
        issues.append(f"failure-library has {len(cases)} case files; expected only a few synthetic examples")
    for case in cases:
        rel = case.relative_to(ROOT).as_posix()
        if "SYNTH-" not in rel:
            issues.append(f"failure-library case does not look synthetic: {rel}")
    return issues


def main() -> int:
    files = iter_files()
    issues = []
    issues.extend(check_names(files))
    issues.extend(check_text(files))
    issues.extend(check_failure_library())

    if issues:
        print("Publish-readiness check failed:\n")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Publish-readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
