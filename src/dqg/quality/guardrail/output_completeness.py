"""Output Completeness Guardrail — 截断检测 + 最小长度门槛.

借鉴 DeepCode 的 Output Completeness Scoring 思路，
用纯规则零 LLM 成本检测报告截断和内容不足。
在 finalize 前拦截，避免 Judge 浪费 token 评审残缺报告。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dqg.log import get_logger

from .guardrail import (
    GuardrailContext,
    GuardrailLevel,
    GuardrailResult,
    PhaseGuardrail,
)

log = get_logger(__name__)

# 按 Phase 的最小报告长度（字符数）
# 低于此值说明报告明显不完整
_MIN_REPORT_LENGTH: dict[str, int] = {
    "Q01": 500,  # 需求分析
    "Q02": 800,  # 技术方案
    "Q03": 500,  # 技术方案评审
    "Q04": 300,  # 覆盖度矩阵
    "Q05": 600,  # 单测生成
    "Q06": 600,  # 单测审计
    "Q07": 500,  # Code Review
}
_DEFAULT_MIN_LENGTH = 300

# 正常结尾标记
_VALID_ENDINGS = re.compile(r"[。.!?！？\n\]\}\)`>*\-]$")

# 截断信号：末行过长且无正常结尾
_TRUNCATION_LINE_THRESHOLD = 150


@dataclass
class OutputCompletenessGuardrail(PhaseGuardrail):
    """检测报告截断和内容不足."""

    name: str = "output_completeness"
    level: GuardrailLevel = GuardrailLevel.WARNING

    def check(self, ctx: GuardrailContext) -> list[GuardrailResult]:
        results: list[GuardrailResult] = []

        report_text = self._load_report(ctx)
        if report_text is None:
            return results  # 报告不存在，其他 guardrail 会处理

        # 1. 最小长度检查
        min_len = _MIN_REPORT_LENGTH.get(ctx.phase_id, _DEFAULT_MIN_LENGTH)
        if len(report_text) < min_len:
            results.append(
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.WARNING,
                    message=f"报告长度不足：{len(report_text)} 字符 < 最小阈值 {min_len}",
                    details=[f"Phase {ctx.phase_id} 报告预期至少 {min_len} 字符"],
                )
            )

        # 2. 截断检测
        truncation = self._detect_truncation(report_text)
        if truncation:
            results.append(
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=False,
                    level=GuardrailLevel.WARNING,
                    message="报告疑似被 token 限制截断",
                    details=truncation,
                )
            )

        if not results:
            results.append(
                GuardrailResult(
                    guardrail_name=self.name,
                    passed=True,
                    level=GuardrailLevel.INFO,
                    message="报告完整性检查通过",
                )
            )

        return results

    def _load_report(self, ctx: GuardrailContext) -> str | None:
        """加载 Phase 报告文本."""
        from dqg.constants import PHASE_DIR_MAP, REPORT_MAP

        dir_suffix = PHASE_DIR_MAP.get(ctx.phase_id, "")
        report_file = REPORT_MAP.get(ctx.phase_id, "phase_report.md")
        report_path = ctx.output_dir / ctx.project_id / dir_suffix / report_file

        if not report_path.exists():
            return None
        try:
            return report_path.read_text(encoding="utf-8")
        except OSError:
            return None

    @staticmethod
    def _detect_truncation(text: str) -> list[str]:
        """检测截断信号."""
        signals: list[str] = []
        lines = text.rstrip().splitlines()
        if not lines:
            return ["报告为空"]

        last_line = lines[-1].rstrip()

        # 信号 1：末行过长且无正常结尾
        if len(last_line) > _TRUNCATION_LINE_THRESHOLD and not _VALID_ENDINGS.search(last_line):
            signals.append(f"末行 {len(last_line)} 字符且无正常结尾标记，疑似截断")

        # 信号 2：未闭合的 markdown 代码块
        fence_count = text.count("```")
        if fence_count % 2 != 0:
            signals.append(f"Markdown 代码块未闭合（{fence_count} 个 ``` 标记）")

        # 信号 3：末尾是逗号或冒号（JSON/列表截断）
        if last_line.endswith(",") or last_line.endswith("："):
            signals.append(f"末行以 '{last_line[-1]}' 结尾，疑似列表/JSON 截断")

        return signals
