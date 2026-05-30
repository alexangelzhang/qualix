#!/usr/bin/env python3
"""Thin wrapper — 实际逻辑在 src/qualix/summarize_text.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from qualix.context.summarize_text import main

if __name__ == "__main__":
    raise SystemExit(main())
