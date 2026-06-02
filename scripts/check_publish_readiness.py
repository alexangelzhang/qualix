#!/usr/bin/env python3
"""Public-release readiness checks for Qualix.

This is intentionally conservative: it catches old branding, old repository
names, private-link hints, and common credential shapes before the repository is
made public.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".claude", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build", ".venv", "venv", "internal", "system-health-reports", "plans", "specs"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".pyc", ".sqlite", ".db", ".tgz", ".zip"}

FORBIDDEN_TEXT = [
    "D" + "QG",
    "d" + "qg",
    "D" + "qg",
    "." + "d" + "qg",
    "rd" + "-gate",
    "your-org",
    "d" + "qg-starter",
    "d" + "qg_starter",
    "d" + "qg.mdc",
    "git.n." + "xiao" + "mi.com",
    "mi" + ".feishu",
    "xiao" + "mi",
    "小" + "米",
    "mi" + ".com",
    "bytedance",
    "customer/",
    "团队数据上报",
    "共享看板",
    "finance" + "-model",
    "shuang" + "zhou-v4",
    "kind" + "-care",
    "store" + "-ops",
]

FORBIDDEN_TEXT_LOWER = [item.lower() for item in FORBIDDEN_TEXT]
FORBIDDEN_PATTERNS = [
    re.compile(r"\b" + "v" + "af" + r"\b", re.IGNORECASE),
    re.compile(r"\b" + "v" + "kf" + r"\b", re.IGNORECASE),
    re.compile(re.escape("." + "toon"), re.IGNORECASE),
]

URL_PATTERN = re.compile(r"https?://[^\s)\]>'\"`]+")
PRIVATE_HOST_HINTS = (
    "corp",
    "internal",
    "intranet",
    "localhost.company",
    "git.n.",
    "feishu.cn",
    "larksuite.com",
    "larkoffice.com",
)

ALLOW_URL_HOSTS = {
    "127.0.0.1",
    "localhost",
    "api.anthropic.com",
    "api.moonshot.cn",
    "api.openai.com",
    "dashscope.aliyuncs.com",
    "evil.com",
    "example.com",
    "example.feishu.cn",
    "generativelanguage.googleapis.com",
    "github.com",
    "json-schema.org",
    "nodejs.org",
    "open.feishu.cn",
    "openrouter.ai",
    "qualix.local",
}

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
    "scripts/check_publish_readiness.py",
    "tests/test_doctor_cmd.py",
    "tests/test_content_scanner.py",
    "tests/test_adaptive_loop_cache.py",
    "src/qualix/agents/agent.py",
    "src/qualix/tracking/import_bug_cases.py",
    # sandbox.js uses `apiKey` as a variable name; the pattern fires on
    # `apiKey = document.getElementById(...)` which is not a real secret.
    "docs/sandbox/sandbox.js",
}

ALLOW_FORBIDDEN_TEXT_FILES = {
    "scripts/check_publish_readiness.py",
}

ALLOW_PRIVATE_URL_FILES = {
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
        if ("d" + "qg") in lowered or ("rd" + "-gate") in lowered:
            issues.append(f"filename contains legacy name: {rel}")
        if "open-source-plan" in lowered and rel != ".open-source-plan.local.md":
            issues.append(f"open-source plan must stay local-only: {rel}")
        if lowered.startswith(".open-source-plan"):
            issues.append(f"temporary open-source plan still exists: {rel}")
    return issues


def check_text(files: list[Path]) -> list[str]:
    issues: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        text_lower = text.lower()
        if rel not in ALLOW_FORBIDDEN_TEXT_FILES:
            for needle in FORBIDDEN_TEXT_LOWER:
                if needle in text_lower:
                    issues.append(f"{rel}: contains forbidden text `{needle}`")
            for pattern in FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    issues.append(f"{rel}: matches forbidden pattern `{pattern.pattern}`")

        if rel not in ALLOW_PRIVATE_URL_FILES:
            for match in URL_PATTERN.finditer(text):
                raw_url = match.group(0).rstrip(".,;")
                try:
                    host = (urlparse(raw_url).hostname or "").lower()
                except ValueError:
                    continue
                if not host:
                    continue
                if host in ALLOW_URL_HOSTS or host.endswith(".github.com"):
                    continue
                if host.startswith("example."):
                    continue
                if any(hint in host for hint in PRIVATE_HOST_HINTS):
                    issues.append(f"{rel}: contains private-link-like URL `{raw_url}`")

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
