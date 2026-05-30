"""dqg-run contribute — 把本地新积累的 failure-library 案例贡献回 DQG repo.

触发时机：
1. dqg-run contribute          手动批量贡献
2. dqg-run <pid> approve       Phase approve 后自动触发（静默，失败不阻断）
3. dqg-run doctor              doctor 时顺带检测并提示
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str, load_json_strict


def _failure_library_cases() -> Path:
    return Path.home() / ".dqg" / "regression" / "failure-library" / "cases"


def _issues_url() -> str:
    try:
        from dqg.commands.doctor import resolve_issues_url

        return resolve_issues_url()
    except Exception:
        return "https://github.com/your-org/rd-gate/issues"


def _repo_path_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    for suffix in ("/-/issues", "/issues"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return path


def scan_new_cases(cases_root: Path | None = None) -> list[dict[str, Any]]:
    """扫描未贡献的新案例（status != 'contributed'）."""
    root = cases_root or _failure_library_cases()
    if not root.exists():
        return []
    cases = []
    for case_file in sorted(root.rglob("case.json")):
        try:
            data = load_json_strict(case_file)
            if data.get("status") != "contributed":
                data["_case_file"] = str(case_file)
                cases.append(data)
        except Exception:
            continue
    return cases


def mark_contributed(case_files: list[str]) -> None:
    """把案例 status 标记为 contributed."""
    for path_str in case_files:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            data = load_json_strict(path)
            data["status"] = "contributed"
            data["contributed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
            path.write_text(dump_json_str(data))
        except Exception:
            continue


def _build_mr_description(cases: list[dict[str, Any]]) -> str:
    lines = [
        "## DQG failure-library 案例贡献",
        "",
        f"本 MR 由 `dqg-run contribute` 自动生成，包含 {len(cases)} 条新案例。",
        "",
        "### 案例清单",
        "",
    ]
    for c in cases:
        lines.append(
            f"- **[{c.get('phase', '?')}]** {c.get('title', c.get('case_id', '?'))} "
            f"(`{c.get('error_type', '?')}`, severity={c.get('severity', '?')})"
        )
    lines += [
        "",
        "### 操作说明",
        "1. 审查每条案例的 `root_cause` 和 `lesson` 是否准确",
        "2. 确认 `fix_target` 指向正确的 skill 文件",
        "3. 合并后案例将随下次 `install.sh` 分发给所有用户",
        "",
        "🤖 Generated with [DQG](https://github.com/your-org/rd-gate)",
    ]
    return "\n".join(lines)


def contribute_via_glab(
    cases: list[dict[str, Any]],
    repo_path: str,
    title: str | None = None,
    timeout: int = 30,
) -> tuple[bool, str | None, str]:
    """通过 glab 创建 MR，返回 (success, mr_url, error_message)."""
    if not shutil.which("glab"):
        return False, None, "glab not on PATH"

    if title is None:
        title = f"[contribute] failure-library {len(cases)} 条新案例"

    description = _build_mr_description(cases)

    # 把案例打包成临时 tgz 附件
    with tempfile.TemporaryDirectory() as td:
        bundle_dir = Path(td) / "cases"
        bundle_dir.mkdir()
        for c in cases:
            case_file = Path(c.get("_case_file", ""))
            if case_file.exists():
                dest = bundle_dir / case_file.parent.name
                dest.mkdir(exist_ok=True)
                shutil.copy2(case_file, dest / "case.json")

        bundle_path = Path(td) / f"failure-library-{time.strftime('%Y%m%d-%H%M%S')}.tgz"
        import tarfile

        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(bundle_dir, arcname="cases")

        cmd = [
            "glab",
            "mr",
            "create",
            "--repo",
            repo_path,
            "--title",
            title,
            "--description",
            description,
            "--source-branch",
            f"contribute/failure-library-{time.strftime('%Y%m%d%H%M%S')}",
            "--target-branch",
            "main",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, None, "glab timeout"
        except FileNotFoundError:
            return False, None, "glab not found"

        if r.returncode == 0:
            # 解析 MR URL
            import re

            match = re.search(r"https://[^\s]+/-?/?merge_requests/\d+", r.stdout)
            url = match.group(0) if match else None
            return True, url, ""
        return False, None, (r.stderr or r.stdout).strip()


def run_contribute(
    cases_root: Path | None = None,
    title: str | None = None,
    no_upload: bool = False,
    silent: bool = False,
) -> tuple[int, list[dict[str, Any]]]:
    """执行贡献流程，返回 (exit_code, contributed_cases)."""
    cases = scan_new_cases(cases_root)

    if not cases:
        if not silent:
            print("✓ 无新案例需要贡献")
        return 0, []

    if not silent:
        print(f"发现 {len(cases)} 条新案例待贡献：")
        for c in cases:
            print(f"  [{c.get('phase', '?')}] {c.get('title', c.get('case_id', '?'))}")

    if no_upload or os.environ.get("CI"):
        if not silent:
            print(f"\n--no-upload 已指定或 CI 环境，跳过上传。案例位于: {_failure_library_cases()}")
        return 0, cases

    issues_url = _issues_url()
    repo_path = _repo_path_from_url(issues_url).replace("/-/issues", "").replace("/issues", "")

    ok, url, err = contribute_via_glab(cases, repo_path, title=title)
    if ok:
        mark_contributed([c["_case_file"] for c in cases if "_case_file" in c])
        if not silent:
            print(f"✓ MR 已创建: {url or '(URL 未能解析)'}")
        return 0, cases
    else:
        if not silent:
            print(f"⚠ 上传失败: {err}")
            print(f"  案例已保存在本地: {_failure_library_cases()}")
            print(f"  可手动提交到: {issues_url}")
        return 1, cases
