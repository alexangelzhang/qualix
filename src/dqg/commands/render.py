"""dqg-run render：把 Phase 结构化产物渲染成交互式 HTML (lab).

PoC 限制：仅 Q05。扩展到其他 Phase 时，改 _RENDERERS 注册表与错误提示。
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json
from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.reporting.html_render import render_q05_eut_matrix

_SUPPORTED_PHASES = {"Q05", "Q05a"}
_DEFAULT_OUTPUT_NAME = {"Q05": "eut_matrix.html", "Q05a": "eut_matrix.html"}


def _emit(
    *,
    success: bool,
    exit_code: int,
    project_id: str,
    phase_id: str,
    args: Any,
    data: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> int:
    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="render",
                project_id=project_id,
                success=success,
                exit_code=exit_code,
                phase_id=phase_id,
                extra=data,
                errors=errors,
            )
        )
    else:
        if success and data:
            print(f"✅ Rendered {phase_id} HTML → {data.get('html_path')}")
            print(f"   source: {data.get('source_json')}")
            print(f"   test cases: {data.get('test_case_count')}")
        elif errors:
            for msg in errors:
                print(f"❌ {msg}")
    return exit_code


def cmd_render(args: Any, output_dir: Path) -> int:
    """渲染 Phase 结构化产物为 HTML. PoC 仅支持 Q05."""
    project_id = args.project_id
    phase_id = (getattr(args, "phase", None) or "").upper()

    if phase_id not in _SUPPORTED_PHASES:
        supported = ", ".join(sorted(_SUPPORTED_PHASES))
        return _emit(
            success=False,
            exit_code=2,
            project_id=project_id,
            phase_id=phase_id or "—",
            args=args,
            errors=[f"phase not yet supported in HTML render (PoC limited to: {supported})"],
        )

    phase_dir = output_dir / project_id / PHASE_DIR_MAP[phase_id]
    source_json = phase_dir / STRUCTURED_JSON_MAP[phase_id]

    if not source_json.exists():
        return _emit(
            success=False,
            exit_code=1,
            project_id=project_id,
            phase_id=phase_id,
            args=args,
            errors=[f"SOURCE_NOT_FOUND: {source_json}"],
        )

    # 输出路径：显式 --output 优先，否则用 phase 目录下的默认文件名
    output_override = getattr(args, "output", None)
    if output_override:
        output_path = Path(output_override).resolve()
    else:
        output_path = phase_dir / _DEFAULT_OUTPUT_NAME[phase_id]

    try:
        result = render_q05_eut_matrix(source_json, output_path)
    except (FileNotFoundError, ValueError) as e:
        return _emit(
            success=False,
            exit_code=1,
            project_id=project_id,
            phase_id=phase_id,
            args=args,
            errors=[f"RENDER_FAILED: {type(e).__name__}: {e}"],
        )

    if getattr(args, "open", False):
        webbrowser.open(f"file://{result['html_path']}")

    return _emit(
        success=True,
        exit_code=0,
        project_id=project_id,
        phase_id=phase_id,
        args=args,
        data=result,
    )
