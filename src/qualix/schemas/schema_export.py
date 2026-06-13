"""Phase 结构化产物 → Pydantic JSON Schema 导出（供 qualix-run spec）."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel  # noqa: TC002 — 用于运行时 dict 值类型，不是纯 typing 标注

from qualix.schemas.phase_q01 import PhaseAOutput
from qualix.schemas.phase_q02 import PhaseA3Output
from qualix.schemas.phase_q03 import PhaseA6Output
from qualix.schemas.phase_q04 import PhaseA5Output
from qualix.schemas.phase_q05 import PhaseBCodeStatusOutput, PhaseBOutput
from qualix.schemas.phase_q06 import PhaseCOutput
from qualix.schemas.phase_q07 import PhaseDOutput

_PHASE_ROOT_MODELS: dict[str, type[BaseModel]] = {
    "Q01": PhaseAOutput,
    "Q02": PhaseA3Output,
    "Q03": PhaseA6Output,
    "Q04": PhaseA5Output,
    "Q05a": PhaseBOutput,
    "Q05b": PhaseBCodeStatusOutput,
    "Q06": PhaseCOutput,
    "Q07": PhaseDOutput,
}


def structured_root_model(phase_id: str) -> type[BaseModel] | None:
    return _PHASE_ROOT_MODELS.get(phase_id)


def json_schema_for_phase(phase_id: str) -> dict[str, Any] | None:
    """返回 Phase 产物的 Pydantic v2 ``model_json_schema``；无模型时返回 None.

    **注意**：
    - ``mode='serialization'`` + ``by_alias=True``：Agent 关心的是 **输出形态**
      （结构化产物会被 Judge/下游 Phase 消费），不是"接受任何合法输入"。
    - JSON Schema **不覆盖** ``field_validator`` / ``model_validator`` 的动态校验。
      例如 PhaseAOutput 的 "至少一个 REQ 级需求" 规则只在 Pydantic 运行时生效，
      schema 只展示字段类型/required 标记。Agent 生成产物后仍需跑 Pydantic
      validate 才能确认完全合规。
    """
    model = structured_root_model(phase_id)
    if model is None:
        return None
    try:
        return model.model_json_schema(mode="serialization", by_alias=True)
    except Exception as e:  # pragma: no cover - 动态 schema 边界
        return {"_export_error": str(e), "phase_id": phase_id}
