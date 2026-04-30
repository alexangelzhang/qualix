"""SE Checklist 加载器：从 profile 的 se_checklist.yaml 加载维度，供 Q01 Step 3b 使用。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def load_se_checklist(
    profile_dir: Path,
    prd_text: str = "",
    activated_optionals: set[str] | None = None,
) -> list[dict[str, Any]]:
    """加载 SE checklist 并过滤适用维度。

    Args:
        profile_dir: profile 目录（如 profiles/java-ddd-tmf/）
        prd_text: PRD 文本，用于判断 applies_when 条件
        activated_optionals: 已激活的可选维度 ID 集合（如 {"tmf_extension"}）

    Returns:
        适用的维度列表，每项包含 id/name/questions
    """
    checklist_path = profile_dir / "se_checklist.yaml"
    if not checklist_path.exists():
        return []

    data = _load_yaml(checklist_path)
    if not data or "dimensions" not in data:
        return []

    activated = activated_optionals or set()
    result: list[dict[str, Any]] = []

    for dim in data["dimensions"]:
        if dim.get("optional") and dim["id"] not in activated:
            continue

        applies = dim.get("applies_when", "always")
        if applies != "always" and not _check_applies(applies, prd_text):
            continue

        result.append(
            {
                "id": dim["id"],
                "name": dim["name"],
                "optional": dim.get("optional", False),
                "questions": dim.get("questions", []),
            }
        )

    return result


def format_checklist_prompt(dimensions: list[dict[str, Any]]) -> str:
    """将 checklist 格式化为 LLM 可读的 prompt 片段。"""
    if not dimensions:
        return ""

    lines = ["## SE 推导 Checklist（逐维度扫描）", ""]
    lines.append("对每个 REQ/BR，按以下维度逐一检查，有发现则生成 SE：")
    lines.append("")

    for dim in dimensions:
        tag = "（可选）" if dim.get("optional") else ""
        lines.append(f"### {dim['name']}{tag}")
        for q in dim["questions"]:
            lines.append(f"- {q}")
        lines.append("")

    lines.append("**规则**：每个维度至少扫描一遍。无发现时跳过，不要强行生成 SE。")
    lines.append("有发现时，SE 必须绑定到具体 REQ/BR，且有可验证的判定依据。")

    return "\n".join(lines)


def _check_applies(condition: str, prd_text: str) -> bool:
    """检查 applies_when 条件是否满足。"""
    if not prd_text:
        return True

    keywords = re.findall(r"[一-鿿]{2,}|[a-zA-Z]{3,}", condition)
    text_lower = prd_text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """加载 YAML 文件。优先用 PyYAML，不可用时用简易解析。"""
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        return _parse_yaml_simple(path)
    except Exception:
        return None


def _parse_yaml_simple(path: Path) -> dict[str, Any] | None:
    """简易 YAML 解析（不依赖 PyYAML），只支持 se_checklist 的固定结构。"""
    text = path.read_text(encoding="utf-8")
    dimensions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_questions = False

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- id:"):
            if current:
                dimensions.append(current)
            current = {"id": stripped.split(":", 1)[1].strip(), "questions": []}
            in_questions = False
        elif current is not None:
            if stripped.startswith("name:"):
                current["name"] = stripped.split(":", 1)[1].strip().strip('"')
            elif stripped.startswith("optional:"):
                current["optional"] = stripped.split(":", 1)[1].strip().lower() == "true"
            elif stripped.startswith("applies_when:"):
                current["applies_when"] = stripped.split(":", 1)[1].strip().strip('"')
            elif stripped.startswith("activation:"):
                current["activation"] = stripped.split(":", 1)[1].strip().strip('"')
            elif stripped == "questions:":
                in_questions = True
            elif in_questions and stripped.startswith("- "):
                current["questions"].append(stripped[2:].strip().strip('"'))
            else:
                in_questions = False

    if current:
        dimensions.append(current)

    return {"dimensions": dimensions} if dimensions else None
