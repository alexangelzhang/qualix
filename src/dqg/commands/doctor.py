"""Doctor bundle 生成 + 脱敏 + 版本一致性检查（Task 12 纯函数层 + Task 13 CLI/上传）."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from importlib.metadata import metadata as _metadata
from importlib.metadata import version as _version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{6,}"),
    re.compile(r"claude-[A-Za-z0-9_-]{6,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_.-]{6,}"),
]


def redact_text(text: str) -> str:
    """Redact user home paths and common secret-token prefixes."""
    text = re.sub(r"/Users/[^/\s\"']+", "/Users/<user>", text)
    text = re.sub(r"/home/[^/\s\"']+", "/home/<user>", text)
    for pat in _TOKEN_PATTERNS:
        text = pat.sub(lambda m: m.group(0)[:6] + "***", text)
    return text


def _collect_env() -> str:
    lines = []
    try:
        lines.append(f"dqg version: {_version('dev-quality-gate')}")
    except Exception as e:
        lines.append(f"dqg version: unknown ({e})")
    lines.append(f"python: {sys.version.splitlines()[0]}")
    lines.append(f"platform: {platform.platform()}")
    try:
        pip_list = subprocess.run(
            [sys.executable, "-m", "pip", "list"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        lines.append("\n--- pip list ---\n" + pip_list.stdout)
    except Exception as e:
        lines.append(f"pip list failed: {e}")
    return "\n".join(lines)


def check_version_consistency(
    project_root: Path,
    global_version: str | None = None,
    installed_version: str | None = None,
) -> dict[str, Any]:
    """Compare settings.yaml / global VERSION / installed package versions."""
    from contextlib import suppress

    from dqg.core.settings import load_settings

    settings_version = ""
    with suppress(FileNotFoundError):
        settings_version = load_settings(project_root).dqg_version
    if global_version is None:
        g = Path.home() / ".dqg" / "VERSION"
        global_version = g.read_text().strip() if g.exists() else ""
    if installed_version is None:
        try:
            installed_version = _version("dev-quality-gate")
        except Exception:
            installed_version = ""
    versions_seen = {v for v in (settings_version, global_version, installed_version) if v}
    return {
        "settings": settings_version,
        "global": global_version,
        "installed": installed_version,
        "mismatch": len(versions_seen) > 1,
    }


def _recent_output_internal(project_root: Path) -> list[Path]:
    output = project_root / ".dqg" / "output"
    if not output.exists():
        return []
    picks: list[Path] = []
    for proj in output.iterdir():
        if not proj.is_dir():
            continue
        for phase in proj.iterdir():
            if not phase.is_dir():
                continue
            internal = phase / "_internal"
            if internal.is_dir():
                picks.extend(internal.iterdir())
    picks.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return picks[:20]


def build_bundle(
    project_root: Path,
    output: Path,
    redact: bool,
    include_internal: bool,
) -> None:
    """Assemble a tgz doctor bundle rooted at ``project_root`` into ``output``."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        staging = Path(td) / "doctor-bundle"
        staging.mkdir()
        consistency = check_version_consistency(project_root)
        manifest = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "project_root": str(project_root),
            "version_consistency": consistency,
            "version_mismatch": consistency["mismatch"],
            "redacted": redact,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        (staging / "env.txt").write_text(_collect_env())

        settings_path = project_root / ".dqg" / "settings.yaml"
        if settings_path.exists():
            raw = settings_path.read_text()
            (staging / "settings.yaml").write_text(redact_text(raw) if redact else raw)

        last_run = project_root / ".dqg" / "last-run.json"
        (staging / "recent-errors").mkdir()
        if last_run.exists():
            raw = last_run.read_text()
            (staging / "recent-errors" / "last-run.json").write_text(redact_text(raw) if redact else raw)

        output_root = project_root / ".dqg" / "output"
        if output_root.exists():
            for proj in output_root.iterdir():
                sj = proj / "state.json"
                if sj.exists():
                    raw = sj.read_text()
                    (staging / f"state-{proj.name}.json").write_text(redact_text(raw) if redact else raw)

        if include_internal:
            dest = staging / "_internal"
            dest.mkdir()
            for f in _recent_output_internal(project_root):
                if f.suffix not in {".md", ".json", ".txt"}:
                    continue
                try:
                    raw = f.read_text(errors="ignore")
                except Exception:
                    continue
                out_name = f"{f.parent.parent.name}-{f.name}"
                (dest / out_name).write_text(redact_text(raw) if redact else raw)

        lines: list[str] = []
        if output_root.exists():
            for proj in output_root.iterdir():
                for item in proj.rglob("*"):
                    if item.is_file():
                        with contextlib.suppress(Exception):
                            lines.append(f"{item.relative_to(project_root)}\t{item.stat().st_size}")
        (staging / "input-summary.txt").write_text("\n".join(lines[:500]))

        with tarfile.open(output, "w:gz") as tar:
            tar.add(staging, arcname="doctor-bundle")


# ---------------------------------------------------------------------------
# Task 13: glab 自动上传 + CLI 入口
# ---------------------------------------------------------------------------

_ISSUE_URL_PATTERN = re.compile(r"https://[^\s]+/-?/?issues/\d+")


def detect_glab() -> tuple[bool, str]:
    if not shutil.which("glab"):
        return False, "glab not on PATH"
    try:
        r = subprocess.run(
            ["glab", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, f"glab auth status failed: {r.stderr.strip()}"
    except Exception as e:
        return False, str(e)
    return True, "ok"


def resolve_issues_url() -> str:
    try:
        meta = _metadata("dev-quality-gate")
    except Exception:
        return "https://github.com/your-org/rd-gate/issues"
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() == "issues":
            return url.strip()
    return "https://github.com/your-org/rd-gate/issues"


def _repo_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    for suffix in ("/-/issues", "/issues"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return path


def parse_issue_url_from_stdout(stdout: str) -> str | None:
    match = _ISSUE_URL_PATTERN.search(stdout)
    return match.group(0) if match else None


def upload_via_glab(
    title: str,
    description: str,
    bundle: Path,
    repo_path: str,
    timeout: int = 30,
) -> tuple[bool, str | None, str]:
    """Returns (success, issue_url, error_message)."""
    base_cmd = [
        "glab",
        "issue",
        "create",
        "--repo",
        repo_path,
        "--title",
        title,
        "--description",
        description,
    ]
    try:
        r = subprocess.run(
            [*base_cmd, "--file", str(bundle)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, None, "glab timeout"
    except FileNotFoundError:
        return False, None, "glab not found"
    if r.returncode == 0:
        return True, parse_issue_url_from_stdout(r.stdout), ""
    # Fallback for older glab without --file
    try:
        r2 = subprocess.run(
            base_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, None, "glab timeout"
    if r2.returncode != 0:
        return False, None, (r2.stderr or r.stderr).strip()
    url = parse_issue_url_from_stdout(r2.stdout)
    return True, url, "warning: 旧版 glab 不支持 --file，bundle 需手动上传到上面的 issue"


def _is_ci() -> bool:
    """Detect common CI environments via environment variables."""
    return any(os.environ.get(v) for v in ("CI", "GITLAB_CI", "GITHUB_ACTIONS", "JENKINS_URL", "BUILDKITE"))


def run_doctor(
    project_root: Path,
    output: Path | None,
    redact: bool,
    include_internal: bool,
    no_upload: bool,
    title: str | None,
) -> int:
    ci_mode = _is_ci()
    # CI 环境强制 no_upload（无交互、glab 通常不可用）
    if ci_mode:
        no_upload = True

    if not redact and not no_upload:
        print(
            "错误: --no-redact 与上传互斥。请加 --no-upload 或去掉 --no-redact。",
            file=sys.stderr,
        )
        return 2
    if output is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output = project_root / ".dqg" / f"doctor-bundle-{ts}.tgz"
    build_bundle(project_root, output, redact=redact, include_internal=include_internal)
    size_kb = output.stat().st_size // 1024

    consistency = check_version_consistency(project_root)
    issues_url = resolve_issues_url()

    # 检测本地未贡献的新案例
    new_case_count = 0
    try:
        from dqg.commands.contribute import scan_new_cases

        new_case_count = len(scan_new_cases())
    except Exception:
        pass

    if ci_mode:
        # CI 模式：输出机器可读 JSON 到 stdout，供 CI pipeline 消费
        import json as _json

        result = {
            "bundle": str(output),
            "size_kb": size_kb,
            "version_ok": not consistency["mismatch"],
            "version": consistency,
            "upload": "skipped_ci",
            "issues_url": issues_url,
            "new_cases_pending": new_case_count,
        }
        print(_json.dumps(result))
        return 0

    print(f"✓ Bundle 已生成: {output} ({size_kb} KB)")

    if consistency["mismatch"]:
        print(
            f"⚠ 版本不一致: settings={consistency['settings']}, "
            f"global={consistency['global']}, installed={consistency['installed']}"
        )
        print("  建议重跑 install.sh 和 dqg-run init --force")
    else:
        print(f"✓ 版本一致性: OK ({consistency['installed']})")

    issues_url = resolve_issues_url()
    if no_upload:
        print(f"\n--no-upload 已指定。可手动上传 bundle 到:\n  {issues_url}")
        return 0

    ok, reason = detect_glab()
    if not ok:
        print(f"\n⚠ {reason}")
        print(f"  bundle 已生成，请手动上传到:\n    {issues_url}")
        print("  安装 glab 后可启用自动上传: brew install glab && glab auth login -h github.com")
        return 0

    if title is None:
        if sys.stdin.isatty():
            try:
                title = input("issue 标题: ").strip() or "[doctor] DQG error report"
            except EOFError:
                title = "[doctor] DQG error report"
        else:
            title = "[doctor] DQG error report"

    repo_path = _repo_path_from_url(issues_url)
    ok, url, warn = upload_via_glab(
        title=title,
        description=f"自动生成的 doctor bundle。版本: {consistency['installed']}",
        bundle=output,
        repo_path=repo_path,
    )
    if ok:
        print(f"✓ Issue 已创建: {url or '(URL 未能解析)'}")
        if warn:
            print(f"  {warn}")
        if new_case_count > 0:
            print(f"\n💡 发现 {new_case_count} 条本地新案例，可运行 dqg-run contribute 贡献回 DQG repo")
        return 0
    print(f"⚠ 上传失败: {warn}")
    print(f"  bundle 仍保留于: {output}")
    print(f"  可手动上传到: {issues_url}")
    if new_case_count > 0:
        print(f"\n💡 发现 {new_case_count} 条本地新案例，可运行 dqg-run contribute 贡献回 DQG repo")
    return 2
