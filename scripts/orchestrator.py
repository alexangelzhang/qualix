#!/usr/bin/env python3
"""Thin wrapper — 实际逻辑已迁移至 src/dqg/orchestrator.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dqg.services.orchestrator import main  # noqa: E402

if __name__ == "__main__":
    main()
