"""跨模型 Judge 一致性评估.

同一 Phase 报告用多个 LLM 模型分别打分，对比：
- 分数分布（range / stddev）
- PASS/FAIL 是否一致
- 哪些评审维度存在显著分歧（score spread > 1.0）→ 这些维度的规则可能模型相关

用法：
    from qualix.tracking.multi_model_judge import run_multi_model_judge
    report = run_multi_model_judge(output_dir, "my-project", "Q03",
                                   models=["deepseek-chat", "claude-opus-4-6"])
    print(report.consistency_verdict, report.fragile_dimensions)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qualix.log import get_logger

log = get_logger(__name__)

# 维度分歧阈值：超过此 score spread 认为该维度是 fragile rule
FRAGILE_DIM_THRESHOLD = 1.0
# 整体分数 range 判断一致性的阈值
CONSISTENT_RANGE = 0.5
MARGINAL_RANGE = 1.0


@dataclass
class ModelJudgeRun:
    """单模型 Judge 结果."""

    model: str
    overall_score: float
    verdict: str
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    health: str = "HEALTHY"
    duration: float = 0.0
    error: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict in {"PASS", "PASS_WITH_CONCERNS"}


@dataclass
class MultiJudgeReport:
    """跨模型 Judge 一致性报告."""

    phase_id: str
    project_id: str
    report_path: str
    models_run: list[str] = field(default_factory=list)
    results: dict[str, ModelJudgeRun] = field(default_factory=dict)

    # 统计
    score_range: float = 0.0
    score_stddev: float = 0.0
    verdict_agreement: bool = True
    fragile_dimensions: list[str] = field(default_factory=list)
    consistency_verdict: str = "CONSISTENT"  # CONSISTENT | MARGINAL | DIVERGED

    def summary_lines(self) -> list[str]:
        """返回人类可读的摘要行."""
        lines = [
            f"Phase {self.phase_id} | {self.project_id}",
            f"Models: {', '.join(self.models_run)}",
            f"Consistency: {self.consistency_verdict}  (range={self.score_range:.2f}, stddev={self.score_stddev:.2f})",
            f"Verdict agreement: {'✅ 一致' if self.verdict_agreement else '❌ 分歧'}",
        ]
        for model, run in self.results.items():
            status = "✅" if run.health == "HEALTHY" else "❌"
            lines.append(f"  {status} {model}: {run.overall_score:.1f} ({run.verdict})")
        if self.fragile_dimensions:
            lines.append(f"⚠️  Fragile dimensions (模型间分歧>1.0): {self.fragile_dimensions}")
        return lines


def run_multi_model_judge(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    models: list[str],
    rubric: str = "",
) -> MultiJudgeReport:
    """对同一 Phase 报告用多个模型各运行一次 Judge.

    Args:
        output_dir: 项目 output 根目录
        project_id: 项目 ID
        phase_id: Phase ID（需要有已完成的报告）
        models: 要测试的模型列表，如 ["deepseek-chat", "claude-opus-4-6"]
        rubric: 自定义 rubric（留空则走默认 compose_rubric）

    Returns:
        MultiJudgeReport：包含每个模型的 Judge 结果和一致性分析
    """
    from qualix.constants import REPORT_MAP
    from qualix.core.state_machine import PHASE_DEFS
    from qualix.core.state_machine import phase_dir as _phase_dir
    from qualix.quality.judge.judge_rubrics import compose_rubric
    from qualix.quality.judge.judge_runner import JudgeRunner

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        raise ValueError(f"Unknown phase: {phase_id}")

    pd = _phase_dir(output_dir, project_id, phase_def)
    report_filename = REPORT_MAP.get(phase_id, "")
    if not report_filename:
        raise ValueError(f"No report file configured for phase {phase_id}")

    report_path = pd / report_filename
    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    if not rubric:
        rubric = compose_rubric(phase_id)

    report = MultiJudgeReport(
        phase_id=phase_id,
        project_id=project_id,
        report_path=str(report_path),
        models_run=list(models),
    )

    runner = JudgeRunner()
    for model in models:
        log.info("multi_model_judge: running %s on %s/%s", model, project_id, phase_id)
        try:
            result = runner.run(phase_id, str(report_path), str(output_dir), model, rubric=rubric)
            report.results[model] = ModelJudgeRun(
                model=model,
                overall_score=result.overall_score,
                verdict=result.verdict,
                dimensions=result.dimensions,
                health=result.health,
                duration=result.duration,
                error="" if result.health == "HEALTHY" else result.raw_output[:300],
            )
        except Exception as e:
            log.error("multi_model_judge: model %s failed: %s", model, e)
            report.results[model] = ModelJudgeRun(
                model=model,
                overall_score=0.0,
                verdict="FAIL",
                health="INFRA_FAILURE",
                error=str(e)[:300],
            )

    _compute_stats(report)
    return report


def _compute_stats(report: MultiJudgeReport) -> None:
    """原地计算统计摘要."""
    healthy = [r for r in report.results.values() if r.health == "HEALTHY"]
    if len(healthy) < 2:
        return

    scores = [r.overall_score for r in healthy]
    report.score_range = max(scores) - min(scores)
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    report.score_stddev = math.sqrt(variance)

    _PASS_LABELS = {"PASS", "PASS_WITH_CONCERNS"}
    verdicts_bool = [r.verdict in _PASS_LABELS for r in healthy]
    report.verdict_agreement = len(set(verdicts_bool)) == 1

    # 维度级分歧
    all_dim_ids: set[str] = set()
    for run in healthy:
        all_dim_ids.update(d.get("id", "") for d in run.dimensions)

    for dim_id in all_dim_ids:
        if not dim_id:
            continue
        dim_scores = [d.get("score", 0) for run in healthy for d in run.dimensions if d.get("id") == dim_id]
        if len(dim_scores) >= 2 and (max(dim_scores) - min(dim_scores)) > FRAGILE_DIM_THRESHOLD:
            report.fragile_dimensions.append(dim_id)

    if report.score_range <= CONSISTENT_RANGE and report.verdict_agreement:
        report.consistency_verdict = "CONSISTENT"
    elif report.score_range <= MARGINAL_RANGE:
        report.consistency_verdict = "MARGINAL"
    else:
        report.consistency_verdict = "DIVERGED"
