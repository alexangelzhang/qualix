"""Qualix 统一日志配置.

所有模块通过 `get_logger(__name__)` 获取 logger，
格式统一、级别可通过环境变量 QUALIX_LOG_LEVEL 控制。
"""

from __future__ import annotations

import logging
import os

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"
_configured = False


def _configure_once() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level_str = os.environ.get("QUALIX_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_str, logging.WARNING)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger("qualix")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """获取 Qualix 子 logger. 用法: `log = get_logger(__name__)`."""
    _configure_once()
    return logging.getLogger(name)
