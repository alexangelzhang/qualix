# DQG 工具化分发 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 DQG 工具与用户项目之间的物理分发边界，让外部用户 cwd 下 `ls` 看不到 DQG 源码，Claude 读不到就不会改。

**Architecture:** 采纳 ROADMAP §F 的 L1 备选路径（install.sh + `~/.dqg/`），Python 包装入 `site-packages`，资源（skills/references/profiles/regression）拷到 `~/.dqg/`，用户项目下建 `.dqg/` 工作区（output + settings.yaml），CLAUDE.md 追加 guardrail 章节。所有资源路径推导收口到统一 `ResourceResolver`。按三批实施：物理边界 → 用户工作区 → doctor。

**Tech Stack:** Python 3.11+, hatchling ≥ 1.18, importlib.resources/metadata, bash + 内联 Python 脚本（install.sh 采用 VAF 模式），glab CLI（doctor 上传）。

---

## 参考资料

- Spec: `docs/superpowers/specs/2026-05-11-dqg-tool-distribution-design.md`
- 诊断: `docs/distribution-gap.md`
- ROADMAP §F
- VAF install.sh 模式: `https://github.com/your-org/rd-gate/blob/main/install.sh`

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `VERSION` | Create | 纯文本版本号，如 `0.2.0-dev.20260511`；hatchling 和 install.sh 的共同版本源 |
| `install.sh` | Create | bash + 内联 Python 脚本，借鉴 VAF；拷资源 + pip 安装 |
| `src/dqg/core/resource_resolver.py` | Create | 三层资源查找（项目 `.dqg/` → `~/.dqg/` → `importlib.resources`） |
| `src/dqg/commands/init.py` | Create | `dqg-run init` 实现：建 .dqg/output、写 settings.yaml、注入 CLAUDE.md |
| `src/dqg/commands/doctor.py` | Create | `dqg-run doctor` 实现：生成 bundle、脱敏、glab 上传 |
| `src/dqg/commands/path_cmd.py` | Create | `dqg-run path <skills\|references\|profiles>` 只读查看内置资源 |
| `src/dqg/core/last_run.py` | Create | last-run marker 读写（`.dqg/last-run.json`） |
| `src/dqg/core/settings.py` | Create | `.dqg/settings.yaml` 加载器 + 版本一致性检查 |
| `pyproject.toml` | Modify | dynamic version、project.urls、wheel force-include |
| `src/dqg/__init__.py` | Modify | `__version__` 走 importlib.metadata |
| `src/dqg/core/profiles.py` | Modify | `_profiles_root` / `_repo_root` 迁到 ResourceResolver |
| `src/dqg/core/cli.py` | Modify | 迁移 Path(__file__) 到 ResourceResolver；不动 `_base_dir`（仍用 Path.cwd）|
| `src/dqg/core/runner.py` | Modify | startup 时记录 last-run marker；注册 init/doctor/path 子命令 |
| `src/dqg/cache/llm_result_cache.py` | Modify | Path(__file__).parent.parent 迁到 ResourceResolver |
| `tests/test_resource_resolver.py` | Create | 三层查找单元测试 |
| `tests/test_install_sh.py` | Create | install.sh 核心函数测试（通过内联 python 导入） |
| `tests/test_init_cmd.py` | Create | init 幂等性、CLAUDE.md marker 替换测试 |
| `tests/test_doctor_cmd.py` | Create | bundle 生成、脱敏、glab fallback 测试 |
| `tests/test_settings.py` | Create | settings.yaml 加载、版本一致性 |
| `tests/test_version.py` | Create | VERSION 文件与 importlib.metadata 一致 |
| `docs/migration-from-0.1.md` | Create | 老用户迁移指南 |

## 分批交付

- **第一批 · 物理边界** (Task 1-6): VERSION + pyproject + ResourceResolver + install.sh + 老路径 deprecation
- **第二批 · 用户工作区** (Task 7-10): init + path 命令 + settings + 版本一致性 warning
- **第三批 · doctor** (Task 11-15): last-run marker + bundle + 脱敏 + glab 上传 + 迁移文档

每个 Task 末尾都 commit。Task 内部的 step 保持 2-5 分钟粒度。

---

## 第一批 · 物理边界

### Task 1: VERSION 文件 + pyproject.toml 改造

**Files:**
- Create: `VERSION`
- Modify: `pyproject.toml`
- Modify: `src/dqg/__init__.py`
- Test: `tests/test_version.py`

- [ ] **Step 1: 创建 VERSION 文件**

```bash
echo "0.2.0-dev.20260511" > VERSION
```

- [ ] **Step 2: 写版本一致性测试**

```python
# tests/test_version.py
from pathlib import Path
import importlib.metadata


def test_version_file_exists():
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    assert version_file.exists()
    content = version_file.read_text().strip()
    assert content  # 非空
    assert "\n" not in content  # 单行


def test_package_version_matches_file():
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    file_version = version_file.read_text().strip()
    pkg_version = importlib.metadata.version("dev-quality-gate")
    assert pkg_version == file_version
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd /path/to/rd-gate && python -m pytest tests/test_version.py -v`
Expected: FAIL（VERSION 文件不存在或 pyproject 还没改 dynamic）

- [ ] **Step 4: 修改 pyproject.toml**

将 `version = "0.1.0"` 改为 `dynamic = ["version"]`，增加 hatch version source 和 project.urls：

```toml
[project]
name = "dev-quality-gate"
dynamic = ["version"]
description = "研发质量门禁 — 从需求到代码的全链路防漏管线"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
]

[project.urls]
Homepage = "https://github.com/your-org/rd-gate"
Issues = "https://github.com/your-org/rd-gate/-/issues"
Source = "https://github.com/your-org/rd-gate"

[tool.hatch.version]
path = "VERSION"
pattern = "(?P<version>.+)"

[tool.hatch.build.targets.wheel]
packages = ["src/dqg"]

[tool.hatch.build.targets.wheel.force-include]
"skills" = "dqg/skills"
"references" = "dqg/references"
"profiles" = "dqg/profiles"
```

- [ ] **Step 5: 修改 src/dqg/__init__.py**

在文件顶部加：

```python
from importlib.metadata import version as _meta_version

__version__ = _meta_version("dev-quality-gate")
```

- [ ] **Step 6: 重新安装并跑测试**

Run: `cd /path/to/rd-gate && pip install -e . && python -m pytest tests/test_version.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add VERSION pyproject.toml src/dqg/__init__.py tests/test_version.py
git commit -m "feat(distribution): VERSION 文件 + pyproject.toml dynamic version + project.urls"
```

---

### Task 2: ResourceResolver 统一资源查找

**Files:**
- Create: `src/dqg/core/resource_resolver.py`
- Test: `tests/test_resource_resolver.py`

- [ ] **Step 1: 写 ResourceResolver 测试**

```python
# tests/test_resource_resolver.py
from pathlib import Path
import pytest

from dqg.core.resource_resolver import ResourceResolver


@pytest.fixture
def tmp_project(tmp_path):
    """模拟项目目录 + .dqg/"""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".dqg" / "skill-overrides").mkdir(parents=True)
    (project / ".dqg" / "skill-overrides" / "Q01.md").write_text("override")
    return project


@pytest.fixture
def tmp_global(tmp_path):
    """模拟 ~/.dqg/"""
    global_dqg = tmp_path / "home" / ".dqg"
    (global_dqg / "skills" / "Q01").mkdir(parents=True)
    (global_dqg / "skills" / "Q01" / "SKILL.md").write_text("global skill")
    (global_dqg / "references").mkdir(parents=True)
    (global_dqg / "references" / "data.md").write_text("ref data")
    (global_dqg / "profiles" / "java-ddd").mkdir(parents=True)
    (global_dqg / "profiles" / "java-ddd" / "profile.json").write_text("{}")
    (global_dqg / "regression").mkdir(parents=True)
    return global_dqg


def test_resolve_project_override(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("skill-overrides", "Q01.md")
    assert result == tmp_project / ".dqg" / "skill-overrides" / "Q01.md"


def test_resolve_global_fallback(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("skills", "Q01/SKILL.md")
    assert result == tmp_global / "skills" / "Q01" / "SKILL.md"


def test_resolve_not_found_raises(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    with pytest.raises(FileNotFoundError):
        resolver.resolve("skills", "NONEXISTENT/SKILL.md")


def test_resolve_profiles(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("profiles", "java-ddd/profile.json")
    assert result == tmp_global / "profiles" / "java-ddd" / "profile.json"


def test_list_category(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    items = resolver.list_category("profiles")
    assert any("java-ddd" in str(p) for p in items)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_resource_resolver.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 ResourceResolver**

```python
# src/dqg/core/resource_resolver.py
from __future__ import annotations

from pathlib import Path


class ResourceResolver:
    """三层回退资源查找：项目 .dqg/ -> ~/.dqg/ -> importlib.resources 兜底."""

    def __init__(
        self,
        project_root: Path | None = None,
        global_root: Path | None = None,
    ):
        self.project_root = project_root or Path.cwd()
        self.project_dqg = self.project_root / ".dqg"
        self.global_root = global_root or (Path.home() / ".dqg")

    def resolve(self, category: str, relative: str) -> Path:
        """按 项目级 -> 全局 -> 包内 顺序查找，返回第一个存在的路径."""
        candidates = [
            self.project_dqg / category / relative,
            self.global_root / category / relative,
            self._package_fallback(category, relative),
        ]
        for path in candidates:
            if path and path.exists():
                return path
        raise FileNotFoundError(
            f"Resource not found: {category}/{relative}\n"
            f"Searched: {[str(c) for c in candidates if c]}"
        )

    def resolve_dir(self, category: str) -> Path:
        """返回某个 category 的目录（优先全局）."""
        candidates = [
            self.global_root / category,
            self._package_fallback_dir(category),
        ]
        for path in candidates:
            if path and path.exists():
                return path
        raise FileNotFoundError(f"Category directory not found: {category}")

    def list_category(self, category: str) -> list[Path]:
        """列出某个 category 下所有条目（合并项目级 + 全局，项目级优先）."""
        seen: dict[str, Path] = {}
        global_dir = self.global_root / category
        if global_dir.exists():
            for item in sorted(global_dir.iterdir()):
                if item.name != ".DS_Store":
                    seen[item.name] = item
        project_dir = self.project_dqg / category
        if project_dir.exists():
            for item in sorted(project_dir.iterdir()):
                if item.name != ".DS_Store":
                    seen[item.name] = item
        return list(seen.values())

    @staticmethod
    def _package_fallback(category: str, relative: str) -> Path | None:
        try:
            from importlib.resources import files
            pkg_path = files("dqg") / category / relative
            if hasattr(pkg_path, "_path"):
                p = Path(str(pkg_path._path))
            else:
                p = Path(str(pkg_path))
            return p if p.exists() else None
        except (ModuleNotFoundError, TypeError):
            return None

    @staticmethod
    def _package_fallback_dir(category: str) -> Path | None:
        try:
            from importlib.resources import files
            pkg_path = files("dqg") / category
            if hasattr(pkg_path, "_path"):
                p = Path(str(pkg_path._path))
            else:
                p = Path(str(pkg_path))
            return p if p.is_dir() else None
        except (ModuleNotFoundError, TypeError):
            return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_resource_resolver.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/core/resource_resolver.py tests/test_resource_resolver.py
git commit -m "feat(distribution): ResourceResolver 三层资源查找"
```

---

### Task 3: 迁移 profiles.py 和 cli.py 到 ResourceResolver

**Files:**
- Modify: `src/dqg/core/profiles.py:41-46`
- Modify: `src/dqg/core/cli.py:174`
- Modify: `src/dqg/cache/llm_result_cache.py:97`

- [ ] **Step 1: 跑现有测试确认绿色基线**

Run: `python -m pytest tests/ -x -q --timeout=30 2>&1 | tail -5`
Expected: 全绿或已知 skip

- [ ] **Step 2: 迁移 profiles.py**

将 `_profiles_root()` 和 `_repo_root()` 改为使用 ResourceResolver：

```python
# src/dqg/core/profiles.py — 替换 L41-46
from dqg.core.resource_resolver import ResourceResolver

_resolver = ResourceResolver()


def _profiles_root() -> Path:
    return _resolver.resolve_dir("profiles")


def _repo_root() -> Path:
    """Deprecated: 仅用于 profile.json 里的相对路径解析."""
    return _resolver.global_root
```

- [ ] **Step 3: 迁移 cli.py 的 dashboard 路径**

```python
# src/dqg/core/cli.py L174 — 替换 Path(__file__).parents[1] / "reporting" / ...
from dqg.reporting.dashboard import __file__ as _dashboard_init
dashboard_path = Path(_dashboard_init)
```

- [ ] **Step 4: 迁移 llm_result_cache.py**

```python
# src/dqg/cache/llm_result_cache.py L97 — 替换
from dqg.quality.judge import __file__ as _judge_file
judge_module = Path(_judge_file)
```

- [ ] **Step 5: 跑全量测试确认无回归**

Run: `python -m pytest tests/ -x -q --timeout=30 2>&1 | tail -10`
Expected: 与 Step 1 相同的通过数

- [ ] **Step 6: Commit**

```bash
git add src/dqg/core/profiles.py src/dqg/core/cli.py src/dqg/cache/llm_result_cache.py
git commit -m "refactor(distribution): profiles/cli/cache 路径推导迁移到 ResourceResolver"
```

---

### Task 4: install.sh 基础框架（非 dev 模式）

**Files:**
- Create: `install.sh`
- Test: `tests/test_install_sh.py`

- [ ] **Step 1: 写 install.sh 核心函数测试**

```python
# tests/test_install_sh.py
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"


def test_install_sh_exists_and_executable():
    assert INSTALL_SH.exists()
    assert os.access(INSTALL_SH, os.X_OK)


def test_install_sh_dry_run(tmp_path):
    """dry-run 只打印计划，不实际落盘."""
    output_root = tmp_path / "fake-home" / ".dqg"
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--dry-run",
            "--skip-pip",
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "安装计划" in result.stdout
    assert "DQG version" in result.stdout
    assert not output_root.exists(), "dry-run 不应该创建目录"


def test_install_sh_real_copy(tmp_path):
    """--skip-pip 模式下只拷资源，验证拷贝完整."""
    output_root = tmp_path / "fake-home" / ".dqg"
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--skip-pip",
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    for name in ("skills", "references", "profiles", "regression"):
        assert (output_root / name).is_dir(), f"{name} 未拷贝"
    assert (output_root / "VERSION").is_file()
    assert (output_root / "VERSION").read_text().strip() == (REPO_ROOT / "VERSION").read_text().strip()


def test_install_sh_missing_source_root_fails(tmp_path):
    """source-root 缺资源目录必须报错退出."""
    fake_source = tmp_path / "not-a-dqg-repo"
    fake_source.mkdir()
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--dry-run",
            "--skip-pip",
            "--source-root",
            str(fake_source),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "缺少必要目录" in result.stderr or "缺少必要目录" in result.stdout
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_install_sh.py -v`
Expected: FAIL（install.sh 不存在）

- [ ] **Step 3: 创建 install.sh（bash shim + 内联 Python）**

```bash
#!/usr/bin/env bash
set -euo pipefail

P="$0"
while [ -L "$P" ]; do
  D="$(cd "$(dirname "$P")" && pwd -P)"
  P="$(readlink "$P")"
  [[ "$P" != /* ]] && P="$D/$P"
done

exec python3 - "$P" "$@" <<'PYCODE'
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_RESOURCES = ["skills", "references", "profiles", "regression"]
REQUIRED_META = ["VERSION", "pyproject.toml"]


class InstallError(RuntimeError):
    pass


class RaiseArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InstallError(message)


def expand(raw: str) -> Path:
    return Path(os.path.expanduser(raw)).resolve()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = RaiseArgumentParser(
        prog="install.sh",
        description="把 DQG 资源和 Python 包安装到 ~/.dqg + site-packages",
    )
    parser.add_argument("--output-root", default="~/.dqg")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--dev", action="store_true", help="维护者模式：symlink + pip install -e")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-pip", action="store_true")
    return parser.parse_args(argv)


def ensure_source(source: Path) -> None:
    missing = [
        str(source / name)
        for name in REQUIRED_RESOURCES + REQUIRED_META
        if not (source / name).exists()
    ]
    if missing:
        raise InstallError("缺少必要目录/文件:\n- " + "\n- ".join(missing))


def read_version(source: Path) -> str:
    return (source / "VERSION").read_text().strip()


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def copy_resource(src: Path, dest_parent: Path) -> Path:
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    remove_path(dest)
    if src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
    else:
        shutil.copy2(src, dest)
    return dest


def symlink_resource(src: Path, dest_parent: Path) -> Path:
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    # 已经正确指向则跳过
    if dest.is_symlink() and Path(os.readlink(dest)) == src.resolve():
        return dest
    # 已是真实目录则拒绝（防误删）
    if dest.exists() and not dest.is_symlink():
        raise InstallError(
            f"{dest} 已是真实目录（可能之前跑过非 --dev）\n"
            f"请先手动删除再重试: rm -rf {dest}"
        )
    if dest.is_symlink():
        dest.unlink()
    os.symlink(src.resolve(), dest)
    return dest


def run_pip(source: Path, editable: bool) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "--user"]
    if editable:
        cmd.append("-e")
    cmd.append(str(source))
    print(f"\n执行: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise InstallError(f"pip install 失败，退出码 {result.returncode}")


def main() -> int:
    script_path = expand(sys.argv[1])
    args = parse_args(sys.argv[2:])

    source = expand(args.source_root) if args.source_root else script_path.parent
    ensure_source(source)
    version = read_version(source)

    output_root = expand(args.output_root)
    mode = "dev-symlink" if args.dev else "production"

    print("安装计划：")
    print(f"- 模式: {mode}")
    print(f"- 源目录: {source}")
    print(f"- DQG version: {version}")
    print(f"- 目标根: {output_root}")
    print(f"- 资源条目: {', '.join(REQUIRED_RESOURCES)}")
    print(f"- pip 安装: {'跳过' if args.skip_pip else ('editable' if args.dev else 'normal')}")

    if args.dry_run:
        print("dry-run: 不实际执行")
        return 0

    # 拷贝/链接资源
    placer = symlink_resource if args.dev else copy_resource
    for name in REQUIRED_RESOURCES:
        placer(source / name, output_root)

    # VERSION 文件（非 dev 模式也要一份，用于版本一致性检查）
    if args.dev:
        # dev 模式下 ~/.dqg/VERSION 也 symlink 回 repo，保持同步
        symlink_resource(source / "VERSION", output_root)
    else:
        shutil.copy2(source / "VERSION", output_root / "VERSION")

    # pip 安装
    if not args.skip_pip:
        run_pip(source, editable=args.dev)

    print("\n✓ 安装完成")
    print("\n下一步：")
    print("  cd 你的项目目录")
    print("  dqg-run init")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"install.sh: {exc}", file=sys.stderr)
        raise SystemExit(1)
PYCODE
```

- [ ] **Step 4: 赋予执行权限**

Run: `chmod +x install.sh`

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_install_sh.py -v`
Expected: 4 PASS

- [ ] **Step 6: 实际 dry-run 一次做 sanity check**

Run: `./install.sh --dry-run --skip-pip --output-root /tmp/dqg-dry`
Expected: 打印安装计划包含 DQG version、不创建 /tmp/dqg-dry

- [ ] **Step 7: Commit**

```bash
git add install.sh tests/test_install_sh.py
git commit -m "feat(distribution): install.sh 基础框架 + dry-run + --dev + --skip-pip"
```

---

### Task 5: 老路径 deprecation warning

**Files:**
- Modify: `src/dqg/core/resource_resolver.py`（加 deprecation 检测）
- Test: `tests/test_resource_resolver.py`（补测试）

- [ ] **Step 1: 补 deprecation 测试**

```python
# tests/test_resource_resolver.py 追加

def test_legacy_cwd_layout_warns(tmp_path, capsys, monkeypatch):
    """cwd 同时有 src/dqg/ 和 skills/ 时打印 deprecation warning."""
    legacy = tmp_path / "legacy"
    (legacy / "src" / "dqg").mkdir(parents=True)
    (legacy / "skills").mkdir()

    resolver = ResourceResolver(
        project_root=legacy,
        global_root=tmp_path / "empty-global",
    )
    resolver.check_legacy_layout()

    captured = capsys.readouterr()
    assert "deprecat" in captured.err.lower() or "deprecat" in captured.out.lower()


def test_non_legacy_layout_no_warn(tmp_path, capsys):
    """正常用户项目不触发 warning."""
    project = tmp_path / "user-project"
    project.mkdir()
    resolver = ResourceResolver(
        project_root=project,
        global_root=tmp_path / "empty-global",
    )
    resolver.check_legacy_layout()
    captured = capsys.readouterr()
    assert "deprecat" not in captured.err.lower()
    assert "deprecat" not in captured.out.lower()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_resource_resolver.py::test_legacy_cwd_layout_warns -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现 check_legacy_layout**

追加到 `src/dqg/core/resource_resolver.py`：

```python
import sys
import warnings


class ResourceResolver:
    # ... 已有代码 ...

    def check_legacy_layout(self) -> None:
        """检测 cwd 是否还是老的 DQG repo 内布局，打印 deprecation warning."""
        legacy_signals = [
            self.project_root / "src" / "dqg",
            self.project_root / "skills",
        ]
        if all(p.exists() for p in legacy_signals):
            print(
                "\n⚠️  DEPRECATION: 检测到 cwd 仍在 DQG repo 内布局运行。\n"
                "   未来版本将移除此兼容路径，请按 docs/migration-from-0.1.md 迁移：\n"
                "   1. 在家目录外新建你的项目工作区\n"
                "   2. cd 到工作区后运行 dqg-run init\n"
                "   此警告保留 3 个月，然后会升级为 error。\n",
                file=sys.stderr,
            )
```

- [ ] **Step 4: 挂到 runner 入口**

修改 `src/dqg/core/runner.py` 的 `main()`，在派发前调一次：

```python
# src/dqg/core/runner.py main() 内部靠近顶部
from dqg.core.resource_resolver import ResourceResolver
ResourceResolver().check_legacy_layout()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_resource_resolver.py -v`
Expected: 全 PASS

- [ ] **Step 6: 手工 sanity check**

```bash
# 在 DQG repo 根跑，应该看到 warning
python -m dqg.core.runner status 2>&1 | head -10
```

Expected: stderr 有 "DEPRECATION" 字样

- [ ] **Step 7: Commit**

```bash
git add src/dqg/core/resource_resolver.py src/dqg/core/runner.py tests/test_resource_resolver.py
git commit -m "feat(distribution): cwd 内老布局 deprecation warning（3 个月兼容期）"
```

---

### Task 6: 第一批里程碑 — install.sh 端到端验证

**Files:**
- Test: 仅手工验证，不写新测试

- [ ] **Step 1: 清理潜在的老 ~/.dqg**

```bash
ls ~/.dqg 2>&1 | head -5
# 如果有内容且是 dev 环境遗留，确认没有重要东西后:
# mv ~/.dqg ~/.dqg.bak.before-migration
```

Expected: 你确认可删或可备份

- [ ] **Step 2: 在隔离目录跑完整 install.sh**

```bash
./install.sh --dev
ls -la ~/.dqg
```

Expected:
- `~/.dqg/skills/` 是 symlink 指向 `<repo>/skills`
- `~/.dqg/references/`、`~/.dqg/profiles/`、`~/.dqg/regression/`、`~/.dqg/VERSION` 同理
- `pip show dev-quality-gate` 显示 editable install

- [ ] **Step 3: 验证 dqg-run 能读 ~/.dqg 资源**

```bash
cd /tmp
mkdir -p test-user-project && cd test-user-project
# 此时 cwd 里没有 src/dqg/
ls  # 应该只有自己放的内容
python -c "from dqg.core.resource_resolver import ResourceResolver; r = ResourceResolver(); print(r.resolve_dir('profiles'))"
```

Expected: 打印 `~/.dqg/profiles` 路径

- [ ] **Step 4: 第一批验收清单手工确认**

- [ ] `./install.sh --dry-run` 输出包含 "DQG version" 和 "安装计划"
- [ ] `./install.sh --dev` 在 repo 根执行后，改 `skills/` 文件立即在 `~/.dqg/skills/` 可见
- [ ] `dqg-run --version` 返回 VERSION 文件内容
- [ ] 在 DQG repo 内跑任意 dqg-run 子命令能看到 deprecation warning
- [ ] 在 /tmp/test-user-project 跑 `dqg-run` 能读到 ~/.dqg 资源不报错

- [ ] **Step 5: Commit 里程碑标记**

```bash
git commit --allow-empty -m "chore(distribution): 第一批里程碑 · 物理边界完成"
```

---

## 第二批 · 用户工作区

### Task 7: settings.yaml 加载器 + 版本一致性

**Files:**
- Create: `src/dqg/core/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写 settings 加载测试**

```python
# tests/test_settings.py
from pathlib import Path
import pytest

from dqg.core.settings import DqgSettings, load_settings, check_version_drift


def test_load_settings_minimal(tmp_path):
    settings_file = tmp_path / ".dqg" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text(
        "dqg_version: \"0.2.0\"\n"
        "profile: java-ddd\n"
        "code_repos:\n"
        "  - /path/to/repo1\n"
    )
    s = load_settings(tmp_path)
    assert s.dqg_version == "0.2.0"
    assert s.profile == "java-ddd"
    assert s.code_repos == ["/path/to/repo1"]


def test_load_settings_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path)


def test_version_drift_matching(tmp_path, monkeypatch):
    settings_file = tmp_path / ".dqg" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text("dqg_version: \"0.2.0\"\nprofile: java-ddd\ncode_repos: []\n")
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift is None


def test_version_drift_mismatch(tmp_path):
    settings_file = tmp_path / ".dqg" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text("dqg_version: \"0.1.9\"\nprofile: java-ddd\ncode_repos: []\n")
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift == ("0.1.9", "0.2.0")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 settings.py**

```python
# src/dqg/core/settings.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DqgSettings:
    dqg_version: str
    profile: str = "java-ddd"
    code_repos: list[str] = field(default_factory=list)


def load_settings(project_root: Path) -> DqgSettings:
    path = project_root / ".dqg" / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Not a DQG project workspace: {path} missing. 先跑 `dqg-run init`")
    data = yaml.safe_load(path.read_text()) or {}
    return DqgSettings(
        dqg_version=str(data.get("dqg_version", "")),
        profile=str(data.get("profile", "java-ddd")),
        code_repos=list(data.get("code_repos") or []),
    )


def check_version_drift(project_root: Path, installed_version: str) -> tuple[str, str] | None:
    """返回 (pinned, installed) 如不一致，None 表一致."""
    try:
        s = load_settings(project_root)
    except FileNotFoundError:
        return None
    if s.dqg_version and s.dqg_version != installed_version:
        return (s.dqg_version, installed_version)
    return None
```

- [ ] **Step 4: 确认 pyyaml 依赖**

检查 `pyproject.toml` 里是否已有 pyyaml。如果没有：

```toml
# pyproject.toml [project] dependencies 追加
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
]
```

- [ ] **Step 5: 跑测试确认通过**

Run: `pip install -e . && python -m pytest tests/test_settings.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/core/settings.py tests/test_settings.py pyproject.toml
git commit -m "feat(distribution): .dqg/settings.yaml 加载器 + 版本一致性检查"
```

---

### Task 8: dqg-run init 命令

**Files:**
- Create: `src/dqg/commands/init.py`
- Modify: `src/dqg/core/runner.py`（注册 init 子命令）
- Test: `tests/test_init_cmd.py`

- [ ] **Step 1: 写 init 测试**

```python
# tests/test_init_cmd.py
from pathlib import Path

import pytest

from dqg.commands.init import run_init, GUARDRAIL_BEGIN, GUARDRAIL_END


def test_init_creates_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=False)
    assert rc == 0
    assert (tmp_path / ".dqg" / "output").is_dir()
    settings = (tmp_path / ".dqg" / "settings.yaml").read_text()
    assert "profile: java-ddd" in settings
    assert "dqg_version:" in settings
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert GUARDRAIL_BEGIN in claude_md
    assert GUARDRAIL_END in claude_md


def test_init_idempotent_claude_md(tmp_path):
    """重跑 init --force 时 CLAUDE.md marker 节被替换而非重复追加."""
    (tmp_path / "CLAUDE.md").write_text("# 我的原始 CLAUDE.md\n\n已有内容\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    first = (tmp_path / "CLAUDE.md").read_text()
    run_init(project_root=tmp_path, profile="java-ddd", force=True)
    second = (tmp_path / "CLAUDE.md").read_text()
    # 原始内容保留
    assert "# 我的原始 CLAUDE.md" in second
    assert "已有内容" in second
    # marker 只出现一次
    assert second.count(GUARDRAIL_BEGIN) == 1
    assert second.count(GUARDRAIL_END) == 1


def test_init_refuses_existing_without_force(tmp_path):
    (tmp_path / ".dqg").mkdir()
    rc = run_init(project_root=tmp_path, profile="java-ddd", force=False)
    assert rc != 0


def test_init_appends_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert ".dqg/output/" in content
    # 原有内容保留
    assert "node_modules/" in content


def test_init_creates_gitignore_if_absent(tmp_path):
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert ".dqg/output/" in content


def test_init_skips_duplicate_gitignore_entry(tmp_path):
    (tmp_path / ".gitignore").write_text(".dqg/output/\n")
    run_init(project_root=tmp_path, profile="java-ddd", force=False)
    content = (tmp_path / ".gitignore").read_text()
    assert content.count(".dqg/output/") == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_init_cmd.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 init 命令**

```python
# src/dqg/commands/init.py
from __future__ import annotations

import shutil
from importlib.metadata import version as _version
from pathlib import Path


GUARDRAIL_BEGIN = "<!-- DQG-GUARDRAIL-BEGIN -->"
GUARDRAIL_END = "<!-- DQG-GUARDRAIL-END -->"

_GUARDRAIL_BODY = """## DQG 使用规约

DQG 是通过 install.sh 安装的工具，**不要修改它的源码**。

遇到 DQG 报错时：
1. 跑 `dqg-run doctor` 生成 issue bundle
2. 把 bundle 提交给 DQG 维护者

相关资源：
- `dqg-run --help` — CLI 完整参数
- `dqg-run path <skills|references|profiles>` — 查看内置资源"""


def _settings_yaml(profile: str, dqg_version: str) -> str:
    return (
        f"# DQG 项目配置 — 由 dqg-run init 生成\n"
        f"dqg_version: \"{dqg_version}\"   # 自动写入，勿手改\n"
        f"profile: {profile}\n"
        f"code_repos: []   # 填写代码仓绝对路径\n"
    )


def _inject_guardrail(claude_md: Path) -> None:
    marker_block = f"\n{GUARDRAIL_BEGIN}\n{_GUARDRAIL_BODY}\n{GUARDRAIL_END}\n"
    if not claude_md.exists():
        claude_md.write_text(marker_block.lstrip("\n"))
        return
    content = claude_md.read_text()
    if GUARDRAIL_BEGIN in content and GUARDRAIL_END in content:
        # 替换已有块
        before, _, rest = content.partition(GUARDRAIL_BEGIN)
        _, _, after = rest.partition(GUARDRAIL_END)
        # before 尾部和 after 头部的换行由 marker_block 统一重置
        new_content = before.rstrip() + "\n" + marker_block + after.lstrip()
        claude_md.write_text(new_content)
    else:
        sep = "" if content.endswith("\n") else "\n"
        claude_md.write_text(content + sep + marker_block)


def _append_gitignore(gitignore: Path, entry: str) -> None:
    if not gitignore.exists():
        gitignore.write_text(entry + "\n")
        return
    content = gitignore.read_text()
    lines = content.splitlines()
    if entry in lines:
        return
    sep = "" if content.endswith("\n") else "\n"
    gitignore.write_text(content + sep + entry + "\n")


def run_init(project_root: Path, profile: str, force: bool) -> int:
    dqg_root = project_root / ".dqg"
    if dqg_root.exists() and not force:
        print(f"错误: {dqg_root} 已存在。使用 --force 覆盖（会删除原有 .dqg/ 及其 code_repos 配置）")
        return 1
    if dqg_root.exists() and force:
        print(f"⚠️  --force 模式将删除 {dqg_root}")
        shutil.rmtree(dqg_root)

    (dqg_root / "output").mkdir(parents=True)
    try:
        dqg_version = _version("dev-quality-gate")
    except Exception:
        dqg_version = "unknown"
    (dqg_root / "settings.yaml").write_text(_settings_yaml(profile, dqg_version))

    _inject_guardrail(project_root / "CLAUDE.md")
    _append_gitignore(project_root / ".gitignore", ".dqg/output/")

    print("✓ .dqg/ 工作区已创建")
    print("✓ CLAUDE.md guardrail 已注入")
    print("✓ .gitignore 已追加 .dqg/output/")
    print("\n下一步：")
    print("  1. 编辑 .dqg/settings.yaml 填写 code_repos")
    print("  2. 运行 dqg-run <project_id> startup 开始")
    return 0
```

- [ ] **Step 4: 在 runner.py 注册 init 子命令**

修改 `src/dqg/core/runner.py` 的 `_build_parser()`，在现有子命令后追加：

```python
init_p = subparsers.add_parser("init", help="在当前目录初始化 .dqg/ 工作区")
init_p.add_argument("--profile", default="java-ddd", help="默认 profile")
init_p.add_argument("--force", action="store_true", help="删除已有 .dqg/ 重建")
```

以及 `_dispatch` 函数新增分支：

```python
if cmd == "init":
    from dqg.commands.init import run_init
    from pathlib import Path
    def _run(args):
        return run_init(Path.cwd(), args.profile, args.force)
    return _run
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_init_cmd.py -v`
Expected: 6 PASS

- [ ] **Step 6: 手工 sanity check**

```bash
mkdir -p /tmp/test-init && cd /tmp/test-init
dqg-run init
ls -la .dqg/
cat .dqg/settings.yaml
cat CLAUDE.md
cat .gitignore
```

Expected: 全部符合预期

- [ ] **Step 7: Commit**

```bash
git add src/dqg/commands/init.py src/dqg/core/runner.py tests/test_init_cmd.py
git commit -m "feat(distribution): dqg-run init 建 .dqg/ 工作区 + 注入 CLAUDE.md guardrail"
```

---

### Task 9: dqg-run path 只读查看内置资源

**Files:**
- Create: `src/dqg/commands/path_cmd.py`
- Modify: `src/dqg/core/runner.py`（注册 path 子命令）

- [ ] **Step 1: 写 path 命令测试**

```python
# tests/test_path_cmd.py
import pytest
from dqg.commands.path_cmd import run_path


def test_path_skills(tmp_path, capsys, monkeypatch):
    global_dqg = tmp_path / "home" / ".dqg"
    (global_dqg / "skills" / "Q01").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    rc = run_path("skills")
    assert rc == 0
    captured = capsys.readouterr()
    assert str(global_dqg / "skills") in captured.out


def test_path_unknown_category():
    rc = run_path("unknown-category")
    assert rc != 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_path_cmd.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 path 命令**

```python
# src/dqg/commands/path_cmd.py
from __future__ import annotations

from dqg.core.resource_resolver import ResourceResolver


_ALLOWED = {"skills", "references", "profiles", "regression"}


def run_path(category: str) -> int:
    if category not in _ALLOWED:
        print(f"错误: 未知类别 '{category}'。可用: {', '.join(sorted(_ALLOWED))}")
        return 1
    try:
        path = ResourceResolver().resolve_dir(category)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        return 2
    print(path)
    return 0
```

- [ ] **Step 4: 在 runner.py 注册 path 子命令**

```python
path_p = subparsers.add_parser("path", help="打印内置资源目录的绝对路径（只读）")
path_p.add_argument("category", choices=sorted(["skills", "references", "profiles", "regression"]))
```

_dispatch 分支：

```python
if cmd == "path":
    from dqg.commands.path_cmd import run_path
    def _run(args):
        return run_path(args.category)
    return _run
```

- [ ] **Step 5: 跑测试**

Run: `python -m pytest tests/test_path_cmd.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/commands/path_cmd.py src/dqg/core/runner.py tests/test_path_cmd.py
git commit -m "feat(distribution): dqg-run path <category> 只读查看内置资源"
```

---

### Task 10: 版本一致性启动 warning

**Files:**
- Modify: `src/dqg/core/runner.py`（main 入口检测 drift）

- [ ] **Step 1: 写启动 warning 测试**

```python
# tests/test_version_drift_warning.py
import subprocess
from pathlib import Path

import pytest


def test_drift_warning_prints(tmp_path, monkeypatch):
    """构造 settings.yaml 版本与 installed 不同时跑 dqg-run，应看到 warning."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dqg").mkdir()
    (tmp_path / ".dqg" / "settings.yaml").write_text(
        "dqg_version: \"0.0.1-ancient\"\nprofile: java-ddd\ncode_repos: []\n"
    )
    # 跑最轻量命令：help，但要 main() 走到 drift check
    result = subprocess.run(
        ["dqg-run", "status", "--json"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    # 非零退出码也行（.dqg 未完整），但 stderr 应该出现 drift warning
    assert "0.0.1-ancient" in result.stderr or "version" in result.stderr.lower()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_version_drift_warning.py -v`
Expected: FAIL

- [ ] **Step 3: 在 runner.main 加 drift 检测**

```python
# src/dqg/core/runner.py main() 靠近 check_legacy_layout() 的地方追加

def _check_version_drift(cwd: Path) -> None:
    import sys
    from importlib.metadata import version as _v
    from dqg.core.settings import check_version_drift
    try:
        installed = _v("dev-quality-gate")
    except Exception:
        return
    drift = check_version_drift(cwd, installed)
    if drift:
        pinned, running = drift
        print(
            f"\n⚠️  版本漂移: settings.yaml pin 的 {pinned} 与安装的 {running} 不一致\n"
            f"   建议运行: dqg-run init --force 同步（注意会清空 code_repos）\n"
            f"   或手动修改 .dqg/settings.yaml 的 dqg_version 字段\n",
            file=sys.stderr,
        )


def main() -> int:
    # ... 现有代码 ...
    from pathlib import Path
    from dqg.core.resource_resolver import ResourceResolver
    ResourceResolver().check_legacy_layout()
    _check_version_drift(Path.cwd())
    # ... 后续派发 ...
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_version_drift_warning.py -v`
Expected: PASS

- [ ] **Step 5: 第二批里程碑验收**

- [ ] `dqg-run init` 在空项目建出 `.dqg/output/` + settings.yaml + 注入 CLAUDE.md
- [ ] 重跑 `dqg-run init --force` CLAUDE.md guardrail 只有一份
- [ ] `dqg-run path skills` 打印 `~/.dqg/skills` 绝对路径
- [ ] 用户项目里改 settings.yaml 的 dqg_version 后跑 dqg-run 看到漂移 warning

- [ ] **Step 6: Commit**

```bash
git add src/dqg/core/runner.py tests/test_version_drift_warning.py
git commit -m "feat(distribution): 启动时版本漂移 warning"
git commit --allow-empty -m "chore(distribution): 第二批里程碑 · 用户工作区完成"
```

---

## 第三批 · doctor

### Task 11: last-run marker

**Files:**
- Create: `src/dqg/core/last_run.py`
- Modify: `src/dqg/core/runner.py`
- Test: `tests/test_last_run.py`

- [ ] **Step 1: 写 last-run 测试**

```python
# tests/test_last_run.py
import json
from pathlib import Path

from dqg.core.last_run import write_last_run, read_last_run


def test_write_then_read(tmp_path):
    write_last_run(
        project_root=tmp_path,
        cmd=["dqg-run", "status"],
        exit_code=0,
        stderr_tail="",
    )
    data = read_last_run(tmp_path)
    assert data["cmd"] == ["dqg-run", "status"]
    assert data["exit_code"] == 0
    assert "ts" in data
    assert "cwd" in data


def test_read_missing_returns_none(tmp_path):
    assert read_last_run(tmp_path) is None


def test_atomic_write_no_partial_file(tmp_path):
    """中断不应留下损坏的 JSON."""
    write_last_run(tmp_path, ["dqg-run", "x"], 0, "")
    path = tmp_path / ".dqg" / "last-run.json"
    # 必须能严格 JSON 解析
    json.loads(path.read_text())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_last_run.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 last_run.py**

```python
# src/dqg/core/last_run.py
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


_LAST_RUN = ".dqg/last-run.json"


def write_last_run(
    project_root: Path,
    cmd: list[str],
    exit_code: int,
    stderr_tail: str,
) -> None:
    target_dir = project_root / ".dqg"
    if not target_dir.exists():
        # 没有 .dqg/ 工作区就不写，避免污染用户目录
        return
    path = project_root / _LAST_RUN
    tmp = path.with_suffix(".tmp")
    payload: dict[str, Any] = {
        "cmd": cmd,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "cwd": str(project_root),
        "exit_code": exit_code,
        "stderr_tail": stderr_tail[-4096:],
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def read_last_run(project_root: Path) -> dict[str, Any] | None:
    path = project_root / _LAST_RUN
    if not path.exists():
        return None
    return json.loads(path.read_text())
```

- [ ] **Step 4: 在 runner.main 末尾写 last-run**

修改 `src/dqg/core/runner.py` 的 `main()`，在 return exit_code 前捕获：

```python
def main() -> int:
    import sys
    from pathlib import Path
    from dqg.core.last_run import write_last_run
    # ... 现有代码，得到 exit_code ...
    try:
        write_last_run(
            project_root=Path.cwd(),
            cmd=sys.argv,
            exit_code=int(exit_code or 0),
            stderr_tail="",  # 第一版留空；捕获 stderr tail 属后续增强
        )
    except Exception:
        pass  # marker 写失败不影响主流程
    return exit_code
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_last_run.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dqg/core/last_run.py src/dqg/core/runner.py tests/test_last_run.py
git commit -m "feat(distribution): last-run marker atomic write"
```

---

### Task 12: doctor bundle 生成 + 脱敏

**Files:**
- Create: `src/dqg/commands/doctor.py`
- Test: `tests/test_doctor_cmd.py`

- [ ] **Step 1: 写 bundle 测试**

```python
# tests/test_doctor_cmd.py
import json
import tarfile
from pathlib import Path

import pytest

from dqg.commands.doctor import (
    build_bundle,
    redact_text,
    check_version_consistency,
)


@pytest.fixture
def project_with_state(tmp_path):
    (tmp_path / ".dqg").mkdir()
    (tmp_path / ".dqg" / "settings.yaml").write_text(
        "dqg_version: \"0.2.0\"\nprofile: java-ddd\ncode_repos:\n  - /abs/path\n"
    )
    (tmp_path / ".dqg" / "last-run.json").write_text(
        json.dumps({"cmd": ["dqg-run", "status"], "exit_code": 1, "ts": "t", "cwd": str(tmp_path), "stderr_tail": "boom"})
    )
    output = tmp_path / ".dqg" / "output" / "proj1"
    output.mkdir(parents=True)
    (output / "state.json").write_text("{}")
    (output / "Q01" / "_internal").mkdir(parents=True)
    (output / "Q01" / "_internal" / "_reasoning_log.md").write_text("# log")
    return tmp_path


def test_build_bundle_contains_required_members(project_with_state, tmp_path):
    out = tmp_path / "bundle.tgz"
    build_bundle(project_root=project_with_state, output=out, redact=True, include_internal=True)
    assert out.exists()
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert any(n.endswith("manifest.json") for n in names)
    assert any(n.endswith("env.txt") for n in names)
    assert any(n.endswith("settings.yaml") for n in names)
    assert any("recent-errors" in n for n in names)
    assert any("_reasoning_log.md" in n for n in names)


def test_redact_username_in_paths():
    raw = "error at /Users/zhang3/code/app.py line 42"
    out = redact_text(raw)
    assert "/Users/zhang3" not in out
    assert "<user>" in out


def test_redact_token_prefixes():
    for prefix in ("sk-abc123xyz", "claude-key-xxx", "Bearer token-long"):
        assert "***" in redact_text(prefix)


def test_version_consistency_mismatch_flag(project_with_state):
    (project_with_state / ".dqg" / "settings.yaml").write_text(
        "dqg_version: \"0.0.1\"\nprofile: java-ddd\ncode_repos: []\n"
    )
    (Path.home() / ".dqg").mkdir(exist_ok=True)
    # 不真的改家目录 VERSION；传 override
    result = check_version_consistency(
        project_root=project_with_state,
        global_version="0.2.0",
        installed_version="0.2.0",
    )
    assert result["mismatch"] is True
    assert result["settings"] == "0.0.1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_doctor_cmd.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 doctor 的 bundle + 脱敏部分**

```python
# src/dqg/commands/doctor.py
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from importlib.metadata import version as _version
from pathlib import Path
from typing import Any


_TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{6,}"),
    re.compile(r"claude-[A-Za-z0-9_-]{6,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_.-]{6,}"),
]


def redact_text(text: str) -> str:
    # 绝对路径里的 username
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
            capture_output=True, text=True, timeout=20,
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
    settings_version = ""
    settings_path = project_root / ".dqg" / "settings.yaml"
    if settings_path.exists():
        for line in settings_path.read_text().splitlines():
            if line.strip().startswith("dqg_version:"):
                settings_version = line.split(":", 1)[1].strip().strip('"').strip("'")
                break
    if global_version is None:
        g = Path.home() / ".dqg" / "VERSION"
        global_version = g.read_text().strip() if g.exists() else ""
    if installed_version is None:
        try:
            installed_version = _version("dev-quality-gate")
        except Exception:
            installed_version = ""
    versions = {settings_version, global_version, installed_version} - {""}
    return {
        "settings": settings_version,
        "global": global_version,
        "installed": installed_version,
        "mismatch": len(versions) > 1,
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
            internal = phase / "_internal"
            if internal.is_dir():
                picks.extend(internal.iterdir())
    # 最近修改的 20 个
    picks.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return picks[:20]


def build_bundle(
    project_root: Path,
    output: Path,
    redact: bool,
    include_internal: bool,
) -> None:
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

        # settings.yaml
        settings = project_root / ".dqg" / "settings.yaml"
        if settings.exists():
            raw = settings.read_text()
            (staging / "settings.yaml").write_text(redact_text(raw) if redact else raw)

        # last-run
        last_run = project_root / ".dqg" / "last-run.json"
        (staging / "recent-errors").mkdir()
        if last_run.exists():
            raw = last_run.read_text()
            (staging / "recent-errors" / "last-run.json").write_text(
                redact_text(raw) if redact else raw
            )

        # state.json
        output_root = project_root / ".dqg" / "output"
        if output_root.exists():
            for proj in output_root.iterdir():
                sj = proj / "state.json"
                if sj.exists():
                    raw = sj.read_text()
                    (staging / f"state-{proj.name}.json").write_text(
                        redact_text(raw) if redact else raw
                    )

        # _internal
        if include_internal:
            dest = staging / "_internal"
            dest.mkdir()
            for f in _recent_output_internal(project_root):
                raw = f.read_text(errors="ignore") if f.suffix in {".md", ".json", ".txt"} else None
                if raw is not None:
                    out = dest / f"{f.parent.parent.name}-{f.name}"
                    out.write_text(redact_text(raw) if redact else raw)

        # input-summary
        lines = []
        for proj in (project_root / ".dqg" / "output").glob("*"):
            for f in proj.rglob("*"):
                if f.is_file():
                    lines.append(f"{f.relative_to(project_root)}\t{f.stat().st_size}")
        (staging / "input-summary.txt").write_text("\n".join(lines[:500]))

        # 打包
        with tarfile.open(output, "w:gz") as tar:
            tar.add(staging, arcname="doctor-bundle")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_doctor_cmd.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/dqg/commands/doctor.py tests/test_doctor_cmd.py
git commit -m "feat(distribution): doctor bundle 生成 + 脱敏 + 版本一致性"
```

---

### Task 13: doctor 的 glab 上传 + fallback

**Files:**
- Modify: `src/dqg/commands/doctor.py`（加 upload 函数和主入口）
- Modify: `src/dqg/core/runner.py`（注册 doctor 子命令）
- Test: `tests/test_doctor_upload.py`

- [ ] **Step 1: 写 upload 测试**

```python
# tests/test_doctor_upload.py
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from dqg.commands.doctor import (
    detect_glab,
    upload_via_glab,
    parse_issue_url_from_stdout,
    resolve_issues_url,
)


def test_detect_glab_absent(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert detect_glab() == (False, "glab not on PATH")


def test_parse_issue_url():
    out = "creating issue...\nhttps://github.com/your-org/rd-gate/-/issues/42\n"
    assert parse_issue_url_from_stdout(out) == "https://github.com/your-org/rd-gate/-/issues/42"


def test_parse_issue_url_none():
    assert parse_issue_url_from_stdout("no url here") is None


def test_resolve_issues_url_from_metadata():
    # 从已安装包的 Project-URL 里解析 repo 路径
    url = resolve_issues_url()
    assert url.endswith("/-/issues") or url.endswith("/issues")


@patch("subprocess.run")
def test_upload_via_glab_success(mock_run, tmp_path):
    bundle = tmp_path / "b.tgz"
    bundle.write_bytes(b"x")
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="created: https://github.com/your-org/rd-gate/-/issues/7\n",
        stderr="",
    )
    ok, url, err = upload_via_glab(
        title="t", description="d", bundle=bundle,
        repo_path="nr-car-service/dev-quality-gate", timeout=5,
    )
    assert ok
    assert url and "issues/7" in url
    assert err == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_doctor_upload.py -v`
Expected: FAIL

- [ ] **Step 3: 追加 upload 实现到 doctor.py**

```python
# src/dqg/commands/doctor.py 追加

import re
import shutil
import subprocess
from importlib.metadata import metadata as _metadata
from urllib.parse import urlparse


_ISSUE_URL_PATTERN = re.compile(r"https://[^\s]+/-?/?issues/\d+")


def detect_glab() -> tuple[bool, str]:
    if not shutil.which("glab"):
        return False, "glab not on PATH"
    try:
        r = subprocess.run(
            ["glab", "auth", "status"],
            capture_output=True, text=True, timeout=10,
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
        return "https://github.com/your-org/rd-gate/-/issues"
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() == "issues":
            return url.strip()
    return "https://github.com/your-org/rd-gate/-/issues"


def _repo_path_from_url(url: str) -> str:
    parsed = urlparse(url)
    # 去掉 leading / 和尾部的 /-/issues（或 /issues）
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
    """返回 (成功与否, issue URL, 错误信息)."""
    cmd = [
        "glab", "issue", "create",
        "--repo", repo_path,
        "--title", title,
        "--description", description,
    ]
    # 新版 glab 支持 --file；兜底：失败时 fallback 到"创建后单独附件上传"
    try:
        r = subprocess.run(
            cmd + ["--file", str(bundle)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, None, "glab timeout"
    if r.returncode == 0:
        return True, parse_issue_url_from_stdout(r.stdout), ""
    # 旧版不支持 --file：重试无 --file
    try:
        r2 = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, None, "glab timeout"
    if r2.returncode != 0:
        return False, None, r2.stderr.strip() or r.stderr.strip()
    issue_url = parse_issue_url_from_stdout(r2.stdout)
    # 附件 fallback：提示用户手动贴
    return True, issue_url, "warning: 旧版 glab 不支持 --file，bundle 需手动上传到上面的 issue"


def run_doctor(
    project_root: Path,
    output: Path | None,
    redact: bool,
    include_internal: bool,
    no_upload: bool,
    title: str | None,
) -> int:
    if not redact and not no_upload:
        print("错误: --no-redact 与上传互斥。请加 --no-upload 或去掉 --no-redact。", file=sys.stderr)
        return 2
    if output is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output = project_root / ".dqg" / f"doctor-bundle-{ts}.tgz"
    build_bundle(project_root, output, redact=redact, include_internal=include_internal)
    print(f"✓ Bundle 已生成: {output} ({output.stat().st_size // 1024} KB)")

    consistency = check_version_consistency(project_root)
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
        print(f"\n--no-upload 已指定。上传到 {issues_url}")
        return 0

    ok, reason = detect_glab()
    if not ok:
        print(f"\n⚠ {reason}")
        print(f"  bundle 已生成，请手动上传到: {issues_url}")
        print("  安装 glab 后可启用自动上传: brew install glab && glab auth login")
        return 0

    if title is None:
        if sys.stdin.isatty():
            title = input("issue 标题: ").strip() or "[doctor] DQG error report"
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
        return 0
    print(f"⚠ 上传失败: {warn}")
    print(f"  bundle 仍保留于: {output}")
    print(f"  可手动上传到: {issues_url}")
    return 2
```

- [ ] **Step 4: 在 runner.py 注册 doctor 子命令**

```python
doctor_p = subparsers.add_parser("doctor", help="生成 issue bundle 并（可选）自动上传")
doctor_p.add_argument("--output", default=None)
doctor_p.add_argument("--redact", action="store_true", default=True)
doctor_p.add_argument("--no-redact", dest="redact", action="store_false")
doctor_p.add_argument("--include-internal", action="store_true", default=True)
doctor_p.add_argument("--no-include-internal", dest="include_internal", action="store_false")
doctor_p.add_argument("--no-upload", action="store_true")
doctor_p.add_argument("--title", default=None)
```

dispatch:

```python
if cmd == "doctor":
    from dqg.commands.doctor import run_doctor
    from pathlib import Path
    def _run(args):
        return run_doctor(
            project_root=Path.cwd(),
            output=Path(args.output) if args.output else None,
            redact=args.redact,
            include_internal=args.include_internal,
            no_upload=args.no_upload,
            title=args.title,
        )
    return _run
```

- [ ] **Step 5: 跑 upload 测试通过**

Run: `python -m pytest tests/test_doctor_upload.py -v`
Expected: PASS

- [ ] **Step 6: 手工 sanity check（无 glab 场景）**

```bash
cd /tmp/test-init  # Task 8 的目录
PATH=/usr/bin:/bin dqg-run doctor --no-upload
```

Expected: bundle 生成，打印 issue URL，退出 0

- [ ] **Step 7: Commit**

```bash
git add src/dqg/commands/doctor.py src/dqg/core/runner.py tests/test_doctor_upload.py
git commit -m "feat(distribution): doctor 借助 glab 自动上传 + fallback 手动"
```

---

### Task 14: 迁移文档

**Files:**
- Create: `docs/migration-from-0.1.md`

- [ ] **Step 1: 写迁移文档**

```markdown
# DQG 0.1 → 0.2 迁移指南

> 0.2 引入了工具化分发边界：DQG 源码与你的项目物理隔离。

## 变化

- DQG 源码不再在你的 cwd 下；通过 `pip install --user` 装到 site-packages
- 资源（skills/references/profiles/regression）拷贝到 `~/.dqg/`
- 你的项目下新建 `.dqg/` 工作区（output + settings）
- `CLAUDE.md` 会被追加一段 DQG 使用规约（marker 包裹）

## 从 0.1 迁移步骤

### 1. 安装新版 DQG

```bash
cd <DQG repo 目录>
git pull
./install.sh            # 非 dev 用户
# 或
./install.sh --dev      # 你是 DQG 维护者
```

### 2. 在你的项目目录初始化工作区

```bash
cd <你的项目目录>
dqg-run init
```

这会创建：
- `.dqg/output/` — 运行输出写这里
- `.dqg/settings.yaml` — profile、code_repos 等
- `.gitignore` 追加 `.dqg/output/`
- `CLAUDE.md` 追加 guardrail 段落

### 3. 迁移自定义配置（如果有）

| 0.1 放哪里 | 0.2 放哪里 |
|-----------|------------|
| DQG repo 下 `profiles/your-profile/` | `<你的项目>/.dqg/profiles/your-profile/` |
| DQG repo 下你改过的 skills 片段 | `<你的项目>/.dqg/skill-overrides/` |
| DQG repo 下 `output/<pid>/` | `<你的项目>/.dqg/output/<pid>/` |

`.dqg/profiles/` 和 `.dqg/skill-overrides/` 子目录 `init` 不会预建；有需要手动 `mkdir` 后放进去，ResourceResolver 会自动检测并优先使用。

### 4. 填写 settings.yaml 的 code_repos

```yaml
code_repos:
  - /absolute/path/to/your-service
```

### 5. 验证

```bash
dqg-run status --json
```

Expected: 正常输出，无 deprecation warning。

## 常见问题

### deprecation warning 出现

表示 cwd 里仍有 `src/dqg/` 和 `skills/` 共存的老布局。按上面步骤换到新工作区。3 个月后 warning 升级为 error。

### `~/.dqg/` 要不要手动清理

重跑 `./install.sh` 会覆盖资源目录，不会删额外文件。要彻底清理运行 `rm -rf ~/.dqg`。

### 多项目复用

一次 `install.sh` 后，每个项目分别 `cd` 进去跑 `dqg-run init`，各自有独立 `.dqg/output/`，共享 `~/.dqg/` 资源。

### 如何回滚到 0.1

```bash
pip uninstall dev-quality-gate
rm -rf ~/.dqg
cd <DQG repo>
git checkout <0.1 tag>
pip install -e .
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/migration-from-0.1.md
git commit -m "docs(distribution): 0.1 → 0.2 迁移指南"
```

---

### Task 15: 第三批里程碑 + 总验收

**Files:**
- 仅手工验证 + 更新 ROADMAP

- [ ] **Step 1: 全量测试一次**

Run: `python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -10`
Expected: 全绿

- [ ] **Step 2: DoD 逐条验收**

参考 spec 的 Definition of Done 节：

- [ ] 新用户执行 `git clone && ./install.sh && cd <别的项目> && dqg-run init` 后 `<别的项目>/` 下 `ls` 看不到 DQG 源码
- [ ] `dqg-run init` 幂等：重跑不重复写 CLAUDE.md marker 节段
- [ ] `dqg-run --version` 返回 VERSION 文件内容
- [ ] `pyproject.toml` 的 version 为 dynamic，build wheel 时读 VERSION（跑 `python -m build` 验证）
- [ ] `dqg-run doctor --no-upload` 打印 bundle 路径 + issue URL，退出 0
- [ ] `dqg-run doctor`（装了 glab 且登录过）创建 issue 并打印 URL
- [ ] 老路径触发 deprecation warning 但仍可跑通 Q01
- [ ] `./install.sh --dev` 改 skills/ 文件立即在 `~/.dqg/skills/` 可见
- [ ] `./install.sh --dry-run` 输出符合 spec 第 2 节样本
- [ ] 单元测试覆盖 ResourceResolver、version、install.sh、init、doctor

- [ ] **Step 3: ROADMAP §F 状态更新**

修改 `ROADMAP.md` §F 顶部 `当前状态: 规划中（P0）` 为 `已完成（P0，2026-05-11）`，并把三批里程碑列为已完成条目。

- [ ] **Step 4: Commit 总里程碑**

```bash
git add ROADMAP.md
git commit -m "chore(distribution): 第三批里程碑 · doctor 完成，ROADMAP §F 关闭"
git commit --allow-empty -m "chore(distribution): 工具化分发全部三批完成"
```

- [ ] **Step 5: 推送到远端（可选）**

```bash
git push -u origin tools-transformation
```

Then 开 PR 合并到 main。
