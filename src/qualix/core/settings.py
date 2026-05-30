from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class QualixSettings:
    qualix_version: str
    profile: str = "java-ddd"
    code_repos: list[str] = field(default_factory=list)


def load_settings(project_root: Path) -> QualixSettings:
    """从 <project_root>/.qualix/settings.yaml 加载配置."""
    path = project_root / ".qualix" / "settings.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Not a Qualix project workspace: {path} missing. 先跑 `qualix-run init`")
    data = yaml.safe_load(path.read_text()) or {}
    return QualixSettings(
        qualix_version=str(data.get("qualix_version", "")),
        profile=str(data.get("profile", "java-ddd")),
        code_repos=list(data.get("code_repos") or []),
    )


def check_version_drift(project_root: Path, installed_version: str) -> tuple[str, str] | None:
    """返回 (pinned, installed) 如不一致；None 表一致或未初始化."""
    try:
        s = load_settings(project_root)
    except FileNotFoundError:
        return None
    if s.qualix_version and s.qualix_version != installed_version:
        return (s.qualix_version, installed_version)
    return None
