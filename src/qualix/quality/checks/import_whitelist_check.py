"""Q05b Import Whitelist Gate.

在编译前扫描 *Test.java 文件中的 import 语句，检测幻觉 import（引用了不存在的类）。
- WARNING：发现单条无法识别的 import
- BLOCKED：超过 50% 的非标准 import 无法识别

失败开放（fail-open）：若 _q05_target_modules.json 不存在，直接返回空列表，不阻断 finalize。
"""

from __future__ import annotations

import re
from pathlib import Path

from qualix.core.state_machine import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.json_utils import load_json
from qualix.log import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 标准前缀白名单（始终允许，无需警告）
# ---------------------------------------------------------------------------

_STANDARD_PREFIXES: tuple[str, ...] = (
    "java.",
    "javax.",
    "jakarta.",
    "org.junit.",
    "org.assertj.",
    "org.mockito.",
    "org.springframework.",
    "com.fasterxml.",
    "lombok.",
)

# 匹配 import 语句，捕获 FQCN（支持静态 import）
_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*(?:\.[a-zA-Z_$][a-zA-Z0-9_$*]*)+)\s*;",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# 已知类名提取
# ---------------------------------------------------------------------------

def _extract_known_classes(target_modules_data: dict) -> set[str]:
    """从 _q05_target_modules.json 中提取所有已知的 FQCN 和简单类名.

    来源：
    - se_mappings / br_mappings 的 impl_class（可能是简单类名或 FQCN）
    - code_symbols 的 name（简单类名）
    """
    known: set[str] = set()

    for key in ("se_mappings", "br_mappings"):
        for mapping in target_modules_data.get(key, []):
            if not isinstance(mapping, dict):
                continue
            impl_class = mapping.get("impl_class", "")
            if impl_class:
                known.add(impl_class)
                # 同时加入简单类名（最后一段）
                simple = impl_class.rsplit(".", 1)[-1]
                if simple:
                    known.add(simple)

    for symbol in target_modules_data.get("code_symbols", []):
        if not isinstance(symbol, dict):
            continue
        name = symbol.get("name", "")
        if name:
            known.add(name)
        container = symbol.get("container", "")
        if container:
            known.add(container)

    return known


# ---------------------------------------------------------------------------
# 单文件检查
# ---------------------------------------------------------------------------

def _check_single_file(
    path: Path,
    known_classes: set[str],
) -> list[str]:
    """检查单个 Java 测试文件的 import 语句.

    Returns:
        WARNING 和 BLOCKED 字符串列表。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    imports = _IMPORT_RE.findall(text)
    if not imports:
        return []

    # 过滤掉标准前缀
    non_standard = [
        fqcn for fqcn in imports
        if not any(fqcn.startswith(prefix) for prefix in _STANDARD_PREFIXES)
    ]
    if not non_standard:
        return []

    # 判断哪些不在已知类列表中
    unrecognized: list[str] = []
    for fqcn in non_standard:
        # 简单类名（最后一段）
        simple = fqcn.rsplit(".", 1)[-1]
        # 通配符 import（import com.example.*）—— 无法判断，跳过
        if simple == "*":
            continue
        if fqcn not in known_classes and simple not in known_classes:
            unrecognized.append(fqcn)

    messages: list[str] = []
    for fqcn in unrecognized:
        messages.append(
            f"WARNING: import whitelist: {fqcn} not in known classes or standard prefix"
            f" (file: {path.name})"
        )

    # 阈值检查：>50% 非标准 import 无法识别 → BLOCKED
    total_non_standard = len([f for f in non_standard if not f.endswith(".*")])
    n_unrecognized = len(unrecognized)
    if total_non_standard > 0 and n_unrecognized / total_non_standard > 0.5:
        messages.append(
            f"BLOCKED: import whitelist: >{50}% unrecognized imports in {path.name}"
            f" ({n_unrecognized}/{total_non_standard})"
        )

    return messages


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def check_import_whitelist(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
    phase_id: str = "Q05b",
) -> list[str]:
    """检查 Q05b 生成的测试文件中是否存在幻觉 import.

    Args:
        output_dir:  Qualix 输出根目录。
        project_id:  项目 ID。
        code_repos:  代码仓库路径列表（字符串）。
        phase_id:    Phase ID，默认 "Q05b"。

    Returns:
        list[str]，每条以 "WARNING: " 或 "BLOCKED: " 开头。
        若 _q05_target_modules.json 不存在，返回空列表（fail-open）。
    """
    # 加载 _q05_target_modules.json（从 Q05b _internal 目录）
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        log.debug("import_whitelist_check: phase_def 不存在，跳过: %s", phase_id)
        return []

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    target_path = int_dir / "_q05_target_modules.json"

    if not target_path.exists():
        log.debug("import_whitelist_check: _q05_target_modules.json 不存在，fail-open: %s", target_path)
        return []

    target_data = load_json(target_path)
    if not target_data or not isinstance(target_data, dict):
        log.debug("import_whitelist_check: _q05_target_modules.json 为空或格式错误，fail-open")
        return []

    known_classes = _extract_known_classes(target_data)

    all_messages: list[str] = []

    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            log.debug("import_whitelist_check: 仓库路径不存在，跳过: %s", repo)
            continue

        test_roots = [
            repo / "src" / "test" / "java",
        ]
        for test_root in test_roots:
            if not test_root.is_dir():
                continue
            for java_file in test_root.rglob("*Test.java"):
                file_messages = _check_single_file(java_file, known_classes)
                all_messages.extend(file_messages)

    return all_messages
