"""Q05 结构合规补充校验（T5）：eut_missing_se / wrong_directory / mock 类启发式.

与 schema、weak_assert_gate、test_execution_gate 互补；不重复编译运行逻辑（compile_fail 见 test_execution_gate）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.constants import STRUCTURED_JSON_MAP
from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# 常见 Mockito 方法名拼写错误（mock_wrong）
_TYPO_METHOD_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\.getSucess\s*\(",
        r"\.getSccess\s*\(",
        r"\.isSucccess\s*\(",
        r"\.isSeccess\s*\(",
    )
)

# 可疑「幽灵方法」：when(mockX.foo()) 中 foo 过短或全大写缩写（启发式，低噪音）
_PHANTOM_METHOD = re.compile(
    r"\bwhen\s*\(\s*[^)]+\)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
)


_SUPPLEMENTAL_SUFFIXES = frozenset((".java", ".kt", ".ts", ".tsx", ".patch"))


def _collect_supplemental_files(phase_root: Path) -> list[Path]:
    d = phase_root / "supplemental_tests"
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*") if p.is_file() and p.suffix in _SUPPLEMENTAL_SUFFIXES)


# 向后兼容别名
_collect_supplemental_java = _collect_supplemental_files


def _check_eut_missing_se(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for i, eut in enumerate(data.get("eut_items") or []):
        if not isinstance(eut, dict):
            continue
        eid = eut.get("eut_id", "?")
        bs = (eut.get("bound_se") or "").strip()
        if not bs:
            errors.append(f"BLOCKED: Q05 eut_missing_se — eut_items[{i}] {eid} 缺少 bound_se")
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
                f"BLOCKED: Q05 wrong_directory — test_cases[{i}] test_location 指向 src/main: {loc.get('file')}"
            )
        # TypeScript: 测试文件不应放在 src/ 根目录下（应在 __tests__/ 或同文件 *.test.ts）
        # 判断：路径在 src/ 下，但既不含 __tests__ 也不是 .test.ts/.spec.ts
        elif fl.endswith((".ts", ".tsx")) and "src/" in fl:
            name = Path(f).name.lower()
            is_test_file = ".test." in name or ".spec." in name or "__tests__" in fl
            if not is_test_file:
                errors.append(
                    f"BLOCKED: Q05 wrong_directory — test_cases[{i}] test_location 指向非测试 TS 文件: {loc.get('file')}"
                )
    return errors


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
                    f"BLOCKED: Q05 mock_wrong — {path.name} 疑似错误方法名拼写（{pat.pattern}），请核对被测 API"
                )
                break
        # mock_phantom_method 启发式：when(...).X( 且 X 长度 <=2（极少为真实业务方法）
        for m in _PHANTOM_METHOD.finditer(text):
            name = m.group(1)
            if len(name) == 1 and name.isalpha():
                errors.append(
                    f"BLOCKED: Q05 mock_phantom_method — {path.name} when().{name}() 单字母方法名，"
                    "请确认是否为臆造方法名"
                )
                break
    return errors


def run_q05_structure_checks(output_dir: Path, project_id: str) -> list[str]:
    """对 Q05 phase_b_structured + supplemental_tests 做结构类校验."""
    phase_def = PHASE_DEFS.get("Q05")
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_name = STRUCTURED_JSON_MAP.get("Q05")
    if not json_name:
        return []

    path = pd / json_name
    data = load_json(path)
    if not data or not isinstance(data, dict):
        return []

    errors: list[str] = []
    errors.extend(_check_eut_missing_se(data))
    errors.extend(_check_wrong_directory(data))
    errors.extend(_check_mock_patterns(_collect_supplemental_java(pd)))

    if errors:
        log.info("Q05 structure checks: %d issue(s)", len(errors))
    return errors
