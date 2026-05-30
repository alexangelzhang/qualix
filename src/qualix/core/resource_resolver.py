from __future__ import annotations

import sys
from pathlib import Path
from typing import ClassVar


class ResourceResolver:
    """四层回退资源查找：项目 .qualix/ -> ~/.qualix/ -> importlib.resources -> Qualix repo root（过渡期）."""

    _LAYER4_WARNED: ClassVar[set[str]] = set()

    def __init__(
        self,
        project_root: Path | None = None,
        global_root: Path | None = None,
    ):
        self.project_root = project_root or Path.cwd()
        self.project_qualix = self.project_root / ".qualix"
        self.global_root = global_root or (Path.home() / ".qualix")

    def _validate(self, category: str, relative: str | None = None) -> None:
        """Validate category and optional relative path against traversal attacks."""
        if "/" in category or "\\" in category or ".." in category or Path(category).is_absolute():
            raise ValueError(f"Invalid category: {category!r}")
        if relative is not None and (".." in Path(relative).parts or Path(relative).is_absolute()):
            raise ValueError(f"Invalid relative path: {relative!r}")

    @staticmethod
    def _repo_root_fallback(category: str) -> Path | None:
        """Transitional layer 4: walk up to Qualix repo root.

        3-month deprecation window during the tool-distribution migration.
        Used when project .qualix/, ~/.qualix/, and importlib.resources all miss.
        """
        candidate = Path(__file__).resolve().parents[3]
        if not (candidate / "pyproject.toml").exists():
            return None
        # claude_commands 在 repo 里存放于 .claude/commands/
        _CATEGORY_ALIASES = {
            "claude_commands": ".claude/commands",
        }
        fs_name = _CATEGORY_ALIASES.get(category, category)
        target = candidate / fs_name
        if not target.exists():
            return None
        if category not in ResourceResolver._LAYER4_WARNED:
            ResourceResolver._LAYER4_WARNED.add(category)
            print(
                f"\n⚠️  Qualix Layer-4 fallback: 从 Qualix repo 根读取 {category}/\n"
                f"   未来版本将移除此兼容路径（见 docs/migration-from-0.1.md）\n",
                file=sys.stderr,
            )
        return target

    def resolve(self, category: str, relative: str) -> Path:
        """按 项目级 -> 全局 -> 包内 -> repo root（过渡期）顺序查找，返回第一个存在的路径."""
        self._validate(category, relative)
        candidates = [
            self.project_qualix / category / relative,
            self.global_root / category / relative,
            self._package_fallback(category, relative),
        ]
        for path in candidates:
            if path and path.exists():
                return path
        # Layer 4 transitional fallback
        repo_dir = self._repo_root_fallback(category)
        if repo_dir is not None:
            layer4 = repo_dir / relative
            if layer4.exists():
                return layer4
        raise FileNotFoundError(
            f"Resource not found: {category}/{relative}\nSearched: {[str(c) for c in candidates if c]}"
        )

    def resolve_dir(self, category: str) -> Path:
        """返回某个 category 的目录，按 项目级 -> 全局 -> 包内 -> repo root（过渡期）顺序查找."""
        self._validate(category)
        candidates = [
            self.project_qualix / category,
            self.global_root / category,
            self._package_fallback_dir(category),
        ]
        for path in candidates:
            if path and path.is_dir():
                return path
        # Layer 4 transitional fallback
        repo_dir = self._repo_root_fallback(category)
        if repo_dir is not None and repo_dir.is_dir():
            return repo_dir
        raise FileNotFoundError(f"Category directory not found: {category}")

    def list_category(self, category: str) -> list[Path]:
        """列出某个 category 下所有条目（合并项目级 + 全局，项目级优先）."""
        self._validate(category)
        seen: dict[str, Path] = {}
        global_dir = self.global_root / category
        if global_dir.exists():
            for item in sorted(global_dir.iterdir()):
                if item.name != ".DS_Store":
                    seen[item.name] = item
        project_dir = self.project_qualix / category
        if project_dir.exists():
            for item in sorted(project_dir.iterdir()):
                if item.name != ".DS_Store":
                    seen[item.name] = item
        # Layer 4: only fall back to repo root when both project and global are empty
        if not seen:
            repo_dir = self._repo_root_fallback(category)
            if repo_dir is not None and repo_dir.exists():
                for item in sorted(repo_dir.iterdir()):
                    if item.name != ".DS_Store":
                        seen[item.name] = item
        return sorted(seen.values(), key=lambda p: p.name)

    def check_legacy_layout(self) -> None:
        """检测 cwd 是否仍是 Qualix repo 内布局，打印一次性 deprecation warning.

        仅当 cwd 同时存在 src/qualix/ 和 skills/ 时认为是老布局。
        """
        legacy_signals = [
            self.project_root / "src" / "qualix",
            self.project_root / "skills",
        ]
        if not all(p.exists() for p in legacy_signals):
            return
        print(
            "\n⚠️  DEPRECATION: 检测到 cwd 仍在 Qualix repo 内布局运行。\n"
            "   未来版本将移除此兼容路径，请按 docs/migration-from-0.1.md 迁移：\n"
            "   1. 在家目录外新建你的项目工作区\n"
            "   2. cd 到工作区后运行 qualix-run init\n"
            "   此警告保留 3 个月，然后会升级为 error。\n",
            file=sys.stderr,
        )

    @staticmethod
    def _package_fallback(category: str, relative: str) -> Path | None:
        try:
            from importlib.resources import files

            pkg_path = files("qualix") / category / relative
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

            pkg_path = files("qualix") / category
            if hasattr(pkg_path, "_path"):
                p = Path(str(pkg_path._path))
            else:
                p = Path(str(pkg_path))
            return p if p.is_dir() else None
        except (ModuleNotFoundError, TypeError):
            return None
