"""LLM 输出结构化重试.

当 Phase 产物的 JSON 校验失败时，提供重试策略：
1. 尝试修复常见 JSON 格式问题
2. 简化 payload（移除可选字段）重试
3. 最终降级为仅 markdown 报告
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from dqg.json_utils import dump_json_str
from dqg.log import get_logger

log = get_logger(__name__)


def fix_common_json_issues(raw: str) -> str:
    """修复常见的 LLM 输出 JSON 格式问题."""
    # 移除 markdown 代码块包裹
    raw = re.sub(r"^```json\s*\n?", "", raw.strip())
    raw = re.sub(r"\n?```\s*$", "", raw.strip())

    # 移除尾部逗号 (trailing comma before } or ])
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    # 修复单引号为双引号
    # 只在明显是 JSON key/value 的场景替换，避免误伤内容中的撇号
    if raw.startswith("{") or raw.startswith("["):
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            # 尝试单引号替换
            fixed = raw.replace("'", '"')
            try:
                json.loads(fixed)
                return fixed
            except json.JSONDecodeError:
                log.debug("fix_common_json_issues: both parse attempts failed for %.60r", raw)

    return raw


def simplify_payload(data: dict, required_keys: set[str] | None = None) -> dict:
    """简化 payload，只保留必填字段."""
    if required_keys is None:
        # 默认必填字段
        required_keys = {"project_id", "requirements", "conclusion", "findings", "eut_items", "audit_items"}

    simplified = {}
    for key, value in data.items():
        if key in required_keys:
            simplified[key] = value
        elif isinstance(value, list) and value:
            # 保留非空列表但截断
            simplified[key] = value[:10] if len(value) > 10 else value
        elif isinstance(value, str) and len(value) > 500:
            # 截断长字符串
            simplified[key] = value[:500] + "..."
        else:
            simplified[key] = value

    return simplified


def try_parse_structured_output(
    raw_content: str,
    retry_limit: int = 3,
) -> tuple[dict | None, list[str]]:
    """尝试解析 LLM 的结构化 JSON 输出，支持重试.

    Returns:
        (parsed_dict, errors): 成功返回 (dict, [])，失败返回 (None, [error1, ...])
    """
    errors: list[str] = []

    for attempt in range(retry_limit):
        content = raw_content if attempt == 0 else fix_common_json_issues(raw_content)

        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data, []
            errors.append(f"Attempt {attempt + 1}: JSON 解析成功但不是 dict，类型为 {type(data).__name__}")
        except json.JSONDecodeError as e:
            errors.append(f"Attempt {attempt + 1}: JSON 解析失败 — {e}")

            # 尝试提取 JSON 块
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    if isinstance(data, dict):
                        return data, []
                except json.JSONDecodeError:
                    errors.append(f"Attempt {attempt + 1}: 提取 JSON 块后仍然解析失败")

    return None, errors


def write_structured_output(
    output_path: Path,
    data: dict,
    retry_limit: int = 3,
) -> tuple[bool, list[str]]:
    """将结构化数据写入 JSON 文件，支持重试.

    Returns:
        (success, errors)
    """
    errors: list[str] = []

    for attempt in range(retry_limit):
        try:
            payload = data if attempt == 0 else simplify_payload(data)
            content = dump_json_str(payload)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            return True, []
        except (TypeError, ValueError) as e:
            errors.append(f"Attempt {attempt + 1}: JSON 序列化失败 — {e}")
            # 下一轮用简化后的 payload 重试

    # 最终降级：写 markdown
    try:
        md_path = output_path.with_suffix(".md")
        md_content = f"# 结构化输出降级为 Markdown\n\n> JSON 序列化失败，降级为文本格式\n\n```\n{data}\n```\n"
        md_path.write_text(md_content, encoding="utf-8")
        errors.append(f"已降级为 Markdown: {md_path}")
    except Exception as e:
        errors.append(f"Markdown 降级也失败: {e}")

    return False, errors
