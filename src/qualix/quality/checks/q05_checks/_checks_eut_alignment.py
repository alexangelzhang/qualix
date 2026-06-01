"""Q05a EUT 代码对齐检查（when/then 关键词、never()、SE-id 追溯、test_location）."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

from ._checks_eut_basic import _INJECT_MOCKS_PATTERN

_METHOD_FROM_WHEN = re.compile(r"\b([a-z][a-zA-Z0-9]{3,})\s*\(")
# C4 / Step 0.5 共享：不应调用语义关键词
_NON_INVOCATION_KWS: frozenset[str] = frozenset(
    {"不发起", "不调用", "不生成", "不回退", "短路", "不传", "不应调用", "禁止调用"}
)
_ASSERT_FROM_THEN = re.compile(
    r"\b(assertEquals|assertThrows|assertThat|verify|assertNull|assertFalse|assertNotNull)\b",
    re.IGNORECASE,
)
# C4: never() pattern in .java files
# Mockito: verify(mock, never()).method() 或 verify(mock, times(0)).method()
# 简单匹配 ", never()" 即可覆盖嵌套括号场景（[^)]+ 无法正确处理 verify(mock, never())）
_NEVER_IN_CODE = re.compile(r",\s*never\s*\(\)|times\s*\(\s*0\s*\)", re.IGNORECASE)
# C7: test_location file existence helper
_REPO_PATH_CACHE: dict[str, Path] = {}


def _check_eut_code_alignment(
    data: dict[str, Any],
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C1+C2: EUT when 字段描述的方法名 + then 字段描述的断言关键词必须出现在测试代码里.

    L1（EUT JSON）↔ L2（.java 测试代码）交叉验证：
    - C1: when="调用 identifyByPrecheckAndFulfillment" → 测试文件里有该方法调用
    - C2: then="assertEquals(LOGISTIC_EXCHANGE, ...)" → 测试文件里有 assertEquals
    """
    if not test_files:
        return []
    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return []

    # 预读所有测试文件文本
    file_texts: list[str] = []
    for p in java_files:
        try:
            file_texts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            file_texts.append("")
    all_code = "\n".join(file_texts)

    euts = data.get("eut_items", [])
    c1_mismatches: list[str] = []
    c2_mismatches: list[str] = []

    for e in euts:
        eid = e.get("eut_id", "?")
        when = str(e.get("when", "") or "")
        then = str(e.get("then", "") or "")

        # C1: 从 when 提取方法名，检查是否出现在测试文件
        method_matches = _METHOD_FROM_WHEN.findall(when)
        for method_name in method_matches:
            if len(method_name) < 5:
                continue
            if method_name not in all_code:
                c1_mismatches.append(f"{eid}(when='{method_name}')")
                break

        # C2: 从 then 提取断言关键词，检查是否出现在测试文件
        then_asserts = _ASSERT_FROM_THEN.findall(then)
        for assert_kw in then_asserts:
            if assert_kw.lower() not in all_code.lower():
                c2_mismatches.append(f"{eid}(then 含{assert_kw}但代码无)")
                break

    errors: list[str] = []
    if c1_mismatches and len(c1_mismatches) / max(len(euts), 1) > 0.3:
        errors.append(
            f"WARNING: Q05a eut_when_mismatch — {len(c1_mismatches)} 个 EUT 的 when 字段方法名"
            f"未出现在测试代码中: {', '.join(c1_mismatches[:4])}。"
            "EUT JSON 的 when 描述与实际测试调用可能不一致。"
        )
    if c2_mismatches and len(c2_mismatches) / max(len(euts), 1) > 0.3:
        errors.append(
            f"WARNING: Q05a eut_then_mismatch — {len(c2_mismatches)} 个 EUT 的 then 字段断言"
            f"未出现在测试代码中: {', '.join(c2_mismatches[:4])}。"
            "EUT then 描述的断言方法与实际测试代码可能不一致。"
        )
    return errors


def _check_never_verify_in_code(
    data: dict[str, Any],
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C4: 修正版 never() 验证——直接扫描 .java 测试代码，不依赖 JSON then 字段.

    若存在"不应调用"语义的 SE，相关测试文件里必须有 verify(mock, never()) 或 times(0)。
    """
    if not q01_data:
        return []
    ses = q01_data.get("semantic_expectations", [])
    non_invoke_ses = [s for s in ses if any(kw in s.get("description", "") for kw in _NON_INVOCATION_KWS)]
    if not non_invoke_ses:
        return []

    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return [
            "BLOCKED: Q05a never_verify_no_testfile — 存在「不应调用」语义 SE 但无新增测试文件，"
            "无法验证 verify(never()) 实际存在于代码中。"
        ]

    found_never = any(
        _NEVER_IN_CODE.search(p.read_text(encoding="utf-8", errors="replace")) for p in java_files if p.is_file()
    )
    if not found_never:
        se_ids = [s["se_id"] for s in non_invoke_ses]
        return [
            f"BLOCKED: Q05a never_verify_missing_in_code — 存在「不应调用」SE（{', '.join(se_ids[:3])}）"
            "但测试代码中未发现 verify(mock, never())/times(0)。"
            "请在对应测试方法里加入 verify(mock, never()).targetMethod() 验证。"
        ]
    return []


def _check_se_id_validity_in_traceability(
    test_files: list[Path],
    q01_data: dict[str, Any] | None,
) -> list[str]:
    """C5: @Test 方法里出现的 SE-xxx 必须是 Q01 里真实存在的 SE ID."""
    if not q01_data or not test_files:
        return []
    valid_se_ids = {s["se_id"] for s in q01_data.get("semantic_expectations", [])}
    ghost_refs: list[str] = []
    for path in test_files:
        if path.suffix != ".java":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in re.finditer(r"SE-(\d+)", text, re.IGNORECASE):
            se_id = f"SE-{m.group(1)}"
            if se_id not in valid_se_ids:
                ghost_refs.append(f"{path.name}:{se_id}")
    if ghost_refs:
        unique = sorted(set(ghost_refs))
        return [
            f"WARNING: Q05a ghost_se_ref — 测试代码中引用了 {len(unique)} 个 Q01 不存在的 SE ID: "
            f"{', '.join(unique[:5])}。请核对注释里的 SE 编号是否拼写正确。"
        ]
    return []


def _check_test_location_file_exists(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """C7: test_cases[].test_location.file 必须在 code_repo 磁盘上真实存在."""
    if not code_repos:
        return []
    test_cases = data.get("test_cases", [])
    missing: list[str] = []
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        loc = tc.get("test_location") or {}
        if not isinstance(loc, dict):
            continue
        file_path = str(loc.get("file", "") or "")
        if not file_path:
            continue
        # 在各 code_repo 下查找该文件
        found = False
        for repo_str in code_repos:
            repo = Path(repo_str).expanduser().resolve()
            candidate = repo / file_path.lstrip("/")
            if candidate.is_file():
                found = True
                break
            # 也尝试只用 basename 搜索
            basename = Path(file_path).name
            if basename and any((repo / "**" / basename).parent.is_dir() for _ in [1]):
                found = True
                break
        if not found:
            missing.append(Path(file_path).name)
    if missing:
        unique = sorted(set(missing))
        return [
            f"WARNING: Q05a test_location_not_found — {len(unique)} 个 test_location.file 在 code_repo 中未找到: "
            f"{', '.join(unique[:5])}。test_location 可能是虚填路径，请确认文件已写入 src/test/java。"
        ]
    return []


def _check_test_file_eut_reverse(
    data: dict[str, Any],
    test_files: list[Path],
    target_modules_data: dict[str, Any] | None,
) -> list[str]:
    """C8: 反向检查——新增测试文件里的被测类必须能在 EUT 矩阵里找到对应条目.

    防止 LLM 写了"幽灵测试"（有代码但 EUT 矩阵里没有对应记录）。
    """
    java_files = [f for f in test_files if f.suffix == ".java"]
    if not java_files:
        return []

    euts = data.get("eut_items", [])
    # 从 EUT when/given/then 提取所有提及的类名（大写开头）
    eut_text = " ".join(
        str(e.get("when", "")) + " " + str(e.get("given", "")) + " " + str(e.get("then", "")) for e in euts
    )
    eut_classes_mentioned: set[str] = set(re.findall(r"\b([A-Z][a-zA-Z0-9]{4,})\b", eut_text))

    # 也从 target_modules se_mappings 读 impl_class
    if target_modules_data:
        for m in target_modules_data.get("se_mappings", []):
            cls = str(m.get("impl_class") or "")
            if cls:
                eut_classes_mentioned.add(cls)

    orphan_tests: list[str] = []
    for path in java_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 提取被测类（@InjectMocks 后的类名）
        for m in _INJECT_MOCKS_PATTERN.finditer(text):
            cls = m.group(1)
            if cls not in eut_classes_mentioned and len(cls) > 5:
                orphan_tests.append(f"{path.name}→{cls}")

    if orphan_tests:
        unique = sorted(set(orphan_tests))[:5]
        return [
            f"WARNING: Q05a orphan_test — {len(orphan_tests)} 个测试文件的被测类（@InjectMocks）"
            f"未出现在 EUT 矩阵 when/given 或 target_modules 中: {', '.join(unique)}。"
            "这些测试可能是无需求溯源的幽灵测试，请确认是否有对应的 EUT 条目。"
        ]
    return []
