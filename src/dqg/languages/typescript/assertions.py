"""TypeScript/Jest/Vitest 断言强度映射."""

from __future__ import annotations

from dqg.languages.base import Strength

# ---------------------------------------------------------------------------
# matcher → 强度映射
# ---------------------------------------------------------------------------

STRONG_MATCHERS = frozenset(
    {
        "toBe",
        "toEqual",
        "toStrictEqual",
        "toMatchObject",
        "toThrow",
        "toThrowError",
        "toHaveBeenCalledWith",
        "toHaveBeenLastCalledWith",
        "toHaveBeenNthCalledWith",
        "toHaveReturnedWith",
        "toHaveLastReturnedWith",
        "toContain",
        "toContainEqual",
        "toMatch",
        "toMatchSnapshot",
        "toMatchInlineSnapshot",
        "toHaveLength",
        "toHaveProperty",
        "toBeGreaterThan",
        "toBeGreaterThanOrEqual",
        "toBeLessThan",
        "toBeLessThanOrEqual",
        "toBeCloseTo",
        "toBeInstanceOf",
        "resolves",
        "rejects",
    }
)

WEAK_MATCHERS = frozenset(
    {
        "toBeDefined",
        "toBeTruthy",
        "toBeFalsy",
        "toBeNull",
        "toBeUndefined",
        "toBeNaN",
    }
)

TRIVIAL_PATTERNS = frozenset(
    {
        # expect(true).toBe(true) 等常量断言在运行时检测
        "toHaveBeenCalled",  # 无参数，只验证调用不验证入参
        "toHaveReturned",  # 无参数
    }
)


def classify_ts_assertion(matcher: str, expect_arg: str, matcher_args: list[str]) -> Strength:
    """TypeScript 断言强度分类.

    Args:
        matcher: matcher 方法名 (toBe, toBeDefined, ...)
        expect_arg: expect() 的参数文本
        matcher_args: matcher 的参数文本列表
    """
    # Trivial: expect(true).toBe(true) / expect(false).toBe(false)
    if matcher == "toBe" and matcher_args:
        arg = matcher_args[0].strip()
        if expect_arg.strip() == arg and arg in ("true", "false", "null", "undefined", "0", "1", '""', "''"):
            return Strength.TRIVIAL

    # Trivial: toHaveBeenCalled() 无参数
    if matcher in TRIVIAL_PATTERNS:
        return Strength.TRIVIAL

    if matcher in STRONG_MATCHERS:
        return Strength.STRONG

    if matcher in WEAK_MATCHERS:
        return Strength.WEAK

    # 未知 matcher 默认 weak
    return Strength.WEAK


# ---------------------------------------------------------------------------
# 弱断言信号码
# ---------------------------------------------------------------------------

EXPECT_DEFINED_ONLY = "EXPECT_DEFINED_ONLY"
CONSTANT_EXPECT = "CONSTANT_EXPECT"
MOCK_VERIFY_ONLY = "MOCK_VERIFY_ONLY"
THROW_NO_EFFECT = "THROW_NO_EFFECT"
INSUFFICIENT_ASSERTIONS = "INSUFFICIENT_ASSERTIONS"

# ---------------------------------------------------------------------------
# Mock 模式
# ---------------------------------------------------------------------------

MOCK_PATTERNS = frozenset(
    {
        "jest.mock",
        "jest.spyOn",
        "jest.fn",
        "vi.mock",
        "vi.spyOn",
        "vi.fn",
    }
)
