"""HTML 渲染器 (lab) — 把 Phase 结构化 JSON 渲染成交互式单文件 HTML.

PoC 范围：仅 Q05 (EUT Matrix)。设计原则：
- 零外部依赖（不引 Jinja / BeautifulSoup），纯 str.replace 做占位符替换
- 渲染函数保持纯函数：只读输入路径 + 写输出路径，不 print / 不 sys.exit
- 输出单文件 HTML，内联 CSS/JS，浏览器直开，无 CDN/字体/图片依赖

扩展到第二个 Phase 时（YAGNI 已破）再抽通用渲染器 registry。
"""

from __future__ import annotations

import json
from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json_strict

_TEMPLATE_PACKAGE = "dqg.reporting.templates"
_Q05_TEMPLATE = "q05_eut_matrix.html"


def _load_template(name: str) -> str:
    return resources.files(_TEMPLATE_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _escape_json_for_script_tag(data_json: str) -> str:
    # 避免 JSON 数据里偶然出现 </script> 闭合 <script type=application/json>。
    # scenario 是中文自由文本，保险起见做一次替换。
    return data_json.replace("</", "<\\/")


def render_q05_eut_matrix(
    structured_json_path: Path | str,
    output_path: Path | str,
) -> dict[str, Any]:
    """渲染 Q05 phase_b_structured.json 为交互式 HTML kanban.

    Args:
        structured_json_path: Q05 结构化 JSON 源路径
        output_path: HTML 输出路径（会覆盖）

    Returns:
        {"html_path": str, "source_json": str, "test_case_count": int, "project_id": str}

    Raises:
        FileNotFoundError: 源 JSON 不存在
        ValueError: 源 JSON 缺少必要字段（project_id/test_cases）
        json.JSONDecodeError: 源 JSON 格式错误
    """
    src = Path(structured_json_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Q05 structured JSON not found: {src}")

    payload = load_json_strict(src)

    if not isinstance(payload, dict):
        raise ValueError(f"Q05 JSON root must be object, got {type(payload).__name__}")
    if "test_cases" not in payload:
        raise ValueError("Q05 JSON missing 'test_cases' key")

    test_cases = payload.get("test_cases") or []
    project_id = str(payload.get("project_id") or "unknown")
    generated_at = datetime.now().isoformat(timespec="seconds")

    # 注入生成时间到嵌入 payload（供 HTML 页面展示）
    embedded = dict(payload)
    embedded["_generated_at"] = generated_at

    data_json = _escape_json_for_script_tag(json.dumps(embedded, ensure_ascii=False, separators=(",", ":")))

    template = _load_template(_Q05_TEMPLATE)
    html = (
        template.replace("{{PROJECT_ID}}", project_id)
        .replace("{{GENERATED_AT}}", generated_at)
        .replace("{{DATA_JSON}}", data_json)
    )

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(html, encoding="utf-8")

    return {
        "html_path": str(dst.resolve()),
        "source_json": str(src.resolve()),
        "test_case_count": len(test_cases),
        "project_id": project_id,
    }
