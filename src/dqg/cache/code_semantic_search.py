"""代码语义检索增强：SE→Code 自动映射 + 概念映射动态扩展 + 调用链查询.

在现有 code_search.py 基础上增强，零新依赖。
为 Phase B（单测生成）、Phase C（单测审计）、Phase D（代码评审）提供
"根据 SE 描述自动找到对应代码实现"的能力。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.cache.code_search import CONCEPT_MAP, expand_query, index_java_repo, search_code
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. SE→Code 自动映射
# ---------------------------------------------------------------------------


def map_se_to_code(
    output_dir: Path,
    project_id: str,
    repo_path: str,
    limit_per_se: int = 5,
) -> list[dict[str, Any]]:
    """将 Phase A 的 SE 列表自动映射到代码实现.

    Returns:
        [
            {
                "se_id": "SE-001",
                "se_description": "...",
                "code_matches": [
                    {"file": "...", "class": "...", "method": "...", "line": N, "matched_keyword": "..."}
                ],
                "coverage": "FOUND" | "NOT_FOUND"
            }
        ]
    """
    # 加载 Phase A 产物
    from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]
    if not phase_a_path.exists():
        return []

    data = load_json(phase_a_path)
    if not data:
        return []

    se_list = data.get("semantic_expectations", [])
    if not se_list:
        return []

    # 确保代码已索引
    repo = Path(repo_path).resolve()
    indexed = index_java_repo(output_dir, repo)
    log.info("Code index: %d symbols from %s", indexed, repo)

    # 动态扩展概念映射
    dynamic_map = _build_dynamic_concept_map(se_list)

    results: list[dict[str, Any]] = []
    for se in se_list:
        se_id = se.get("se_id", se.get("id", ""))
        desc = se.get("description", "")

        # 从 SE 描述提取搜索关键词
        search_terms = _extract_search_terms(desc, dynamic_map)

        # 搜索代码
        all_matches: list[dict[str, Any]] = []
        seen_keys: set[tuple] = set()

        for term in search_terms[:5]:
            hits = search_code(output_dir, term, repo_path=str(repo), limit=limit_per_se)
            for h in hits:
                key = (h.get("file_path", ""), h.get("line_number", 0))
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_matches.append({
                        "file": h.get("file_path", ""),
                        "class": h.get("parent_symbol", ""),
                        "method": h.get("symbol_name", ""),
                        "line": h.get("line_number", 0),
                        "type": h.get("symbol_type", ""),
                        "signature": h.get("signature", "")[:100],
                        "matched_keyword": h.get("matched_keyword", term),
                    })

        results.append({
            "se_id": se_id,
            "se_description": desc[:100],
            "search_terms": search_terms[:5],
            "code_matches": all_matches[:limit_per_se],
            "coverage": "FOUND" if all_matches else "NOT_FOUND",
        })

    return results


def write_se_code_mapping(
    output_dir: Path,
    project_id: str,
    repo_path: str,
    phase_id: str = "Q06",
) -> Path | None:
    """生成 SE→Code 映射文件，注入 Phase B/C/D.

    Returns:
        写入的文件路径
    """
    mapping = map_se_to_code(output_dir, project_id, repo_path)
    if not mapping:
        return None

    # 写入目标 Phase 目录
    from dqg.constants import PHASE_DIR_MAP
    dir_suffix = PHASE_DIR_MAP.get(phase_id, f"phase{phase_id}")
    phase_dir = output_dir / project_id / dir_suffix
    int_dir = phase_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = int_dir / "_se_code_mapping.json"
    save_json(json_path, {
        "mappings": mapping,
        "total_se": len(mapping),
        "found": sum(1 for m in mapping if m["coverage"] == "FOUND"),
        "not_found": sum(1 for m in mapping if m["coverage"] == "NOT_FOUND"),
    })

    # Markdown
    md_path = int_dir / "_se_code_mapping.md"
    md_path.write_text(_render_mapping_md(mapping), encoding="utf-8")

    found = sum(1 for m in mapping if m["coverage"] == "FOUND")
    log.info("SE→Code mapping: %d/%d SE found code matches", found, len(mapping))
    return json_path


# ---------------------------------------------------------------------------
# 2. 概念映射动态扩展
# ---------------------------------------------------------------------------


def _build_dynamic_concept_map(se_list: list[dict[str, Any]]) -> dict[str, list[str]]:
    """从 SE 描述中提取关键词，动态扩展概念映射.

    不修改全局 CONCEPT_MAP，返回一个临时的扩展映射。
    """
    dynamic: dict[str, list[str]] = {}

    for se in se_list:
        desc = se.get("description", "")
        se_id = se.get("se_id", se.get("id", ""))

        # 提取中文业务词
        chinese_words = re.findall(r"[\u4e00-\u9fff]{2,4}", desc)
        # 提取英文标识符
        english_words = re.findall(r"[A-Z][a-z]+(?:[A-Z][a-z]+)*|[a-z]+(?:_[a-z]+)+", desc)

        if chinese_words or english_words:
            dynamic[se_id] = chinese_words + english_words

    return dynamic


def _extract_search_terms(desc: str, dynamic_map: dict[str, list[str]]) -> list[str]:
    """从 SE 描述中提取搜索关键词（静态映射 + 动态映射）."""
    terms: list[str] = []

    # 1. 静态概念映射匹配
    for concept, keywords in CONCEPT_MAP.items():
        if concept in desc:
            terms.extend(keywords[:3])

    # 2. 从描述中直接提取
    # 中文业务词（2-4 字）
    chinese = re.findall(r"[\u4e00-\u9fff]{2,4}", desc)
    terms.extend(chinese[:5])

    # 英文标识符
    english = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", desc)
    terms.extend(english[:5])

    # 3. 去重
    return list(dict.fromkeys(terms))


# ---------------------------------------------------------------------------
# 3. 调用链查询（复用 blast_radius）
# ---------------------------------------------------------------------------


def _list_java_files(repo: Path) -> list[str]:
    """列出仓库中的 Java 文件（git ls-files 优先，fallback rglob）."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.java"],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception:
        pass
    return [str(f.relative_to(repo)) for f in repo.rglob("*.java")]


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def _render_mapping_md(mapping: list[dict[str, Any]]) -> str:
    """渲染 SE→Code 映射为 Markdown."""
    found = sum(1 for m in mapping if m["coverage"] == "FOUND")
    lines = [
        "## SE_CODE_MAPPING — 语义期望→代码实现映射（自动生成）",
        "",
        f"映射率: {found}/{len(mapping)} SE 找到代码匹配",
        "",
    ]

    for m in mapping:
        icon = "✅" if m["coverage"] == "FOUND" else "❌"
        lines.append(f"### {icon} {m['se_id']}: {m['se_description']}")
        lines.append(f"搜索词: {', '.join(m.get('search_terms', []))}")
        lines.append("")

        if m["code_matches"]:
            for match in m["code_matches"]:
                lines.append(
                    f"- `{match['class']}.{match['method']}` "
                    f"({match['file']}:{match['line']}) "
                    f"[{match['type']}] matched: {match['matched_keyword']}"
                )
        else:
            lines.append("- *未找到匹配代码*")
        lines.append("")

    return "\n".join(lines)
