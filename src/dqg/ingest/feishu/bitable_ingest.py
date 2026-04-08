"""飞书多维表格（Bitable）解析模块.

当 Wiki 节点 obj_type 为 bitable 时，通过 larkkit CLI 读取所有 sheet 数据，
输出结构化 JSON + plain text。
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.ingest.common import info, warn


def _run_larkkit_bitable(
    args: list[str],
    timeout: int = 120,
) -> tuple[bool, str, str]:
    """调用 larkkit bitable 子命令."""
    cmd = ["uvx", "larkkit", "bitable", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except Exception as e:
        return False, "", str(e)


def _parse_tables_output(stdout: str) -> list[dict[str, str]]:
    """从 larkkit bitable tables 的文本输出中解析 table 列表."""
    tables: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        # 匹配 "1. 数据表" 或 "2. Sheet2" 等
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            if current.get("table_id"):
                tables.append(current)
            current = {"name": m.group(1).strip()}
            continue
        if line.startswith("table_id:"):
            current["table_id"] = line.split(":", 1)[1].strip()
    if current.get("table_id"):
        tables.append(current)
    return tables


def _parse_fields_output(stdout: str) -> list[dict[str, str]]:
    """从 larkkit bitable fields 的文本输出中解析字段定义."""
    fields: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("- ") and not line.startswith("- ID:") and not line.startswith("- 类型"):
            if current.get("name"):
                fields.append(current)
            current = {"name": line[2:].strip()}
            continue
        if line.startswith("ID:"):
            current["id"] = line.split(":", 1)[1].strip()
        elif line.startswith("类型:"):
            current["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("选项:"):
            current["options"] = line.split(":", 1)[1].strip()
    if current.get("name"):
        fields.append(current)
    return fields


def _fetch_all_records(
    app_token: str,
    table_id: str,
    batch_size: int = 500,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """分批获取一个 table 的所有记录."""
    all_records: list[dict[str, Any]] = []
    ok, stdout, stderr = _run_larkkit_bitable(
        ["list", app_token, "--table", table_id, "--output", "json", "--limit", str(batch_size)],
        timeout=timeout,
    )
    if not ok:
        warn(f"读取 bitable 记录失败: table={table_id}, err={stderr[:200]}")
        return all_records

    # 从 stdout 中提取 JSON 数组（跳过 larkkit 的 banner 行）
    json_start = stdout.find("[")
    if json_start < 0:
        return all_records
    try:
        records = json.loads(stdout[json_start:])
        if isinstance(records, list):
            all_records.extend(records)
    except json.JSONDecodeError:
        warn(f"解析 bitable JSON 失败: table={table_id}")

    return all_records


def _flatten_field_value(value: Any) -> str:
    """将 bitable 字段值展平为字符串."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", "") or item.get("name", "") or str(item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    if isinstance(value, dict):
        # 超链接类型
        if "text" in value and "link" in value:
            return value["text"]
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _records_to_plain_text(
    table_name: str,
    fields: list[dict[str, str]],
    records: list[dict[str, Any]],
) -> str:
    """将记录转为可读的 plain text."""
    field_names = [f["name"] for f in fields] if fields else None
    lines = [f"# {table_name}", f"共 {len(records)} 条记录", ""]

    for i, record in enumerate(records, 1):
        record_fields = record.get("fields", {})
        lines.append(f"## 记录 {i}")
        keys = field_names or sorted(record_fields.keys())
        for key in keys:
            if key in record_fields:
                val = _flatten_field_value(record_fields[key])
                if val:
                    lines.append(f"- {key}: {val}")
        lines.append("")

    return "\n".join(lines)


def ingest_bitable(
    app_token: str,
    output_dir: Path,
    timeout: int = 120,
) -> dict[str, Any]:
    """解析飞书多维表格，输出结构化 JSON + plain text.

    Args:
        app_token: bitable 的 app_token
        output_dir: 输出目录
        timeout: 单次 API 调用超时（秒）

    Returns:
        ingest 结果字典
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 获取所有 table
    ok, stdout, stderr = _run_larkkit_bitable(
        ["tables", app_token],
        timeout=timeout,
    )
    if not ok:
        raise RuntimeError(f"获取 bitable 表列表失败: {stderr[:200]}")

    tables = _parse_tables_output(stdout)
    if not tables:
        raise RuntimeError("bitable 中未找到任何数据表")

    info(f"Bitable {app_token}: 发现 {len(tables)} 个数据表")

    # 2. 遍历每个 table，获取字段定义和记录
    all_tables_data: list[dict[str, Any]] = []
    all_plain_text_parts: list[str] = []
    total_records = 0

    for table in tables:
        table_id = table["table_id"]
        table_name = table.get("name", table_id)
        info(f"  读取数据表: {table_name} ({table_id})")

        # 获取字段定义
        ok, stdout, stderr = _run_larkkit_bitable(
            ["fields", app_token, "--table", table_id],
            timeout=timeout,
        )
        fields = _parse_fields_output(stdout) if ok else []

        # 获取所有记录
        records = _fetch_all_records(app_token, table_id, timeout=timeout)
        total_records += len(records)
        info(f"    {len(records)} 条记录, {len(fields)} 个字段")

        table_data = {
            "table_id": table_id,
            "table_name": table_name,
            "field_count": len(fields),
            "record_count": len(records),
            "fields": fields,
            "records": records,
        }
        all_tables_data.append(table_data)

        # 生成 plain text
        plain_text = _records_to_plain_text(table_name, fields, records)
        all_plain_text_parts.append(plain_text)

    # 3. 写入输出文件
    ingest = {
        "source": {
            "type": "bitable",
            "app_token": app_token,
            "generated_at": datetime.now().isoformat(),
        },
        "summary": {
            "table_count": len(tables),
            "total_record_count": total_records,
        },
        "tables": all_tables_data,
    }

    ingest_path = output_dir / "ingest.json"
    plain_text_path = output_dir / "plain_text.txt"

    ingest_path.write_text(
        json.dumps(ingest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    plain_text_path.write_text(
        "\n\n".join(all_plain_text_parts).strip() + "\n",
        encoding="utf-8",
    )

    info(f"Bitable 解析完成: {len(tables)} 表, {total_records} 条记录")

    return {
        "status": "ok",
        "type": "bitable",
        "app_token": app_token,
        "ingest_path": str(ingest_path),
        "plain_text_path": str(plain_text_path),
        "summary": ingest["summary"],
    }
