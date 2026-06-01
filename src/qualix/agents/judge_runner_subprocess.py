"""JudgeRunner subprocess wrapper for context isolation.

Invoked as: python -m qualix.agents.judge_runner_subprocess --input <path> --output <path>

Reads a JSON input file, runs JudgeRunner in a fresh process (no Worker reasoning
traces in memory), writes the serialized JudgeResult to the output file.

Input JSON fields:
    report_path     : str  — path to phase_a_report.md
    output_dir      : str  — directory for Judge output artefacts
    model           : str  — primary model identifier
    fallback        : str | null
    rubric          : str
    warning_override: str | null
    rubric_dims     : list[dict] | null  — pre-computed rubric dims (optional)

Output JSON: serialized JudgeResult (see _judge_result_to_dict).

Exit codes: 0 = success, 1 = any exception.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qualix.quality.judge.judge_runner import JudgeResult


def _judge_result_to_dict(result: JudgeResult) -> dict[str, Any]:
    """Explicit serializer — avoids dataclasses.asdict() which drops _schema_version."""
    return {
        "overall_score": result.overall_score,
        "verdict": result.verdict,
        "dimensions": result.dimensions,
        "issues": result.issues,
        "raw_output": result.raw_output,
        "health": result.health,
        "model": result.model,
        "duration": result.duration,
        "token_usage": result.token_usage,
        "failing_dimensions": result.failing_dimensions,
        "schema_version": result._schema_version,  # explicitly included
    }


def run_subprocess(data: dict[str, Any]) -> dict[str, Any]:
    """Execute JudgeRunner and return serialized result dict.

    Replicates the setup logic from _run_single_judge:
    - Infers project_id / phase_id from report_path
    - Calls _get_dynamic_dim_generator to produce rubric_dims (unless pre-supplied)
    - Delegates to JudgeRunner.run()
    """
    from pathlib import Path

    from qualix.agents.judge_vote import _get_dynamic_dim_generator
    from qualix.agents.pipeline_io import infer_phase_project_ids
    from qualix.quality.judge_runner import JudgeRunner

    report_path: str = data["report_path"]
    output_dir: str = data["output_dir"]
    model: str = data["model"]
    fallback: str | None = data.get("fallback")
    rubric: str = data.get("rubric", "")
    warning_override: str | None = data.get("warning_override")
    rubric_dims: list[dict[str, Any]] | None = data.get("rubric_dims")

    # Replicate dynamic-dim setup from _run_single_judge (only if not pre-supplied)
    if rubric_dims is None:
        phase_id, project_id = infer_phase_project_ids(report_path)
        gen = _get_dynamic_dim_generator(phase_id)
        if gen and project_id:
            rubric_dims = gen(Path(output_dir), project_id, phase_id)

    runner = JudgeRunner(rubric_dims=rubric_dims)
    result = runner.run(
        phase="",
        report_path=report_path,
        output_dir=output_dir,
        model=model,
        fallback=fallback,
        rubric=rubric,
        warning_override=warning_override,
    )

    return _judge_result_to_dict(result)


if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Run JudgeRunner in an isolated subprocess for context isolation."
    )
    parser.add_argument("--input", required=True, help="Path to JSON input file")
    parser.add_argument("--output", required=True, help="Path to write JSON output file")
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        result_dict = run_subprocess(data)
        Path(args.output).write_text(
            json.dumps(result_dict, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        sys.exit(0)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
