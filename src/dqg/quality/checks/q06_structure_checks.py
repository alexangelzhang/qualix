"""Q06 结构合规补充校验：COVERED 断言验证 / weak_assert sidecar / WRONG_TARGET 代码验证."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.constants import STRUCTURED_JSON_MAP
from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# 与 q05_structure_checks.py 共享的断言强度模式
_STRONG_ASSERT = re.compile(
    r"\b(assertEquals|assertNotEquals|assertSame|assertThrows|assertThat|assertIterableEquals"
    r"|assertArrayEquals|verify\s*\(|ArgumentCaptor)\b",
    re.IGNORECASE,
)
_WEAK_ONLY = re.compile(r"\bassertNotNull\b", re.IGNORECASE)
_TEST_METHOD_RE = re.compile(r"(?:public|protected|void)\s+(\w+)\s*\(")
_WEAK_ASSERT_SIDECAR_METHOD = re.compile(r"(?:method|方法)[：:]\s*`?(\w+Test\w*)`?|`(\w+)\s*\(`", re.IGNORECASE)


def _load_test_files(code_repos: list[str]) -> dict[str, str]:
    """加载所有 code_repo 的 .java 测试文件内容，返回 {class_name: file_content}."""
    result: dict[str, str] = {}
    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            continue
        for java_file in repo.rglob("*Test.java"):
            try:
                content = java_file.read_text(encoding="utf-8", errors="replace")
                result[java_file.stem] = content
            except OSError:
                continue
    return result


def _find_method_block(class_content: str, method_name: str) -> str:
    """从类内容中提取指定方法的代码块（简单启发式）."""
    pattern = re.compile(
        rf"@Test\b[^{{]*?\b{re.escape(method_name)}\s*\([^)]*\)\s*\{{",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(class_content)
    if not m:
        return ""
    # 提取方法体（取开头 500 字符）
    start = m.start()
    return class_content[start : start + 500]


def _check_covered_assertion_strength(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """G1: COVERED 的 audit_item 对应测试方法必须有强断言.

    L1（status=COVERED）↔ L0（.java 测试代码断言强度）交叉验证。
    防止 LLM 把弱断言测试（assertNotNull）错误标为 COVERED，应为 WRONG_TARGET。
    """
    if not code_repos:
        return []

    audit_items = data.get("audit_items", [])
    covered_items = [
        i
        for i in audit_items
        if isinstance(i, dict) and str(i.get("status", "")).upper() == "COVERED" and i.get("test_method")
    ]
    if not covered_items:
        return []

    test_files = _load_test_files(code_repos)
    if not test_files:
        return []

    suspicious: list[str] = []
    for item in covered_items:
        test_class = str(item.get("test_class", "") or "")
        test_method = str(item.get("test_method", "") or "")
        eut_id = item.get("eut_id", "?")

        class_key = Path(test_class).stem if test_class else ""
        content = test_files.get(class_key, "")
        if not content:
            continue

        block = _find_method_block(content, test_method)
        if not block:
            continue

        has_strong = bool(_STRONG_ASSERT.search(block))
        has_weak = bool(_WEAK_ONLY.search(block))
        if has_weak and not has_strong:
            suspicious.append(f"{eut_id}({test_class}.{test_method})")

    if suspicious and len(suspicious) / max(len(covered_items), 1) > 0.2:
        return [
            f"WARNING: Q06 covered_weak_assert — {len(suspicious)} 个 COVERED 条目的测试方法"
            f"仅有 assertNotNull 弱断言，应标为 WRONG_TARGET: {', '.join(suspicious[:4])}。"
            "COVERED 必须验证业务结果（assertEquals/assertThrows/verify 等）。"
        ]
    return []


def _check_weak_assert_sidecar_utilization(
    output_dir: Path,
    project_id: str,
    phase_def: dict,
    data: dict[str, Any],
) -> list[str]:
    """G4: weak_assert sidecar 存在时，sidecar 标记的弱断言方法必须在 Q06 里被标为 WRONG_TARGET.

    SKILL.md 铁律：_internal/_weak_assert_context.md 存在时必须读取用于 WRONG_TARGET 判定。
    若 sidecar 里的方法在 audit_items 里标为 COVERED，疑似 LLM 未读取 sidecar。
    """
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    sidecar_path = int_dir / "_weak_assert_context.md"
    if not sidecar_path.exists():
        return []

    try:
        sidecar_content = sidecar_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # 提取 sidecar 里标记的弱断言测试方法名
    sidecar_methods: set[str] = set()
    for m in re.finditer(
        r"\b(\w+Test\w*)\s*#\s*(\w+)|\b(\w+)\s*\(.*?\)\s*—.*弱|WEAK.*?\b(\w+Test\w*)", sidecar_content
    ):
        for g in m.groups():
            if g and len(g) > 5:
                sidecar_methods.add(g)

    if not sidecar_methods:
        return []

    # 检查这些方法在 Q06 里是否被标为 WRONG_TARGET
    wrong_target_methods: set[str] = set()
    for item in data.get("audit_items", []):
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "WRONG_TARGET":
            m = item.get("test_method", "") or ""
            if m:
                wrong_target_methods.add(m)

    not_marked = sidecar_methods - wrong_target_methods
    if not_marked:
        samples = sorted(not_marked)[:4]
        return [
            f"WARNING: Q06 sidecar_ignored — weak_assert sidecar 中 {len(not_marked)} 个弱断言方法"
            f"未在 audit_items 里标注为 WRONG_TARGET: {', '.join(samples)}。"
            "SKILL.md 铁律：_weak_assert_context.md 存在时必须读取并用于 WRONG_TARGET 判定。"
        ]
    return []


def _check_wrong_target_code_validation(
    data: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """G6: WRONG_TARGET 的判定应有代码端支撑——对应测试方法确实是弱断言.

    防止 LLM 随意标记 WRONG_TARGET（虚报问题制造覆盖率偏低的假象）。
    WRONG_TARGET 的测试方法应该只有弱断言，如果实际有强断言，判定可疑。
    """
    if not code_repos:
        return []

    wrong_items = [
        i
        for i in data.get("audit_items", [])
        if isinstance(i, dict) and str(i.get("status", "")).upper() == "WRONG_TARGET" and i.get("test_method")
    ]
    if not wrong_items:
        return []

    test_files = _load_test_files(code_repos)
    if not test_files:
        return []

    suspicious: list[str] = []
    for item in wrong_items:
        test_class = str(item.get("test_class", "") or "")
        test_method = str(item.get("test_method", "") or "")
        eut_id = item.get("eut_id", "?")

        class_key = Path(test_class).stem if test_class else ""
        content = test_files.get(class_key, "")
        if not content:
            continue

        block = _find_method_block(content, test_method)
        if not block:
            continue

        # WRONG_TARGET 的方法应该缺乏强断言
        has_strong = bool(_STRONG_ASSERT.search(block))
        if has_strong:
            suspicious.append(f"{eut_id}({test_method})")

    if suspicious:
        return [
            f"WARNING: Q06 wrong_target_suspicious — {len(suspicious)} 个标为 WRONG_TARGET 的测试方法"
            f"实际有强断言，判定可疑（可能应该是 COVERED）: {', '.join(suspicious[:4])}。"
            "请重新核实这些测试是否真的验证了错误目标。"
        ]
    return []


def run_q06_structure_checks(output_dir: Path, project_id: str) -> list[str]:
    """Q06 结构合规补充校验（对标 Q05 run_q05_structure_checks 的深度）."""
    phase_def = PHASE_DEFS.get("Q06")
    if not phase_def:
        return []

    pd = _phase_dir(output_dir, project_id, phase_def)
    json_name = STRUCTURED_JSON_MAP.get("Q06")
    if not json_name:
        return []

    data = load_json(pd / json_name)
    if not data or not isinstance(data, dict):
        return []

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs_data = load_json(int_dir / "_inputs.json") if (int_dir / "_inputs.json").is_file() else {}
    code_repos: list[str] = []
    if inputs_data and isinstance(inputs_data, dict):
        code_repos = inputs_data.get("code_repos") or []
        if not code_repos and inputs_data.get("code_repo"):
            code_repos = [inputs_data["code_repo"]]

    errors: list[str] = []

    # G1: COVERED 判定 ↔ 代码断言强度交叉验证
    errors.extend(_check_covered_assertion_strength(data, code_repos))

    # G4: weak_assert sidecar 利用验证
    errors.extend(_check_weak_assert_sidecar_utilization(output_dir, project_id, phase_def, data))

    # G6: WRONG_TARGET 代码端验证
    errors.extend(_check_wrong_target_code_validation(data, code_repos))

    if errors:
        log.info("Q06 structure checks: %d issue(s)", len(errors))
    return errors
