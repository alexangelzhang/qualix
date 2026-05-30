"""Adaptive Loop 健康监控：多维度检测死循环和停滞.

借鉴 DeepCode LoopDetector 思路，适配 Qualix Judge→Worker→Judge 语义循环。
检测维度：
1. Score stagnation — 连续 N 轮 score delta < 阈值
2. Issue repetition — Critique/Judge 连续报出相同 issue
3. Infra failure streak — 连续 N 轮 Judge 基础设施失败
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)


@dataclass
class HealthCheckResult:
    """健康检查结果."""

    should_stop: bool = False
    status: str = "ok"  # ok / score_stagnation / issue_repetition / infra_failure / output_fingerprint_stagnation / rejection_signature_stagnation
    message: str = ""


class LoopHealthMonitor:
    """Adaptive loop 健康监控器.

    在每轮 iteration 结束后调用 check()，返回是否应该早停。

    Args:
        score_delta_threshold: 连续 N 轮 score 变化小于此值视为停滞
        stagnation_rounds: 连续多少轮停滞触发早停
        issue_overlap_ratio: issue code 重叠比例超过此值视为重复
        max_infra_failures: 连续多少轮 infra failure 触发早停
    """

    def __init__(
        self,
        score_delta_threshold: float = 0.2,
        stagnation_rounds: int = 2,
        issue_overlap_ratio: float = 0.8,
        max_infra_failures: int = 2,
    ) -> None:
        self._score_delta_threshold = score_delta_threshold
        self._stagnation_rounds = stagnation_rounds
        self._issue_overlap_ratio = issue_overlap_ratio
        self._max_infra_failures = max_infra_failures

        self._scores: list[float] = []
        self._issue_sets: list[set[str]] = []
        self._infra_failures: int = 0
        self._worker_output_hashes: list[str] = []
        self._judge_rejection_sigs: list[str] = []

    def record_iteration(
        self,
        avg_score: float,
        issues: list[dict[str, Any]] | None = None,
        judge_health: str = "HEALTHY",
        worker_output_hash: str | None = None,
        judge_rejection_sig: str | None = None,
    ) -> None:
        """记录一轮迭代的结果."""
        self._scores.append(avg_score)

        # 提取 issue code 集合
        issue_codes: set[str] = set()
        if issues:
            for issue in issues:
                code = issue.get("code") or issue.get("dimension") or issue.get("issue", "")
                if code:
                    issue_codes.add(str(code))
        self._issue_sets.append(issue_codes)

        # Infra failure 计数
        if judge_health == "INFRA_FAILURE":
            self._infra_failures += 1
        else:
            self._infra_failures = 0

        self._worker_output_hashes.append(worker_output_hash or "")
        self._judge_rejection_sigs.append(judge_rejection_sig or "")

    def check(self) -> HealthCheckResult:
        """检查当前循环健康状态."""
        # 1. Infra failure streak
        if self._infra_failures >= self._max_infra_failures:
            msg = f"连续 {self._infra_failures} 轮 Judge 基础设施失败，停止循环"
            log.warning("LoopHealthMonitor: %s", msg)
            return HealthCheckResult(should_stop=True, status="infra_failure", message=msg)

        # 2. Score stagnation
        if len(self._scores) >= self._stagnation_rounds + 1:
            recent = self._scores[-self._stagnation_rounds :]
            prev = self._scores[-(self._stagnation_rounds + 1)]
            all_stagnant = all(abs(s - prev) < self._score_delta_threshold for s in recent)
            if all_stagnant:
                msg = (
                    f"连续 {self._stagnation_rounds} 轮 score 变化 < {self._score_delta_threshold}"
                    f"（{' → '.join(f'{s:.1f}' for s in self._scores)}），Worker 修正无效"
                )
                log.warning("LoopHealthMonitor: %s", msg)
                return HealthCheckResult(should_stop=True, status="score_stagnation", message=msg)

        # 3. Issue repetition
        if len(self._issue_sets) >= 2:
            prev_issues = self._issue_sets[-2]
            curr_issues = self._issue_sets[-1]
            if prev_issues and curr_issues:
                overlap = prev_issues & curr_issues
                overlap_ratio = len(overlap) / max(len(prev_issues), len(curr_issues))
                if overlap_ratio >= self._issue_overlap_ratio:
                    msg = (
                        f"Judge 连续 2 轮报出相同 issue（重叠 {overlap_ratio:.0%}）： {', '.join(sorted(overlap)[:3])}"
                    )
                    log.warning("LoopHealthMonitor: %s", msg)
                    return HealthCheckResult(should_stop=True, status="issue_repetition", message=msg)

        # 4. Worker 产出指纹停滞
        if len(self._worker_output_hashes) >= 2:
            last = self._worker_output_hashes[-1]
            if last and last == self._worker_output_hashes[-2]:
                msg = "Worker 连续 2 轮产出完全相同（指纹不变），修正无效"
                log.warning("LoopHealthMonitor: %s", msg)
                return HealthCheckResult(
                    should_stop=True,
                    status="output_fingerprint_stagnation",
                    message=msg,
                )

        # 5. Judge 驳回签名停滞
        if len(self._judge_rejection_sigs) >= 2:
            last = self._judge_rejection_sigs[-1]
            if last and last == self._judge_rejection_sigs[-2]:
                msg = "Judge 连续 2 轮驳回相同 issue（签名不变），Worker 未解决根本问题"
                log.warning("LoopHealthMonitor: %s", msg)
                return HealthCheckResult(
                    should_stop=True,
                    status="rejection_signature_stagnation",
                    message=msg,
                )

        return HealthCheckResult()

    def get_summary(self) -> dict[str, Any]:
        """获取监控摘要，写入 _adaptive_summary.json."""
        return {
            "scores": [round(s, 2) for s in self._scores],
            "issue_overlap_history": [
                round(
                    len(self._issue_sets[i] & self._issue_sets[i - 1]) / max(len(self._issue_sets[i - 1]), 1),
                    2,
                )
                for i in range(1, len(self._issue_sets))
            ],
            "infra_failure_streak": self._infra_failures,
            "total_iterations": len(self._scores),
            "output_fingerprint_history": [h[:8] if h else "" for h in self._worker_output_hashes],
            "rejection_sig_history": [s[:8] if s else "" for s in self._judge_rejection_sigs],
        }
