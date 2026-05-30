"""Evidence Contract 验证器：SE.source 跨引用 + EUT code_target grep。"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)


def verify_se_sources(
    phase_root: Path,
    se_list: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """验证每条 SE.source 指向的 ingest 文件行号真实存在。

    Args:
        phase_root: Q01 phase 目录（含 ingest/ 子目录）
        se_list:    phase_a_structured.json 中的 semantic_expectations 列表

    Returns:
        (errors, evidence_entries)
        errors: BLOCKED:/WARNING: 字符串，直接 extend 到 result.errors
        evidence_entries: 写入 _se_source_evidence.json 的条目列表
    """
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    ingest_dir = phase_root / "ingest"
    verified_at = datetime.now(UTC).isoformat()

    for se in se_list:
        se_id = se.get("se_id", "?")
        source_raw = (se.get("source") or "").strip()

        if not source_raw:
            entries.append(
                {
                    "se_id": se_id,
                    "source_raw": "",
                    "status": "empty_source",
                    "verified_at": verified_at,
                }
            )
            errors.append(f"WARNING: [evidence_contract] {se_id} source 未填写，无法追溯 PRD 原始依据")
            continue

        if ":" not in source_raw:
            entries.append(
                {
                    "se_id": se_id,
                    "source_raw": source_raw,
                    "status": "invalid_format",
                    "verified_at": verified_at,
                }
            )
            errors.append(f"WARNING: [evidence_contract] {se_id} source '{source_raw}' 格式无效，期望 'file.txt:行号'")
            continue

        last_colon = source_raw.rfind(":")
        filename = source_raw[:last_colon]
        try:
            line_num = int(source_raw[last_colon + 1 :])
        except ValueError:
            entries.append(
                {
                    "se_id": se_id,
                    "source_raw": source_raw,
                    "status": "invalid_format",
                    "verified_at": verified_at,
                }
            )
            errors.append(f"WARNING: [evidence_contract] {se_id} source '{source_raw}' 行号非整数")
            continue

        file_path = ingest_dir / filename
        if not file_path.exists():
            entries.append(
                {
                    "se_id": se_id,
                    "source_raw": source_raw,
                    "source_file": filename,
                    "source_line": line_num,
                    "status": "file_missing",
                    "verified_at": verified_at,
                }
            )
            errors.append(f"BLOCKED: [evidence_contract] {se_id} source '{source_raw}' 指向的 ingest 文件不存在")
            continue

        all_lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line_num < 1 or line_num > len(all_lines):
            entries.append(
                {
                    "se_id": se_id,
                    "source_raw": source_raw,
                    "source_file": filename,
                    "source_line": line_num,
                    "status": "line_oob",
                    "verified_at": verified_at,
                    "file_total_lines": len(all_lines),
                }
            )
            errors.append(
                f"BLOCKED: [evidence_contract] {se_id} source '{source_raw}' 行号超出范围 (文件共 {len(all_lines)} 行)"
            )
            continue

        line_text = all_lines[line_num - 1]
        ctx_start = max(0, line_num - 3)
        ctx_end = min(len(all_lines), line_num + 2)
        context_lines = all_lines[ctx_start:ctx_end]
        context_hash = hashlib.sha256(line_text.encode()).hexdigest()[:16]

        entries.append(
            {
                "se_id": se_id,
                "source_raw": source_raw,
                "source_file": filename,
                "source_line": line_num,
                "line_text": line_text,
                "context_lines": context_lines,
                "context_hash": context_hash,
                "status": "ok",
                "verified_at": verified_at,
            }
        )

    return errors, entries


def check_eut_code_target_traceability(
    output_dir: Path,
    project_id: str,
    code_repos: list[str],
) -> list[str]:
    """Q05a: 对每条 EUT，追踪 bound_item → SE.code_target → grep 代码仓库。

    SE.code_target 为空时跳过。grep 不到始终是 WARNING（不 BLOCKED），
    因为 TDD 场景下 impl 可能尚未存在。
    """
    from qualix.constants import STRUCTURED_JSON_MAP
    from qualix.core.phase_registry import PHASE_DEFS
    from qualix.core.state_machine import phase_dir as _phase_dir
    from qualix.json_utils import load_json

    if not code_repos:
        return []

    phase_def_q01 = PHASE_DEFS.get("Q01")
    if not phase_def_q01:
        return []
    q01_json = _phase_dir(output_dir, project_id, phase_def_q01) / STRUCTURED_JSON_MAP.get(
        "Q01", "phase_a_structured.json"
    )
    q01_data = load_json(q01_json) if q01_json.is_file() else {}
    se_code_target: dict[str, str] = {
        se["se_id"]: se.get("code_target", "")
        for se in (q01_data or {}).get("semantic_expectations", [])
        if se.get("se_id")
    }

    phase_def_q05a = PHASE_DEFS.get("Q05a")
    if not phase_def_q05a:
        return []
    q05a_json = _phase_dir(output_dir, project_id, phase_def_q05a) / STRUCTURED_JSON_MAP.get(
        "Q05a", "phase_b_structured.json"
    )
    q05a_data = load_json(q05a_json) if q05a_json.is_file() else {}
    eut_items = (q05a_data or {}).get("eut_items", [])

    errors: list[str] = []
    for eut in eut_items:
        eut_id = eut.get("eut_id", "?")
        bound = (eut.get("bound_item") or eut.get("bound_se") or "").strip()
        if not bound.startswith("SE-"):
            continue
        code_target = se_code_target.get(bound, "")
        if not code_target:
            continue

        class_name = code_target.split(".")[0].strip()
        if not class_name:
            continue

        found = False
        for repo_str in code_repos:
            repo_path = Path(repo_str).expanduser().resolve()
            if not repo_path.is_dir():
                continue
            try:
                result = subprocess.run(
                    ["grep", "-rl", "-F", class_name, str(repo_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.stdout.strip():
                    found = True
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                log.debug("grep failed for %s in %s", class_name, repo_path)

        if not found:
            errors.append(
                f"WARNING: [evidence_contract] {eut_id} bound {bound}.code_target"
                f" '{class_name}' 在代码仓库中未找到，请确认实现类名"
            )

    return errors
