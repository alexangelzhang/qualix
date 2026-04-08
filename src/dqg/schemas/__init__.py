"""Phase 间数据契约 schema 定义.

每个 Phase 的输入输出都有对应的 Pydantic model，
用于在 Phase 衔接点做结构化校验。
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — used at runtime in validate_phase_output

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json_strict
from dqg.schemas.phase_a import PhaseAOutput
from dqg.schemas.phase_a3 import PhaseA3Output
from dqg.schemas.phase_a5 import PhaseA5Output
from dqg.schemas.phase_a6 import PhaseA6Output
from dqg.schemas.phase_b import PhaseBOutput
from dqg.schemas.phase_c import PhaseCOutput
from dqg.schemas.phase_d import PhaseDOutput

__all__ = [
    "PhaseA3Output",
    "PhaseA5Output",
    "PhaseA6Output",
    "PhaseAOutput",
    "PhaseBOutput",
    "PhaseCOutput",
    "PhaseDOutput",
    "validate_phase_output",
]

# Phase schema class 映射
_SCHEMA_CLASS_MAP: dict[str, type] = {
    "A": PhaseAOutput,
    "A.3": PhaseA3Output,
    "A.5": PhaseA5Output,
    "A.6": PhaseA6Output,
    "B": PhaseBOutput,
    "C": PhaseCOutput,
    "D": PhaseDOutput,
}

# Phase ID → (目录后缀, 校验文件名, schema class) — 从 constants 组装
_PHASE_REGISTRY: dict[str, tuple[str, str, type]] = {
    pid: (PHASE_DIR_MAP[pid], STRUCTURED_JSON_MAP[pid], _SCHEMA_CLASS_MAP[pid])
    for pid in _SCHEMA_CLASS_MAP
}


def validate_phase_output(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str] | None:
    """校验指定 Phase 的结构化产物.

    Returns:
        None: 产物文件不存在（跳过）
        []: 校验通过
        ["error1", ...]: 校验失败，返回错误列表
    """
    registry = _PHASE_REGISTRY.get(phase_id)
    if registry is None:
        return [f"未知的 Phase ID: {phase_id}"]

    dir_suffix, json_file, schema_cls = registry

    # 查找产物目录
    phase_dir = output_dir / project_id / dir_suffix

    # A.5/A.6 也可能放在 phaseA 目录下
    if not phase_dir.is_dir() and phase_id in ("A.5", "A.6"):
        phase_dir = output_dir / project_id / PHASE_DIR_MAP["A"]

    if not phase_dir.is_dir():
        return None

    json_path = phase_dir / json_file
    if not json_path.exists():
        return None

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
