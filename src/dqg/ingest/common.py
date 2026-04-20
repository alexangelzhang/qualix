from __future__ import annotations

import re
import sys
from types import MappingProxyType
from typing import Final

BLOCK_TYPE_NAME: Final = MappingProxyType({
    1: "page",
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
    14: "code",
    15: "quote",
    17: "todo",
    18: "bitable",
    19: "callout",
    21: "diagram",
    22: "divider",
    23: "file",
    24: "grid",
    25: "grid_column",
    26: "iframe",
    27: "image",
    29: "mindnote",
    30: "sheet",
    31: "table",
    32: "table_cell",
    34: "quote_container",
    43: "board_or_wiki_catalog",
    44: "undefined_or_board",
})

RAW_IMAGE_KEY_PATTERN = re.compile(r"\bimg_v3_[A-Za-z0-9_]+\b")
REQUEST_TIMEOUT_SECONDS = 60


def info(msg: str) -> None:
    print(f"[feishu_direct_ingest] {msg}")


def warn(msg: str) -> None:
    print(f"[feishu_direct_ingest][WARN] {msg}", file=sys.stderr)


def fail(msg: str) -> None:
    print(f"[feishu_direct_ingest][ERROR] {msg}", file=sys.stderr)
