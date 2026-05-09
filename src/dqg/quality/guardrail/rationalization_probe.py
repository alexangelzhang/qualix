"""T11: 结构化产物字段级放水关键词探测（RationalizationProbe）.

对 Q03 failure_modes 与 Q06 findings/audit 文本做 Layer1 正则扫描，
与 `RationalizationGuard` 共用 `RATIONALIZATION_PATTERNS`。命中仅 WARNING，
避免与语义层 BLOCK 叠加导致误杀；用于提示人工复核。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.constants import RATIONALIZATION_PATTERNS, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json
from dqg.quality.guardrail.guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)

_COMPILED: list[tuple[str, re.Pattern[str]]] = [(p, re.compile(p)) for p in RATIONALIZATION_PATTERNS]
_MAX_HITS = 12


def _scan_field(text: str, field_label: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    s = str(text).replace("\n", " ")
    hits: list[str] = []
    for pattern_str, compiled in _COMPILED:
        if compiled.search(s):
            snippet = s[:120]
            suf = "…" if len(s) > 120 else ""
            hits.append(f"{field_label}: 命中 `{pattern_str}` — 「{snippet}{suf}」")
    return hits


def _collect_q03_hits(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for i, fm in enumerate(data.get("failure_modes") or []):
        if not isinstance(fm, dict):
            continue
        prefix = f"failure_modes[{i}]"
        for key in ("business_path", "failure_scenario", "user_impact"):
            out.extend(_scan_field(str(fm.get(key, "")), f"{prefix}.{key}"))
            if len(out) >= _MAX_HITS:
                return out
    for i, issue in enumerate(data.get("issues") or []):
        if not isinstance(issue, dict):
            continue
        prefix = f"issues[{i}]"
        for key in ("description", "suggestion"):
            out.extend(_scan_field(str(issue.get(key, "")), f"{prefix}.{key}"))
            if len(out) >= _MAX_HITS:
                return out
    return out


def _collect_q06_hits(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for i, f in enumerate(data.get("findings") or []):
        if not isinstance(f, dict):
            continue
        prefix = f"findings[{i}]"
        for key in ("title", "description", "impact", "recommendation"):
            out.extend(_scan_field(str(f.get(key, "")), f"{prefix}.{key}"))
            if len(out) >= _MAX_HITS:
                return out
    for i, a in enumerate(data.get("audit_items") or []):
        if not isinstance(a, dict):
            continue
        prefix = f"audit_items[{i}]"
        for key in ("description", "notes", "recommendation"):
            out.extend(_scan_field(str(a.get(key, "")), f"{prefix}.{key}"))
            if len(out) >= _MAX_HITS:
                return out
    return out


class RationalizationProbeGuardrail(PhaseGuardrail):
    """对结构化 JSON 选定字段做放水关键词扫描（WARNING）。"""

    name = "rationalization_probe_structured"
    level = GuardrailLevel.WARNING

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        phase_id = (ctx.phase_id or "").strip().upper()
        if phase_id not in ("Q03", "Q06"):
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="RationalizationProbe 仅适用于 Q03/Q06",
                )
            ]

        if not ctx.phase_dir:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="无 phase_dir，跳过 RationalizationProbe",
                )
            ]

        fname = STRUCTURED_JSON_MAP.get(phase_id)
        if not fname:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="无结构化文件名映射，跳过",
                )
            ]

        path: Path = ctx.phase_dir / fname
        data = load_json(path)
        if not isinstance(data, dict):
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message=f"未找到或可解析的 {fname}，跳过字段级放水探测",
                )
            ]

        hits = _collect_q03_hits(data) if phase_id == "Q03" else _collect_q06_hits(data)
        if not hits:
            return [
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="结构化字段未命中已知放水关键词模式",
                )
            ]

        return [
            GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"结构化输出中疑似放水表述 {len(hits)} 处（请人工复核，非自动拦截）",
                details=hits[:_MAX_HITS],
            )
        ]
