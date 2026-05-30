"""Java 断言强度映射.

从 weak_assert_analysis.py 中提取的 Java 特定断言模式和信号常量。
"""

from __future__ import annotations

import re

from qualix.languages.base import Strength

# ---------------------------------------------------------------------------
# 断言方法 → 强度映射
# ---------------------------------------------------------------------------

STRONG_ASSERT_METHODS = frozenset(
    {
        "assertEquals",
        "assertNotEquals",
        "assertSame",
        "assertNotSame",
        "assertArrayEquals",
        "assertIterableEquals",
        "assertLinesMatch",
        "assertNull",
        "assertDoesNotThrow",
        "assertAll",
        "assertThat",  # Hamcrest/AssertJ
    }
)

WEAK_ASSERT_METHODS = frozenset(
    {
        "assertNotNull",
        "assertTrue",
        "assertFalse",
    }
)

ALL_ASSERT_METHODS = STRONG_ASSERT_METHODS | WEAK_ASSERT_METHODS | frozenset({"assertThrows"})

CONSTANT_BOOLEANS = frozenset({"true", "false", "Boolean.TRUE", "Boolean.FALSE"})


def classify_java_assertion(kind: str, args: list[str]) -> Strength:
    """Java 断言强度分类."""
    if kind in STRONG_ASSERT_METHODS:
        return Strength.STRONG
    if kind == "assertThrows":
        return Strength.STRONG
    if kind in ("assertTrue", "assertFalse"):
        if args and args[0].strip() in CONSTANT_BOOLEANS:
            return Strength.TRIVIAL
        return Strength.STRONG  # 非常量参数视为强断言
    if kind == "assertNotNull":
        return Strength.WEAK
    if kind == "verify":
        return Strength.WEAK
    return Strength.WEAK


# ---------------------------------------------------------------------------
# 弱断言信号码（与 WeakAssertSignal 对齐）
# ---------------------------------------------------------------------------

ASSERT_NOT_NULL_ONLY = "ASSERT_NOT_NULL_ONLY"
CONSTANT_BOOLEAN_ASSERT = "CONSTANT_BOOLEAN_ASSERT"
VERIFY_ONLY_NO_BUSINESS_ASSERT = "VERIFY_ONLY_NO_BUSINESS_ASSERT"
ASSERT_THROWS_NO_EFFECT_ASSERT = "ASSERT_THROWS_NO_EFFECT_ASSERT"
INSUFFICIENT_ASSERTIONS = "INSUFFICIENT_ASSERTIONS"

# ---------------------------------------------------------------------------
# 正则模式（regex fallback 用）
# ---------------------------------------------------------------------------

TEST_ANNOTATION_PATTERN = re.compile(
    r"^\s*@(?:Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b",
    re.MULTILINE,
)
ASSERT_NOT_NULL_PATTERN = re.compile(r"\bassertNotNull\s*\(")
CONSTANT_BOOL_ASSERT_PATTERN = re.compile(r"\bassert(?:True|False)\s*\(\s*(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\)")
VERIFY_PATTERN = re.compile(r"\bverify\s*\(")
ASSERT_THROWS_PATTERN = re.compile(r"\bassertThrows\s*\(")
STRONG_ASSERT_PATTERN = re.compile(
    r"\bassert(?:Equals|NotEquals|Same|NotSame|ArrayEquals|IterableEquals|LinesMatch|Null|DoesNotThrow|All)\s*\("
)
ASSERT_THAT_PATTERN = re.compile(r"\bassertThat\s*\(")
NON_CONSTANT_BOOL_ASSERT_PATTERN = re.compile(
    r"\bassert(?:True|False)\s*\(\s*(?!(?:Boolean\.)?(?:TRUE|FALSE|true|false)\s*\))"
)
