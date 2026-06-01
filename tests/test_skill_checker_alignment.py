"""SKILL.md 示例 JSON 与 Pydantic schema 对齐测试.

根因：Q02 产物写了 arch_style 但 schema 要求 architecture_style，导致反复 reset 重跑。
根因：checker 接受 高/中/低 但 SKILL.md 示例写 High/Medium/Low（checker 已修），
     需要自动化检测未来的漂移。

本测试每次修改 SKILL.md 或 Pydantic schema 时都会运行，确保两者不再漂移。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from qualix.schemas.schema_export import json_schema_for_phase, structured_root_model

# SKILL.md 文件路径和对应 Phase
_SKILL_PHASE_MAP: dict[str, str] = {
    "requirement-structuring": "Q01",
    "tech-design-generation": "Q02",
    "tech-quality-review": "Q03",
    "tech-coverage-audit": "Q04",
    "unit-test-design": "Q05a",
    "unit-test-codegen": "Q05b",
    "unit-test-audit": "Q06",
    "code-review": "Q07",
}

_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _extract_product_json_example(skill_name: str) -> dict | None:
    """从 SKILL.md 提取包含 project_id 的第一个 JSON 代码块（产物示例）."""
    skill_path = _SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None
    content = skill_path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.findall(r"```json\n(.*?)\n```", content, re.DOTALL)
    for block in blocks:
        if '"project_id"' not in block:
            continue
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            # 有些示例用了占位符（如 "CRITICAL|HIGH|MEDIUM|LOW"），尝试提取字段名
            # 只提取顶层键名集合，不验证值
            keys = re.findall(r'"(\w+)"\s*:', block)
            if keys and "project_id" in keys:
                return {"_keys_only": True, "_keys": set(keys)}
    return None


def _get_required_fields(phase_id: str) -> set[str]:
    """从 Pydantic schema 获取顶层必填字段."""
    schema = json_schema_for_phase(phase_id)
    if not schema:
        return set()
    return set(schema.get("required", []))


@pytest.mark.parametrize("skill_name,phase_id", list(_SKILL_PHASE_MAP.items()))
def test_skill_json_example_contains_required_fields(skill_name: str, phase_id: str) -> None:
    """SKILL.md JSON 示例必须包含 Pydantic schema 所有必填字段名.

    防止示例写了 arch_style 但 schema 要求 architecture_style 这类漂移。
    """
    example = _extract_product_json_example(skill_name)
    if example is None:
        pytest.skip(f"skills/{skill_name}/SKILL.md 不存在或无 JSON 产物示例")

    required = _get_required_fields(phase_id)
    if not required:
        pytest.skip(f"{phase_id} 无 Pydantic schema 或无 required 字段")

    # 获取示例中的字段名集合
    if example.get("_keys_only"):
        example_keys = example["_keys"]
    else:
        example_keys = set(example.keys())

    missing = required - example_keys
    assert not missing, (
        f"skills/{skill_name}/SKILL.md JSON 示例缺少必填字段：{sorted(missing)}\n"
        f"Schema 要求：{sorted(required)}\n"
        f"示例提供：{sorted(example_keys)}\n"
        f"修复方法：在 SKILL.md JSON 示例中补充这些字段"
    )


@pytest.mark.parametrize("skill_name,phase_id", list(_SKILL_PHASE_MAP.items()))
def test_skill_json_no_unknown_required_fields(skill_name: str, phase_id: str) -> None:
    """SKILL.md JSON 示例不应包含 schema 中不存在的顶层字段名（可能是拼写错误）.

    防止 arch_style、risk_level 等拼写错误被示例"固化"。
    """
    example = _extract_product_json_example(skill_name)
    if example is None or example.get("_keys_only"):
        pytest.skip("无法解析完整 JSON")

    schema = json_schema_for_phase(phase_id)
    if not schema:
        pytest.skip(f"{phase_id} 无 Pydantic schema")

    schema_props = set(schema.get("properties", {}).keys())
    if not schema_props:
        pytest.skip("schema 无 properties 定义")

    example_keys = {k for k in example if not k.startswith("_")}
    # project_id 等公共字段排除
    unknown = example_keys - schema_props - {"project_id"}
    assert not unknown, (
        f"skills/{skill_name}/SKILL.md JSON 示例包含 schema 中不存在的字段：{sorted(unknown)}\n"
        f"Schema 允许字段：{sorted(schema_props)}\n"
        f"可能是拼写错误，请对照 `qualix-run spec --phase {phase_id} --json` 检查"
    )


@pytest.mark.parametrize("skill_name,phase_id", list(_SKILL_PHASE_MAP.items()))
def test_pydantic_schema_exists_for_skill(skill_name: str, phase_id: str) -> None:
    """每个有 SKILL 的 Phase 都应该有对应的 Pydantic schema."""
    skill_path = _SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        pytest.skip(f"skills/{skill_name}/SKILL.md 不存在")
    model = structured_root_model(phase_id)
    assert model is not None, (
        f"{phase_id} 缺少 Pydantic schema 模型。\n"
        f"修复：在 src/qualix/schemas/schema_export.py 的 _PHASE_ROOT_MODELS 中注册"
    )
