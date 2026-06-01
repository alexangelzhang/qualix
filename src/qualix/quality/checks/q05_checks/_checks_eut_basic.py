"""Q05a EUT 基础校验：缺失 SE、目录、Mock、追溯、多仓库."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

from ._collect import _PHANTOM_METHOD, _TYPO_METHOD_PATTERNS


def _check_eut_missing_se(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, eut in enumerate(data.get("eut_items") or []):
        if not isinstance(eut, dict):
            continue
        eid = eut.get("eut_id", "?")
        bs = (eut.get("bound_se") or "").strip()
        if not bs:
            errors.append(f"BLOCKED: Q05a eut_missing_se — eut_items[{i}] {eid} 缺少 bound_se")
    return errors


def _check_wrong_directory(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, tc in enumerate(data.get("test_cases") or []):
        if not isinstance(tc, dict):
            continue
        loc = tc.get("test_location") or {}
        if not isinstance(loc, dict):
            continue
        f = str(loc.get("file") or "").replace("\\", "/")
        fl = f.lower()
        # Java/Kotlin: 测试文件不应放在 src/main/
        if "src/main/" in fl and ("test" in fl or fl.endswith(".java") or fl.endswith(".kt")):
            errors.append(
                f"BLOCKED: Q05a wrong_directory — test_cases[{i}] test_location 指向 src/main: {loc.get('file')}"
            )
        # TypeScript: 测试文件不应放在 src/ 根目录下（应在 __tests__/ 或同文件 *.test.ts）
        # 判断：路径在 src/ 下，但既不含 __tests__ 也不是 .test.ts/.spec.ts
        elif fl.endswith((".ts", ".tsx")) and "src/" in fl:
            name = Path(f).name.lower()
            is_test_file = ".test." in name or ".spec." in name or "__tests__" in fl
            if not is_test_file:
                errors.append(
                    f"BLOCKED: Q05a wrong_directory — test_cases[{i}] test_location 指向非测试 TS 文件: {loc.get('file')}"
                )
    return errors


# P0-1: 方法级断言强度检测用到的正则
_TEST_METHOD_SPLIT = re.compile(r"(?=\s*@(?:Test|ParameterizedTest|RepeatedTest)\b)")
_STRONG_IN_METHOD = re.compile(
    r"\b(assertEquals|assertNotEquals|assertSame|assertThrows|assertThat|assertIterableEquals"
    r"|assertArrayEquals|verify\s*\(|ArgumentCaptor)\b"
)
_ANY_ASSERT_IN_METHOD = re.compile(r"\bassert\w+\s*\(|verify\s*\(")


def _check_mock_patterns(java_paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in java_paths:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in _TYPO_METHOD_PATTERNS:
            if pat.search(text):
                errors.append(
                    f"BLOCKED: Q05a mock_wrong — {path.name} 疑似错误方法名拼写（{pat.pattern}），请核对被测 API"
                )
                break
        # mock_phantom_method 启发式：when(...).X( 且 X 长度 <=2（极少为真实业务方法）
        for m in _PHANTOM_METHOD.finditer(text):
            name = m.group(1)
            if len(name) == 1 and name.isalpha():
                errors.append(
                    f"BLOCKED: Q05a mock_phantom_method — {path.name} when().{name}() 单字母方法名，"
                    "请确认是否为臆造方法名"
                )
                break

        # P0-1: 方法级断言强度检查
        errors.extend(_check_method_level_assert_strength(path, text))
    return errors


def _check_method_level_assert_strength(path: Path, text: str) -> list[str]:
    """P0-1: 逐个 @Test 方法检查断言强度，统计弱断言方法比例.

    弱断言方法 = 有 assert 调用但无强断言（assertEquals/assertThrows/verify 等）。
    比例超过阈值（>40%）时报 BLOCKED。
    """
    # 按 @Test 注解分割方法块（简单启发式）
    blocks = _TEST_METHOD_SPLIT.split(text)
    # 过滤掉没有 @Test 的开头块
    test_blocks = [b for b in blocks if re.match(r"\s*@(?:Test|ParameterizedTest|RepeatedTest)\b", b)]
    if not test_blocks:
        return []

    weak_methods: list[str] = []
    for block in test_blocks:
        has_any_assert = bool(_ANY_ASSERT_IN_METHOD.search(block))
        has_strong = bool(_STRONG_IN_METHOD.search(block))
        if has_any_assert and not has_strong:
            # 提取方法名
            m = re.search(r"(?:public|protected|void)\s+(\w+)\s*\(", block)
            name = m.group(1) if m else "?"
            weak_methods.append(name)

    total = len(test_blocks)
    weak_count = len(weak_methods)
    if total > 0 and weak_count / total > 0.4:
        return [
            f"BLOCKED: Q05a weak_assert_method — {path.name} {weak_count}/{total} 个 @Test 方法仅有弱断言"
            f"（assertNotNull 等），缺少 assertEquals/assertThrows/verify：{', '.join(weak_methods[:4])}"
        ]
    return []


_TODO_THEN_PATTERN = re.compile(
    r"^\s*(TODO|待补充|待实现|N/?A|不适用|集成测试|integration\s+test|需要集成|暂不覆盖)\s*$",
    re.IGNORECASE,
)

_INJECT_MOCKS_PATTERN = re.compile(r"@InjectMocks\s+(\w+)", re.IGNORECASE)
_IMPORT_CLASS_PATTERN = re.compile(r"import\s+(?:[\w.]+\.)?(\w+)\s*;")

_TRACEABILITY_PATTERN = re.compile(r"(SE-\d+|EUT-\d+)", re.IGNORECASE)


def _check_se_traceability(test_files: list[Path]) -> list[str]:
    """Fix-3: @Test 方法必须有 SE/EUT 追溯注释（检查比例）.

    SKILL.md Step 3.4：每个 @Test 方法必须标注关联的 SE/EUT ID。
    <60% 的方法有追溯标注 → WARNING。
    """
    if not test_files:
        return []
    total_methods = 0
    traced_methods = 0
    for path in test_files:
        if path.suffix != ".java":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blocks = _TEST_METHOD_SPLIT.split(text)
        test_blocks = [b for b in blocks if re.match(r"\s*@(?:Test|ParameterizedTest|RepeatedTest)\b", b)]
        for block in test_blocks:
            total_methods += 1
            # 检查方法的前3行是否有 SE/EUT 注释，或方法名本身含 SE/EUT 编号
            first_lines = "\n".join(block.splitlines()[:6])
            if _TRACEABILITY_PATTERN.search(first_lines):
                traced_methods += 1

    if total_methods == 0:
        return []
    rate = traced_methods / total_methods
    if rate < 0.6:
        return [
            f"WARNING: Q05a traceability — {traced_methods}/{total_methods} 个 @Test 方法有 SE/EUT 追溯标注"
            f"（{rate:.0%}，要求 ≥60%）。请在方法注释或名称中加入 SE-xxx/EUT-xxx 标识。"
        ]
    return []


def _check_multi_repo_coverage(code_repos: list[str], test_files: list[Path]) -> list[str]:
    """Fix-4: 多仓库完整性 gate — 有代码变更的仓库必须有新增测试文件.

    仅对有 git diff 变更的仓库做要求：master 等基线仓库无生产代码变更，不应要求新测试。
    """

    if len(code_repos) <= 1:
        return []
    errors: list[str] = []
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue

        # 检查该仓库是否有生产代码变更（git diff origin/master...HEAD）
        try:
            result = subprocess.run(
                ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            changed_prod = [f for f in result.stdout.splitlines() if f.endswith(".java") and "/test/" not in f]
        except Exception:
            changed_prod = []

        # 无生产代码变更（如 master 基线仓库）→ 不要求新测试
        if not changed_prod:
            continue

        # 有生产代码变更 → 必须有对应新测试文件
        repo_has_tests = any(str(f).startswith(str(repo)) for f in test_files)
        if not repo_has_tests:
            errors.append(
                f"BLOCKED: Q05a multi_repo_coverage — 仓库 {repo.name} 有 {len(changed_prod)} 个生产代码变更但无新增测试文件。"
                "SKILL.md Step 3.5：有代码变更的仓库必须有对应的测试生成，禁止静默跳过。"
            )
    return errors
