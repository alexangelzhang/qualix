"""执行上下文：Phase 执行期间的共享状态容器."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Any


@dataclass
class ExecutionContext:
    """Phase 执行期间的共享上下文.

    在 execute/finalize 的各个 handler 之间传递，
    避免每个 handler 都要重复解析 args 和构造路径。
    """

    output_dir: Path
    project_id: str
    phase_id: str
    profile_id: str = ""
    model_name: str | None = None
    code_repo: str | None = None
    code_repos: list[str] = field(default_factory=list)
    base_branch: str = "master"
    feature_branch: str = "HEAD"

    # 运行时填充
    phase_def: dict[str, Any] = field(default_factory=dict)
    phase_root: Path | None = None
    internal_dir: Path | None = None
    relevance_text: str | None = None

    # handler 间共享数据
    shared: dict[str, Any] = field(default_factory=dict)
