"""语义级 Guardrail — 检测报告产物中的语义违规.

覆盖规则：
1. BR 概括性描述检测 — BR 条目缺少字段/枚举/校验细节
2. 覆盖度虚高检测 — COVERED 判定无对应证据引用
3. 跨 Phase 越权输出 — Q01/Q02/Q04/Q03 输出 UT/EUT
4. P0 未闭环检测 — 存在 P0 GAP 但给出通过结论
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.quality.guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)


class ReportSemanticGuardrail(PhaseGuardrail):
    """语义级报告质量检测."""

    name = "report_semantic"
    level = GuardrailLevel.WARNING

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        results: list[GuardrailResult] = []
        results.extend(self._check_br_detail(ctx))
        results.extend(self._check_coverage_evidence(ctx))
        results.extend(self._check_cross_phase_violation(ctx))
        results.extend(self._check_p0_unclosed(ctx))
        return results

    # -----------------------------------------------------------------
    # 1. BR 概括性描述检测
    # -----------------------------------------------------------------
    _BR_DETAIL_KEYWORDS = re.compile(
        r"字段|枚举|校验|提示|格式|长度|范围|默认值|必填|可选"
        r"|field|enum|validation|format|length|range|default|required|optional",
        re.IGNORECASE,
    )

    def _check_br_detail(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """BR 条目必须包含具体字段/枚举/校验细节，禁止概括性描述."""
        if ctx.phase_id != "Q01":
            return []

        data = ctx.structured_data
        if not data:
            return []

        results = []
        for req in data.get("requirements", []):
            if not isinstance(req, dict):
                continue
            req_id = req.get("req_id", "")
            if not req_id.startswith("BR-"):
                continue

            desc = str(req.get("description", ""))
            details = str(req.get("details", ""))
            full_text = f"{desc} {details}"

            if len(full_text) < 30 or not self._BR_DETAIL_KEYWORDS.search(full_text):
                results.append(GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.WARNING,
                    message=f"{req_id} 疑似概括性描述，缺少字段/枚举/校验等具体细节",
                    details=[full_text[:100]],
                ))

        return results

    # -----------------------------------------------------------------
    # 2. 覆盖度虚高检测
    # -----------------------------------------------------------------
    def _check_coverage_evidence(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """COVERED 判定必须有对应证据引用."""
        if ctx.phase_id not in ("Q04", "Q06"):
            return []

        report = ctx.report_content
        if not report:
            return []

        results = []
        covered_no_evidence = 0
        for line in report.splitlines():
            # 找到标记为 COVERED 的行
            if "COVERED" in line and "NOT_COVERED" not in line:
                # 检查同一行是否有证据引用（文件名:行号 或 [来源:xxx]）
                has_evidence = bool(
                    re.search(r"\[来源[:：]", line)
                    or re.search(r"\w+\.\w+:\d+", line)  # file.java:123
                    or re.search(r"第\s*\d+\s*行", line)
                    or re.search(r"line\s*\d+", line, re.IGNORECASE)
                )
                if not has_evidence:
                    covered_no_evidence += 1

        if covered_no_evidence > 0:
            results.append(GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"覆盖度虚高风险: {covered_no_evidence} 个 COVERED 判定无证据引用",
                details=[f"count={covered_no_evidence}"],
            ))

        return results

    # -----------------------------------------------------------------
    # 3. 跨 Phase 越权输出
    # -----------------------------------------------------------------
    _UT_PATTERNS = re.compile(
        r"\bEUT[-_]\d+\b"
        r"|\b(单测|单元测试|unit\s*test|test\s*case)\b"
        r"|\b@Test\b"
        r"|\bassert(Equals|True|NotNull|Throws)\b",
        re.IGNORECASE,
    )

    def _check_cross_phase_violation(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q01/Q02/Q04/Q03 禁止输出 UT/EUT 内容."""
        if ctx.phase_id not in ("Q01", "Q02", "Q04", "Q03"):
            return []

        report = ctx.report_content
        if not report:
            return []

        matches = self._UT_PATTERNS.findall(report)
        if len(matches) > 2:  # 容忍偶尔提及，超过 2 次才告警
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"Phase {ctx.phase_id} 疑似越权输出单测内容（发现 {len(matches)} 处 UT/EUT 相关内容）",
                details=[f"matches={len(matches)}"],
            )]

        return []

    # -----------------------------------------------------------------
    # 4. P0 未闭环检测
    # -----------------------------------------------------------------
    def _check_p0_unclosed(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """存在 P0 GAP 时不应给出通过结论."""
        data = ctx.structured_data
        if not data:
            return []

        # 找 P0 GAP
        p0_gaps = []
        for gap in data.get("gaps", []):
            if not isinstance(gap, dict):
                continue
            severity = str(gap.get("severity", gap.get("risk_level", "")))
            status = str(gap.get("status", gap.get("closure_status", "")))
            if "P0" in severity and status.lower() not in ("closed", "resolved", "fixed"):
                p0_gaps.append(gap.get("gap_id", gap.get("id", "?")))

        if not p0_gaps:
            return []

        # 检查报告是否给出了通过结论
        report = ctx.report_content
        pass_patterns = re.compile(
            r"(全部通过|整体通过|质量达标|建议通过|可以通过|PASS|APPROVED)",
            re.IGNORECASE,
        )
        if report and pass_patterns.search(report):
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"存在 {len(p0_gaps)} 个未闭环 P0 GAP 但报告给出通过结论: {', '.join(p0_gaps[:5])}",
                details=[f"p0_gaps={p0_gaps}"],
            )]

        return []
