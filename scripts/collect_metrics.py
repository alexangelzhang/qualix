#!/usr/bin/env python3
"""Thin wrapper — 实际逻辑已迁移至 src/dqg/collect_metrics.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dqg.reporting.collect_metrics import main

if __name__ == "__main__":
    main()
