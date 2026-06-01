"""DDD+TMF Mock 一致性静态检查.

检测 Java 测试文件中 @InjectMocks 和 @Mock 字段之间的层级不匹配。
始终返回 WARNING（不 BLOCKED）——这是建议性检查，不阻断 finalize。
"""

from __future__ import annotations

import re
from pathlib import Path

from qualix.log import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------

# 匹配 @InjectMocks SomeClass varName 或 @InjectMocks SomeClass
_INJECT_MOCKS_RE = re.compile(r"@InjectMocks\s+(\w[\w$]*)\s+(\w+)", re.MULTILINE)
# 匹配 @Mock SomeClass fieldName
_MOCK_FIELD_RE = re.compile(r"@Mock(?:\([^)]*\))?\s+(\w[\w$.<>]*)\s+(\w+)", re.MULTILINE)


# ---------------------------------------------------------------------------
# Layer 推断
# ---------------------------------------------------------------------------

def _infer_layer(class_name: str) -> str:
    """从类名后缀推断 DDD 层级.

    Returns:
        "domain" | "application" | "infrastructure" | "unknown"
    """
    name = class_name.lower()
    if name.endswith("domainservice"):
        return "domain"
    if name.endswith("applicationservice"):
        return "application"
    if (
        name.endswith("repository")
        or name.endswith("mapper")
        or name.endswith("adapter")
        or name.endswith("dao")
    ):
        return "infrastructure"
    return "unknown"


def _is_repository_or_infra(type_name: str) -> bool:
    """判断 Mock 字段类型是否属于 Repository/基础设施."""
    n = type_name.lower()
    return (
        n.endswith("repository")
        or n.endswith("mapper")
        or n.endswith("dao")
        or n.endswith("adapter")
    )


def _is_domain_service(type_name: str) -> bool:
    """判断 Mock 字段类型是否属于 DomainService."""
    return type_name.lower().endswith("domainservice")


# ---------------------------------------------------------------------------
# 核心检查
# ---------------------------------------------------------------------------

def _check_single_file(path: Path) -> list[str]:
    """检查单个 Java 文件，返回 WARNING 字符串列表."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    warnings: list[str] = []

    # 找到所有 @InjectMocks 声明
    inject_matches = list(_INJECT_MOCKS_RE.finditer(text))
    if not inject_matches:
        return []

    # 找到所有 @Mock 声明
    mock_fields: list[tuple[str, str]] = [
        (m.group(1), m.group(2)) for m in _MOCK_FIELD_RE.finditer(text)
    ]

    for im in inject_matches:
        class_name = im.group(1)
        var_name = im.group(2)

        # 检查内部类（含 $）
        if "$" in class_name:
            warnings.append(
                f"WARNING: mock_consistency — {path.name}: "
                f"@InjectMocks {class_name} {var_name} 目标为内部类（含 '$'），"
                "Mockito @InjectMocks 对内部类无效，请改用构造器注入（在 @BeforeEach 中 new Xxx(mockDep)）。"
            )

        layer = _infer_layer(class_name)

        if layer == "application":
            # Application Service 不应直接 Mock Repository/Mapper/DAO
            for field_type, field_name in mock_fields:
                if _is_repository_or_infra(field_type):
                    warnings.append(
                        f"WARNING: mock_consistency — {path.name}: "
                        f"@InjectMocks {class_name} 是 ApplicationService 层，"
                        f"但直接 @Mock 了基础设施类型 {field_type} {field_name}。"
                        "ApplicationService 应当 @Mock DomainService，而不是直接 Mock Repository/Mapper，"
                        "直接 Mock 会绕过领域层，破坏 DDD 层级边界。"
                        "请改为 @Mock 对应的 DomainService。"
                    )

    return warnings


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------

def check_mock_consistency(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
) -> list[str]:
    """检查各仓库测试目录中的 @InjectMocks / @Mock 层级一致性.

    Args:
        output_dir:  Qualix 输出根目录（与其他检查保持签名一致，本检查不读取产物）。
        project_id:  项目 ID（与其他检查保持签名一致）。
        code_repos:  代码仓库路径列表（字符串）。

    Returns:
        list[str]，每条以 "WARNING: " 开头。永远不包含 "BLOCKED:"。
    """
    all_warnings: list[str] = []

    for repo_str in code_repos:
        repo = Path(repo_str).expanduser().resolve()
        if not repo.is_dir():
            log.debug("mock_consistency_check: 仓库路径不存在，跳过: %s", repo)
            continue

        # 查找测试目录
        test_roots = [
            repo / "src" / "test" / "java",
            repo / "src" / "test" / "kotlin",
        ]
        for test_root in test_roots:
            if not test_root.is_dir():
                continue
            pattern = "*Test.kt" if "kotlin" in str(test_root) else "*Test.java"
            for java_file in test_root.rglob(pattern):
                file_warnings = _check_single_file(java_file)
                all_warnings.extend(file_warnings)

    return all_warnings
