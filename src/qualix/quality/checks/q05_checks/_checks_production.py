"""Q05 生产代码真实性检查（幽灵方法等）."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

_METHOD_DEF_PATTERN = re.compile(r"(?:public|protected)\s+(?:static\s+)?(?:final\s+)?\S+\s+([a-z][a-zA-Z0-9_]+)\s*\(")
_THEN_EXTRACT = re.compile(r"\b([a-z][a-zA-Z]{4,})\s*\(")
_THEN_SKIP: frozenset[str] = frozenset(
    {
        # 全部小写，与 m.lower() 比较
        "assertequals",
        "assertnotequals",
        "assertthrows",
        "assertthat",
        "assertnull",
        "assertfalse",
        "asserttrue",
        "assertnotnull",
        "assertsame",
        "assertiterableequals",
        "assertarrayequals",
        "verify",
        "never",
        "times",
        "inorder",
        "any",
        "anystring",
        "anylong",
        "anyint",
        "anydouble",
        "anyobject",
        "eq",
        "argthat",
        "contains",
        "startswith",
        "endswith",
        "when",
        "thenreturn",
        "thenthrow",
        "given",
        "willreturn",
        "mock",
        "spy",
        "captor",
        "capture",
        "getopcode",
        "getoperson",
        "getopname",  # 常见 DTO getter（误报高）
    }
)


def _build_prod_method_set(code_repos: list[str]) -> set[str]:
    """扫描 code_repos 的 src/main/java 目录，构建 public/protected 方法名全集."""
    import os as _os

    method_names: set[str] = set()
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        for root, _dirs, files in _os.walk(str(repo)):
            if "src/main/java" not in root.replace("\\", "/"):
                continue
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                fpath = Path(root) / fname
                try:
                    src = fpath.read_text(encoding="utf-8", errors="replace")
                    method_names.update(_METHOD_DEF_PATTERN.findall(src))
                except OSError:
                    continue
    return method_names


def check_eut_then_phantom_methods(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """Q05a gate: EUT then 字段的业务方法名必须在生产代码中真实存在.

    扫描 code_repos 所有 src/main/java/*.java，构建方法名全集。
    then 字段里出现但全集里不存在的方法名 → 幻觉方法名 → BLOCKED。

    注意：此检查跨类搜索，verify(serviceA).method() 的 method 可能在
    serviceA 类（不一定是被测类），因此搜索范围是整个生产代码库。
    """
    euts = data.get("eut_items", [])
    if not euts or not code_repos:
        return []

    prod_methods = _build_prod_method_set(code_repos)
    if not prod_methods:
        return []

    phantoms: list[str] = []
    for e in euts:
        eid = e.get("eut_id", "?")
        then = str(e.get("then", "") or "")
        if not then:
            continue

        then_methods = {m for m in _THEN_EXTRACT.findall(then) if m.lower() not in _THEN_SKIP and len(m) > 5}

        missing = [m for m in then_methods if m not in prod_methods]
        if missing:
            phantoms.append(f"{eid}({'+'.join(missing[:2])})")

    if not phantoms:
        return []

    return [
        f"BLOCKED: Q05a eut_then_phantom_method — {len(phantoms)} 条 EUT 的 then 字段"
        f"包含生产代码中不存在的方法名（幻觉）: "
        f"{', '.join(phantoms[:5])}{'...' if len(phantoms) > 5 else ''}。"
        "请核对被测类及其依赖的真实 public 方法签名，修正 then 字段后重新 finalize。"
    ]


# ── 实现 SKILL.md 第 44 行文档化但缺失的 gate ────────────────────────────────
# SKILL.md §Step 0.5：feature branch 每个新增/修改的 Java 实现类，
# 必须在某条 EUT 的 when/given 字段里出现。
_IMPL_SUFFIXES: frozenset[str] = frozenset(
    ("Service", "Manager", "Ext", "Consumer", "Handler", "Processor", "Executor", "Impl")
)
_SKIP_CLASS_PATTERNS: frozenset[str] = frozenset(
    (
        "Config",
        "Configuration",
        "Enum",
        "Constant",
        "VO",
        "Vo",
        "Dto",
        "DTO",
        "Entity",
        "Builder",
        "Param",
        "Request",
        "Response",
        "Abstract",
        "Base",
    )
)
# 这些模块路径里的类是接口/常量定义，不需要测试
_SKIP_MODULE_PREFIXES: tuple[str, ...] = (
    "maf-interface/",
    "maf-core/src/main/java/com/mi/maf/core/constant/",
    "maf-core/src/main/java/com/mi/maf/core/enums/",
)
