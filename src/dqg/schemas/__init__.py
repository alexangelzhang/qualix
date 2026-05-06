"""Phase 间数据契约 schema 定义.

每个 Phase 的输入输出都有对应的 Pydantic model，
用于在 Phase 衔接点做结构化校验。
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — used at runtime in validate_phase_output
from types import MappingProxyType
from typing import Final

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json_strict
from dqg.schemas.location import SourceLocation
from dqg.schemas.phase_q01 import PhaseAOutput
from dqg.schemas.phase_q02 import PhaseA3Output
from dqg.schemas.phase_q03 import PhaseA6Output
from dqg.schemas.phase_q04 import PhaseA5Output
from dqg.schemas.phase_q05 import PhaseBOutput
from dqg.schemas.phase_q06 import PhaseCOutput
from dqg.schemas.phase_q07 import PhaseDOutput

__all__ = [
    "PhaseA3Output",
    "PhaseA5Output",
    "PhaseA6Output",
    "PhaseAOutput",
    "PhaseBOutput",
    "PhaseCOutput",
    "PhaseDOutput",
    "SourceLocation",
    "validate_phase_output",
]

# Phase schema class 映射
_SCHEMA_CLASS_MAP: Final = MappingProxyType(
    {
        "Q01": PhaseAOutput,
        "Q02": PhaseA3Output,
        "Q03": PhaseA6Output,
        "Q04": PhaseA5Output,
        "Q05": PhaseBOutput,
        "Q06": PhaseCOutput,
        "Q07": PhaseDOutput,
    }
)

# Phase ID → (目录后缀, 校验文件名, schema class) — 从 constants 组装
_PHASE_REGISTRY: Final = MappingProxyType(
    {pid: (PHASE_DIR_MAP[pid], STRUCTURED_JSON_MAP[pid], _SCHEMA_CLASS_MAP[pid]) for pid in _SCHEMA_CLASS_MAP}
)


def validate_phase_output(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str] | None:
    """校验指定 Phase 的结构化产物.

    Returns:
        None: Phase ID 未注册（不支持校验）
        []: 校验通过
        ["error1", ...]: 校验失败，返回错误列表
    """
    registry = _PHASE_REGISTRY.get(phase_id)
    if registry is None:
        return [f"未知的 Phase ID: {phase_id}"]

    dir_suffix, json_file, schema_cls = registry

    # 查找产物目录
    phase_dir = output_dir / project_id / dir_suffix

    # Q03/Q04 也可能放在 phaseA 目录下（历史兼容）
    if not phase_dir.is_dir() and phase_id in ("Q03", "Q04"):
        phase_dir = output_dir / project_id / PHASE_DIR_MAP["Q01"]

    if not phase_dir.is_dir():
        return [f"产物目录不存在: {dir_suffix}"]

    json_path = phase_dir / json_file
    if not json_path.exists():
        return [f"结构化产物文件不存在: {json_file}"]

    errors: list[str] = []
    try:
        data = load_json_strict(json_path)
    except (json.JSONDecodeError, OSError) as e:
        return [f"JSON 解析失败: {e}"]

    try:
        schema_cls.model_validate(data)
    except Exception as e:
        for err_line in str(e).split("\n"):
            if err_line.strip():
                errors.append(err_line.strip())

    return errors
