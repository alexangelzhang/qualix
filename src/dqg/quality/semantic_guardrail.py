"""语义级 Guardrail — 检测报告产物中的语义违规.

覆盖规则：
1. BR 概括性描述检测 — BR 条目缺少字段/枚举/校验细节
2. 覆盖度虚高检测 — COVERED 判定无对应证据引用
3. 跨 Phase 越权输出 — Q01/Q02/Q04/Q03 输出 UT/EUT
4. P0 未闭环检测 — 存在 P0 GAP 但给出通过结论
5. 发现缺代码证据 — Q03/Q06/Q07 findings 无 file:line
6. 覆盖状态概括性描述 — Q04 使用模糊词汇而非原文引用
7. GAP/OPEN 闭环字段为空 — Q04 闭环状态未填写
8. 仅凭代码推导需求 — Q06 未引用 Phase Q01 ID
9. 孤立分析无调用链 — Q07 评审无调用链上下文
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
        results.extend(self._check_findings_code_evidence(ctx))
        results.extend(self._check_coverage_description_vague(ctx))
        results.extend(self._check_gap_open_closure_empty(ctx))
        results.extend(self._check_code_only_derivation(ctx))
        results.extend(self._check_isolated_analysis(ctx))
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

    # -----------------------------------------------------------------
    # 5. 发现缺代码证据（Q03/Q06/Q07）
    # -----------------------------------------------------------------
    _CODE_EVIDENCE_PATTERN = re.compile(
        r"\w+\.\w+:\d+"           # file.java:123
        r"|第\s*\d+\s*行"         # 第42行
        r"|line\s*\d+"            # line 42
        r"|\[来源[:：]",          # [来源: xxx]
        re.IGNORECASE,
    )

    def _check_findings_code_evidence(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q03/Q06/Q07 的 findings/issues 必须有代码证据（file:line）."""
        if ctx.phase_id not in ("Q03", "Q06", "Q07"):
            return []

        data = ctx.structured_data
        if not data:
            return []

        # 检查 findings 或 issues 列表
        items = data.get("findings", []) or data.get("issues", []) or data.get("audit_items", [])
        if not items:
            return []

        no_evidence_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            # 拼接所有文本字段
            text = " ".join(
                str(item.get(k, ""))
                for k in ("description", "detail", "evidence", "location", "file", "code_ref")
            )
            if not self._CODE_EVIDENCE_PATTERN.search(text):
                no_evidence_count += 1

        if no_evidence_count > 0:
            total = len([i for i in items if isinstance(i, dict)])
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"Phase {ctx.phase_id}: {no_evidence_count}/{total} 条发现缺少代码证据（file:line）",
                details=[f"no_evidence={no_evidence_count}"],
            )]

        return []

    # -----------------------------------------------------------------
    # 6. 覆盖状态概括性描述（Q04）
    # -----------------------------------------------------------------
    _VAGUE_COVERAGE_PATTERN = re.compile(
        r"(基本覆盖|大致覆盖|大概覆盖|整体覆盖|覆盖较好|覆盖较全|已覆盖大部分|大部分已覆盖)",
    )

    def _check_coverage_description_vague(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q04 覆盖状态禁止概括性描述，必须引用技术方案原文."""
        if ctx.phase_id != "Q04":
            return []

        report = ctx.report_content
        if not report:
            return []

        matches = self._VAGUE_COVERAGE_PATTERN.findall(report)
        if matches:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"覆盖度报告使用概括性描述 {len(matches)} 处（如 '{matches[0]}'），应引用技术方案原文作为证据",
                details=[f"matches={matches[:5]}"],
            )]

        return []

    # -----------------------------------------------------------------
    # 7. GAP/OPEN 闭环字段为空（Q04）
    # -----------------------------------------------------------------
    def _check_gap_open_closure_empty(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q04 的 GAP/OPEN 必须有闭环状态，不能留空."""
        if ctx.phase_id != "Q04":
            return []

        data = ctx.structured_data
        if not data:
            return []

        results = []
        empty_closure = 0

        for gap in data.get("gap_closure", data.get("gaps", [])):
            if not isinstance(gap, dict):
                continue
            closure = str(gap.get("closure_status", gap.get("status", ""))).strip()
            if not closure:
                empty_closure += 1

        for item in data.get("open_closure", data.get("open_items", [])):
            if not isinstance(item, dict):
                continue
            closure = str(item.get("closure_status", item.get("status", ""))).strip()
            if not closure:
                empty_closure += 1

        if empty_closure > 0:
            results.append(GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message=f"Q04: {empty_closure} 个 GAP/OPEN 条目闭环状态为空",
                details=[f"empty_closure={empty_closure}"],
            ))

        return results

    # -----------------------------------------------------------------
    # 8. 仅凭代码推导需求（Q06 无 Q01 ID 引用）
    # -----------------------------------------------------------------
    _REQ_ID_PATTERN = re.compile(r"\b(REQ|BR|SE)-\d{1,4}\b")

    def _check_code_only_derivation(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q06 审计必须引用 Phase Q01 产物（REQ/BR/SE ID），不能仅凭代码推导."""
        if ctx.phase_id != "Q06":
            return []

        report = ctx.report_content
        if not report:
            return []

        req_refs = self._REQ_ID_PATTERN.findall(report)
        if not req_refs:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message="Q06 审计报告未引用任何 Phase Q01 ID（REQ/BR/SE），疑似仅凭代码推导需求",
            )]

        return []

    # -----------------------------------------------------------------
    # 9. 孤立分析无调用链（Q07）
    # -----------------------------------------------------------------
    _CALL_CHAIN_PATTERN = re.compile(
        r"(调用链|调用方|被调用|caller|callee|upstream|downstream"
        r"|→|->|链路|上游|下游|依赖方|消费方)",
        re.IGNORECASE,
    )

    def _check_isolated_analysis(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        """Q07 代码评审禁止孤立分析，必须有调用链上下文."""
        if ctx.phase_id != "Q07":
            return []

        report = ctx.report_content
        if not report:
            return []

        # 检查报告中是否有调用链相关描述
        chain_refs = self._CALL_CHAIN_PATTERN.findall(report)
        # 如果报告超过 500 字但没有任何调用链引用，告警
        if len(report) > 500 and not chain_refs:
            return [GuardrailResult(
                guardrail_name=self.name,
                passed=False,
                level=GuardrailLevel.WARNING,
                message="Q07 评审报告未包含调用链上下文，疑似孤立分析单个类/方法",
            )]

        return []
