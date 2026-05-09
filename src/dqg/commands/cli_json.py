"""CLI --json：stdout 单条 JSON，供 Agent / SubAgent 解析."""

from __future__ import annotations

import json
from typing import Any

# Envelope schema 版本号：将来改字段结构时加 2/3，Agent 可据此做兼容切换。
# 改动规则：
#   - 加可选字段 → 不升级版本（向后兼容）
#   - 删字段/改字段语义 → 升级版本号
CLI_ENVELOPE_SCHEMA_VERSION = "1"


def cli_json_mode(args: Any) -> bool:
    return bool(getattr(args, "json", False))


def print_cli_json(obj: dict[str, Any]) -> None:
    """写入 stdout 一条 JSON（UTF-8）."""
    print(json.dumps(obj, ensure_ascii=False, default=str))


def cli_envelope(
    *,
    command: str,
    project_id: str,
    success: bool,
    exit_code: int,
    phase_id: str | None = None,
    phase_result: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    notices: list[str] | None = None,
) -> dict[str, Any]:
    """统一外壳字段（与 PhaseResult 可并存）.

    字段约定（schema_version=1）：
        schema_version: 协议版本号，Agent 应先检查再解析
        success / exit_code / command / project_id: 必须字段
        phase_id / phase_result: Phase 相关场景（execute/finalize/approve 等）
        data: 命令特有 payload（如 metrics / spec 下的 contract）
        errors: 失败原因列表（success=False 时）
        warnings: 非致命警告（success=True 但值得留意）
        notices: 运行环境提示（如 "worktree output 重定向到..."），
                 不影响 success/verdict，但 Agent 可用于日志/诊断
    """
    out: dict[str, Any] = {
        "schema_version": CLI_ENVELOPE_SCHEMA_VERSION,
        "success": success,
        "exit_code": exit_code,
        "command": command,
        "project_id": project_id,
    }
    if phase_id:
        out["phase_id"] = phase_id
    if phase_result is not None:
        out["phase_result"] = phase_result
    if extra:
        out["data"] = extra
    if errors:
        out["errors"] = list(errors)
    if warnings:
        out["warnings"] = list(warnings)
    if notices:
        out["notices"] = list(notices)
    return out
