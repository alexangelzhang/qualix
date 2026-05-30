"""quality package — facade for backward-compatible imports.

After the sub-package split, old import paths like
``from qualix.quality.judge_runner import JudgeRunner``
still work via lazy sys.modules aliases.
"""

from __future__ import annotations

from qualix.compat import install_module_aliases

_ALIASES: dict[str, str] = {
    # judge/
    "qualix.quality._rubric_data": "qualix.quality.judge._rubric_data",
    "qualix.quality.critique": "qualix.quality.judge.critique",
    "qualix.quality.critique_feedback": "qualix.quality.judge.critique_feedback",
    "qualix.quality.dynamic_rubric": "qualix.quality.judge.dynamic_rubric",
    "qualix.quality.judge_rubrics": "qualix.quality.judge.judge_rubrics",
    "qualix.quality.judge_runner": "qualix.quality.judge.judge_runner",
    "qualix.quality.rationalization_guard": "qualix.quality.judge.rationalization_guard",
    "qualix.quality.review_chain": "qualix.quality.judge.review_chain",
    "qualix.quality.score_calibration": "qualix.quality.judge.score_calibration",
    # guardrail/
    "qualix.quality.fabrication_detector": "qualix.quality.guardrail.fabrication_detector",
    "qualix.quality.guardrail_impl": "qualix.quality.guardrail.guardrail_impl",
    "qualix.quality.output_completeness": "qualix.quality.guardrail.output_completeness",
    "qualix.quality.semantic_guardrail": "qualix.quality.guardrail.semantic_guardrail",
    # rules/
    "qualix.quality.rule_checks": "qualix.quality.rules.rule_checks",
    "qualix.quality.rule_checks_bc": "qualix.quality.rules.rule_checks_bc",
    "qualix.quality.rule_compliance": "qualix.quality.rules.rule_compliance",
    "qualix.quality.rule_definitions": "qualix.quality.rules.rule_definitions",
    # eval/
    "qualix.quality.behavioral_fingerprint": "qualix.quality.eval.behavioral_fingerprint",
    "qualix.quality.eval_baseline": "qualix.quality.eval.eval_baseline",
    "qualix.quality.eval_holdout": "qualix.quality.eval.eval_holdout",
    "qualix.quality.evaluation_protocols": "qualix.quality.eval.evaluation_protocols",
    "qualix.quality.golden_sample": "qualix.quality.eval.golden_sample",
    # checks/
    "qualix.quality.auto_checks": "qualix.quality.checks.auto_checks",
    "qualix.quality.blast_radius": "qualix.quality.checks.blast_radius",
    "qualix.quality.business_mutations": "qualix.quality.checks.business_mutations",
    "qualix.quality.checkpoint_validator": "qualix.quality.checks.checkpoint_validator",
    "qualix.quality.compile_check": "qualix.quality.checks.compile_check",
    "qualix.quality.coverage_gate": "qualix.quality.checks.coverage_gate",
    "qualix.quality.coverage_matrix": "qualix.quality.checks.coverage_matrix",
    "qualix.quality.cross_phase_check": "qualix.quality.checks.cross_phase_check",
    "qualix.quality.demand_trace": "qualix.quality.checks.demand_trace",
    "qualix.quality.finalize_checks": "qualix.quality.checks.finalize_checks",
    "qualix.quality.report_quality_checks": "qualix.quality.checks.report_quality_checks",
    "qualix.quality.requirement_graph": "qualix.quality.checks.requirement_graph",
    "qualix.quality.requirement_smell": "qualix.quality.checks.requirement_smell",
    "qualix.quality.test_execution_gate": "qualix.quality.checks.test_execution_gate",
    # regression/
    "qualix.quality.gene_store": "qualix.quality.regression.gene_store",
    "qualix.quality.quality_tracker": "qualix.quality.regression.quality_tracker",
    "qualix.quality.root_cause_tuner": "qualix.quality.regression.root_cause_tuner",
    "qualix.quality.trajectory": "qualix.quality.regression.trajectory",
    "qualix.quality.verification_bundle": "qualix.quality.regression.verification_bundle",
}

install_module_aliases(_ALIASES, __name__)
