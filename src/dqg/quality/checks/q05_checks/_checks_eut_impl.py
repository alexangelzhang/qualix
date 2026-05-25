"""Q05 EUT 实现完整性校验（C9 每条 EUT 有 @Test，check_eut_method_alignment 公开方法）."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

from ._checks_eut_basic import (
    _TEST_METHOD_SPLIT,
    _TRACEABILITY_PATTERN,
)


def _check_eut_implementation_completeness(
    data: dict[str, Any],
    test_files: list[Path],
) -> list[str]:
    """C9: EUT 矩阵实现完整性——每条 EUT 必须有对应的 @Test 方法实现.

    两层检查：
    1. 文件级（旧逻辑）：被测类必须有 {ClassName}Test.java → 无则 BLOCKED
    2. 方法级（新增）：测试文件内的 @Test 方法数量/覆盖必须匹配 EUT 条数
       - 精确模式：@Test 方法体内有 EUT-xxx 追溯注释 → 逐条验证每个 eut_id 有对应方法
       - 代理模式：无追溯注释 → @Test 方法数 ≥ EUT 条数（下界检查）
    """
    import re as _re
    from collections import defaultdict

    euts = data.get("eut_items", [])
    if not euts:
        return []

    # 从测试文件路径建立 被测类名 → 文件路径 的映射
    test_file_by_class: dict[str, Path] = {}
    for tf in test_files:
        stem = tf.stem
        if stem.endswith("Tests"):
            test_file_by_class[stem[:-5]] = tf
        elif stem.endswith("Test"):
            test_file_by_class[stem[:-4]] = tf
        else:
            test_file_by_class[stem] = tf

    # 从 EUT when 字段提取被测类名，统计每类 EUT 条数
    _CLASS_PATTERN = _re.compile(r"\b([A-Z][a-zA-Z0-9]{3,})\.[a-z]")
    class_to_euts: dict[str, list[str]] = defaultdict(list)
    for e in euts:
        when = str(e.get("when", "") or "")
        eut_id = e.get("eut_id", "?")
        for cls in _CLASS_PATTERN.findall(when):
            class_to_euts[cls].append(eut_id)

    errors: list[str] = []
    for cls in sorted(class_to_euts):
        eut_ids = class_to_euts[cls]
        tf = test_file_by_class.get(cls)

        # 层 1：文件不存在
        if tf is None:
            sample = ", ".join(eut_ids[:3])
            suffix = "..." if len(eut_ids) > 3 else ""
            errors.append(
                f"BLOCKED: Q05 eut_not_implemented — {cls} 有 {len(eut_ids)} 条 EUT 设计"
                f"（{sample}{suffix}）但无对应测试文件（{cls}Test.java）。"
                "EUT 矩阵必须全部实现为 @Test 方法后才能 finalize。"
            )
            continue

        # 层 2：方法级检查
        try:
            src = tf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 按 @Test/@ParameterizedTest/@RepeatedTest 边界分割，每块对应一个测试方法
        method_blocks = _TEST_METHOD_SPLIT.split(src)
        test_method_count = max(0, len(method_blocks) - 1)

        # 收集所有 @Test 方法体中出现的 EUT-xxx 追溯引用
        covered_eut_ids: set[str] = set()
        for block in method_blocks[1:]:
            for ref in _TRACEABILITY_PATTERN.findall(block):
                if ref.upper().startswith("EUT-"):
                    covered_eut_ids.add(ref.upper())

        if covered_eut_ids:
            # 精确模式：有追溯注释，逐条验证
            missing = [eid for eid in eut_ids if eid.upper() not in covered_eut_ids]
            if missing:
                sample = ", ".join(missing[:5])
                suffix = "..." if len(missing) > 5 else ""
                errors.append(
                    f"BLOCKED: Q05 eut_method_missing — {cls}Test.java 有 {test_method_count} 个"
                    f" @Test 方法，但以下 {len(missing)} 条 EUT 没有对应实现"
                    f"（按 EUT-xxx 追溯）：{sample}{suffix}。"
                    "请为每条 EUT 添加独立 @Test 方法并标注追溯注释（// EUT-xxx）。"
                )
        else:
            # 代理模式：无追溯注释，用方法数作下界
            if test_method_count < len(eut_ids):
                errors.append(
                    f"BLOCKED: Q05 eut_method_count — {cls} 有 {len(eut_ids)} 条 EUT 设计，"
                    f"但 {cls}Test.java 只有 {test_method_count} 个 @Test 方法。"
                    "每条 EUT 应有独立 @Test 方法（建议同时添加 // EUT-xxx 追溯注释）。"
                )

    return errors


def check_eut_method_alignment(
    data: dict[str, Any],
    test_files: list[Path],
) -> list[str]:
    """C1+C2 方法级升级版：对每个 // EUT-xxx 标注的 @Test 方法体，
    检查是否包含该 EUT then 字段的断言关键词。

    文件级 C1+C2 的不足：all_code 包含所有测试，只要文件里有 assertEquals 就通过，
    即使 EUT-012 的 @Test 方法体只有 assertNull(result)。

    本函数在方法级做精确对齐：
    - 找到 @Test 方法块中的 // EUT-xxx 引用
    - 在该方法块内提取 then 字段的关键词
    - 若关键词不在该方法块中 → WARNING（实现和设计不一致）
    """
    import re as _re

    euts = data.get("eut_items", [])
    if not euts or not test_files:
        return []

    # 构建 eut_id → then 字段映射
    eut_then: dict[str, str] = {}
    for e in euts:
        eid = e.get("eut_id", "?")
        then = str(e.get("then", "") or "")
        if then:
            eut_then[eid.upper()] = then

    # 从 then 提取关键断言词（方法名）
    _THEN_METHOD = _re.compile(
        r"\b(assertEquals|assertThrows|assertThat|verify|assertNull|assertFalse|assertNotNull|never\s*\(\)|times\s*\(\s*\d+\s*\))\s*[(\.]",
        _re.IGNORECASE,
    )
    # 提取 then 中的业务方法名（非通用断言词）
    _THEN_BUSINESS = _re.compile(r"\b([a-z][a-zA-Z]{4,})\s*\(")

    # 跟踪已通过的 EUT（任一窗口通过即算通过，不因另一窗口失败而误报）
    passed_euts: set[str] = set()
    failed_euts: dict[str, str] = {}  # eid → 失败描述

    for tf in test_files:
        if tf.suffix != ".java":
            continue
        try:
            src = tf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 按 @Test 边界分割，每块是一个测试方法
        blocks = _TEST_METHOD_SPLIT.split(src)
        for idx, block in enumerate(blocks[1:], 1):
            # 找块内所有 EUT-xxx 引用
            eut_refs = {m.upper() for m in _re.findall(r"\bEUT-(\d+)\b", block)}
            if not eut_refs:
                continue

            for num in eut_refs:
                eid = f"EUT-{num.zfill(3)}"
                then = eut_then.get(eid.upper())
                if not then:
                    continue

                # 提取 then 里的断言方法名（业务特征词）
                # 先找非通用断言（如 createOrder、doDelivery）
                then_biz_methods = set(_THEN_BUSINESS.findall(then))
                _GENERIC = {
                    # 全部小写，与 m.lower() 比较
                    "assertequals",
                    "assertnotequals",
                    "assertsame",
                    "assertthrows",
                    "assertthat",
                    "assertiterablee",
                    "assertnull",
                    "assertfalse",
                    "asserttrue",
                    "assertnotnull",
                    "verify",
                    "times",
                    "never",
                    "any",
                    "eq",
                    "anystring",
                    "anylong",
                    "anyint",
                    "anyobject",
                    "argthat",
                    "contains",
                    "startswith",
                    "valueof",  # JDK 方法，非生产代码方法
                }
                biz_specific = {m for m in then_biz_methods if m.lower() not in _GENERIC and len(m) > 5}

                if biz_specific:
                    # _TEST_METHOD_SPLIT lookahead 产生多个空 block，实际方法体可能在 10 个 block 后。
                    # 用向后 10 个 block 的窗口覆盖。EUT 在多处出现时，任一窗口通过即算通过。
                    window_end = min(idx + 10, len(blocks))
                    search_scope = "".join(blocks[idx:window_end])
                    missing_biz = [m for m in biz_specific if m not in search_scope]
                    if len(missing_biz) == len(biz_specific):
                        # 本窗口未找到，但其他窗口可能已通过，先记录失败
                        if eid not in passed_euts:
                            sample = list(biz_specific)[:2]
                            failed_euts[eid] = f"{eid}(then 要求调用 {'/'.join(sample)} 但 @Test 方法体内未出现)"
                    else:
                        # 本窗口通过，清除失败记录
                        passed_euts.add(eid)
                        failed_euts.pop(eid, None)

    # 只报在所有窗口里都未通过的 EUT
    final_mismatches = [v for k, v in failed_euts.items() if k not in passed_euts]
    if not final_mismatches:
        return []

    return [
        f"BLOCKED: Q05b eut_method_then_mismatch — {len(final_mismatches)} 个 EUT 的 @Test 方法体"
        f"与 EUT then 字段设计不一致（实现了早返回而非业务主链路）: "
        f"{', '.join(final_mismatches[:5])}{'...' if len(final_mismatches) > 5 else ''}。"
        "必须重写这些 @Test 方法，mock 完整的业务对象使主链路得以执行，才能 finalize。"
    ]
