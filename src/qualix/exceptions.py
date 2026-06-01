"""Qualix 统一异常层次.

替代 None / error list / raw exception 三种不一致的错误处理模式。
"""

from __future__ import annotations


class QualixError(Exception):
    """Qualix 基础异常."""


class PhaseError(QualixError):
    """Phase 执行相关错误."""

    def __init__(self, phase_id: str, message: str) -> None:
        self.phase_id = phase_id
        super().__init__(f"[Phase {phase_id}] {message}")


class ValidationError(QualixError):
    """结构化产物校验失败."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        summary = f"{len(errors)} validation error(s)"
        super().__init__(summary)


class StorageError(QualixError):
    """存储层错误（SQLite / 文件 I/O）."""


class ConfigError(QualixError):
    """配置错误（缺少环境变量、profile 不存在等）."""


class IngestError(QualixError):
    """文档摄入失败."""


class LLMError(QualixError):
    """LLM API 调用失败."""

    def __init__(self, model: str, message: str) -> None:
        self.model = model
        super().__init__(f"[{model}] {message}")


ISSUE_URL = "https://github.com/alexangelzhang/qualix/issues"


def format_error_hint() -> str:
    """Return a one-line hint pointing users to doctor and the issue tracker."""
    return f"Run 'qualix-run doctor' for diagnostics, or report at {ISSUE_URL}"
