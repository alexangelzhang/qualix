"""quality package — facade for backward-compatible imports.

After the sub-package split, old import paths like
``from dqg.quality.judge_runner import JudgeRunner``
still work via lazy sys.modules aliases.
"""

from __future__ import annotations

from dqg.compat import install_module_aliases

_ALIASES: dict[str, str] = {
    # judge/
    "dqg.quality._rubric_data": "dqg.quality.judge._rubric_data",
    "dqg.quality.critique": "dqg.quality.judge.critique",
    "dqg.quality.critique_feedback": "dqg.quality.judge.critique_feedback",
    "dqg.quality.dynamic_rubric": "dqg.quality.judge.dynamic_rubric",
    "dqg.quality.judge_rubrics": "dqg.quality.judge.judge_rubrics",
    "dqg.quality.judge_runner": "dqg.quality.judge.judge_runner",
    "dqg.quality.rationalization_guard": "dqg.quality.judge.rationalization_guard",
    "dqg.quality.review_chain": "dqg.quality.judge.review_chain",
    "dqg.quality.score_calibration": "dqg.quality.judge.score_calibration",
    # guardrail/
    "dqg.quality.fabrication_detector": "dqg.quality.guardrail.fabrication_detector",
    "dqg.quality.guardrail_impl": "dqg.quality.guardrail.guardrail_impl",
    "dqg.quality.output_completeness": "dqg.quality.guardrail.output_completeness",
    "dqg.quality.semantic_guardrail": "dqg.quality.guardrail.semantic_guardrail",
    # rules/
    "dqg.quality.rule_checks": "dqg.quality.rules.rule_checks",
    "dqg.quality.rule_checks_bc": "dqg.quality.rules.rule_checks_bc",
    "dqg.quality.rule_compliance": "dqg.quality.rules.rule_compliance",
    "dqg.quality.rule_definitions": "dqg.quality.rules.rule_definitions",
    # eval/
    "dqg.quality.behavioral_fingerprint": "dqg.quality.eval.behavioral_fingerprint",
    "dqg.quality.eval_baseline": "dqg.quality.eval.eval_baseline",
    "dqg.quality.eval_holdout": "dqg.quality.eval.eval_holdout",
    "dqg.quality.evaluation_protocols": "dqg.quality.eval.evaluation_protocols",
    "dqg.quality.golden_sample": "dqg.quality.eval.golden_sample",
    # checks/
    "dqg.quality.auto_checks": "dqg.quality.checks.auto_checks",
    "dqg.quality.blast_radius": "dqg.quality.checks.blast_radius",
    "dqg.quality.business_mutations": "dqg.quality.checks.business_mutations",
    "dqg.quality.checkpoint_validator": "dqg.quality.checks.checkpoint_validator",
    "dqg.quality.compile_check": "dqg.quality.checks.compile_check",
    "dqg.quality.coverage_gate": "dqg.quality.checks.coverage_gate",
    "dqg.quality.coverage_matrix": "dqg.quality.checks.coverage_matrix",
    "dqg.quality.cross_phase_check": "dqg.quality.checks.cross_phase_check",
    "dqg.quality.demand_trace": "dqg.quality.checks.demand_trace",
    "dqg.quality.finalize_checks": "dqg.quality.checks.finalize_checks",
    "dqg.quality.report_quality_checks": "dqg.quality.checks.report_quality_checks",
    "dqg.quality.requirement_graph": "dqg.quality.checks.requirement_graph",
    "dqg.quality.requirement_smell": "dqg.quality.checks.requirement_smell",
    "dqg.quality.test_execution_gate": "dqg.quality.checks.test_execution_gate",
    # regression/
    "dqg.quality.gene_store": "dqg.quality.regression.gene_store",
    "dqg.quality.quality_tracker": "dqg.quality.regression.quality_tracker",
    "dqg.quality.root_cause_tuner": "dqg.quality.regression.root_cause_tuner",
    "dqg.quality.trajectory": "dqg.quality.regression.trajectory",
    "dqg.quality.verification_bundle": "dqg.quality.regression.verification_bundle",
}

install_module_aliases(_ALIASES, __name__)
