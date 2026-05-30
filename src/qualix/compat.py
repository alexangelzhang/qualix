"""Backward-compatible module alias registration for sub-package splits.

Usage in a package __init__.py::

    from qualix.compat import install_module_aliases

    install_module_aliases({
        "qualix.quality.judge_runner": "qualix.quality.judge.judge_runner",
        ...
    }, __name__)
"""

from __future__ import annotations

import importlib
import sys

from qualix.log import get_logger

_log = get_logger(__name__)


def install_module_aliases(aliases: dict[str, str], package_name: str) -> None:
    """Register sys.modules aliases so old import paths keep working.

    For each alias, imports the target module and registers it under the old
    path in sys.modules. Also sets it as an attribute on the package module
    so monkeypatch-style dotted attribute access works.
    """
    package_mod = sys.modules[package_name]

    for old, new in aliases.items():
        if old not in sys.modules:
            try:
                mod = importlib.import_module(new)
            except ImportError:
                _log.warning("compat alias failed: %s -> %s", old, new, exc_info=True)
                continue
            sys.modules[old] = mod
        attr = old.rsplit(".", 1)[-1]
        if not hasattr(package_mod, attr):
            setattr(package_mod, attr, sys.modules[old])
