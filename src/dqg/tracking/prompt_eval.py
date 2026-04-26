"""Prompt-level A/B regression for Q05/Q06.

Reads prompt_versions/*.md under a regression case directory, executes each
version through an injectable executor or offline prompt_outputs/*.json, computes
metrics from PHASE_METRICS, and outputs a Markdown comparison table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from dqg.json_utils import load_json, load_json_strict
from dqg.quality.eval_baseline import PHASE_METRICS, _compute_single_metric

if TYPE_CHECKING:
    from pathlib import Path


class PromptEvalExecutor(Protocol):
    """Callable that executes one prompt version and returns structured output."""

    def __call__(
        self,
        version_name: str,
        prompt: str,
        fixed_input: dict[str, Any],
        meta: dict[str, Any],
    ) -> dict[str, Any]: ...


def _load_case(case_dir: Path) -> dict[str, Any]:
    return load_json_strict(case_dir / "case.json")


def _load_input(case_dir: Path, phase: str) -> dict[str, Any]:
    """Load the fixed input JSON for the case."""
    input_dir = case_dir / "input"
    for path in sorted(input_dir.glob("*.json")):
        return load_json_strict(path)
    raise FileNotFoundError(f"No input JSON found in {input_dir}")


def _discover_prompt_versions(case_dir: Path) -> list[tuple[str, str]]:
    """Return sorted list of (version_name, content) from prompt_versions/."""
    versions_dir = case_dir / "prompt_versions"
    if not versions_dir.exists():
        return []
    results = []
    for path in sorted(versions_dir.glob("*.md")):
        results.append((path.stem, path.read_text(encoding="utf-8")))
    return results


def _load_prompt_manifest(case_dir: Path, version_name: str) -> dict[str, Any]:
    manifest_path = case_dir / "prompt_versions" / f"{version_name}.manifest.json"
    data = load_json(manifest_path)
    return data if isinstance(data, dict) else {}


def _load_prompt_output(case_dir: Path, version_name: str) -> dict[str, Any] | None:
    output_path = case_dir / "prompt_outputs" / f"{version_name}.json"
    data = load_json(output_path)
    return data if isinstance(data, dict) else None


def _execute_prompt_version(
    *,
    case_dir: Path,
    version_name: str,
    prompt: str,
    fixed_input: dict[str, Any],
    meta: dict[str, Any],
    executor: PromptEvalExecutor | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if executor is not None:
        return executor(version_name, prompt, fixed_input, meta), {"source": "executor"}

    offline_output = _load_prompt_output(case_dir, version_name)
    if offline_output is not None:
        return offline_output, {"source": "prompt_outputs"}

    return fixed_input, {"source": "fixed_input_fallback"}


def run_prompt_eval_case(case_dir: Path, executor: PromptEvalExecutor | None = None) -> dict[str, Any]:
    """Compute metrics for each prompt version in a case.

    Returns a dict with case metadata, metric definitions, and per-version scores.
    Each prompt version is executed independently via executor or offline output.
    """
    meta = _load_case(case_dir)
    phase = meta["phase"]
    metric_defs = PHASE_METRICS.get(phase, [])
    if not metric_defs:
        raise ValueError(f"No PHASE_METRICS defined for phase {phase}")

    fixed_input = _load_input(case_dir, phase)
    versions = _discover_prompt_versions(case_dir)
    if not versions:
        raise FileNotFoundError(f"No prompt versions found in {case_dir / 'prompt_versions'}")

    metric_ids = [m["id"] for m in metric_defs]
    metric_names = {m["id"]: m["name"] for m in metric_defs}

    rows: list[dict[str, Any]] = []
    for version_name, content in versions:
        manifest = _load_prompt_manifest(case_dir, version_name)
        data, execution = _execute_prompt_version(
            case_dir=case_dir,
            version_name=version_name,
            prompt=content,
            fixed_input=fixed_input,
            meta=meta,
            executor=executor,
        )
        scores: dict[str, float | None] = {}
        for mdef in metric_defs:
            scores[mdef["id"]] = _compute_single_metric(mdef, data)
        rows.append(
            {
                "version": version_name,
                "prompt_hash": manifest.get("prompt_hash", ""),
                "assembly_order": manifest.get("assembly_order", []),
                "section_hashes": manifest.get("section_hashes", {}),
                "execution": execution,
                "scores": scores,
            }
        )

    return {
        "case_id": meta["case_id"],
        "phase": phase,
        "metric_ids": metric_ids,
        "metric_names": metric_names,
        "rows": rows,
    }


def compute_prompt_metrics(case_dir: Path) -> dict[str, Any]:
    """Backward-compatible prompt metric computation entry point."""
    return run_prompt_eval_case(case_dir)


def format_comparison_table(result: dict[str, Any]) -> str:
    """Format the prompt comparison result as a Markdown table."""
    metric_ids = result["metric_ids"]
    metric_names = result["metric_names"]

    header_cells = ["prompt_version", "prompt_hash", "sections", "execution"] + [
        metric_names.get(mid, mid) for mid in metric_ids
    ]
    header = "| " + " | ".join(header_cells) + " |"
    sep = "| " + " | ".join(["---"] + ["---:"] * (len(header_cells) - 1)) + " |"

    lines = [
        f"# Prompt Comparison: {result['case_id']} ({result['phase']})",
        "",
        header,
        sep,
    ]
    for row in result["rows"]:
        sections = ",".join(row.get("assembly_order") or [])
        execution = row.get("execution") or {}
        cells = [
            row["version"],
            row.get("prompt_hash", "")[:12] or "N/A",
            sections or "N/A",
            execution.get("source", "N/A"),
        ]
        for mid in metric_ids:
            val = row["scores"].get(mid)
            if val is None:
                cells.append("N/A")
            elif isinstance(val, float) and ("rate" in mid or "ratio" in mid):
                cells.append(f"{val:.2%}")
            else:
                cells.append(str(round(val, 4) if isinstance(val, float) else val))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


def run_prompt_comparison(case_id: str | None, phase: str | None, cases_root: Path) -> int:
    """Entry point called from regression.py subcommand."""
    prompt_dir = cases_root / "prompt-eval"
    if not prompt_dir.exists():
        print(f"prompt-eval cases directory not found: {prompt_dir}")
        return 1

    candidates = []
    for case_json in sorted(prompt_dir.rglob("case.json")):
        meta = load_json_strict(case_json)
        if meta.get("sample_type") != "prompt-eval":
            continue
        if case_id and meta["case_id"] != case_id:
            continue
        if phase and meta.get("phase") != phase:
            continue
        candidates.append(case_json.parent)

    if not candidates:
        print(f"No matching prompt-eval case found (case_id={case_id}, phase={phase})")
        return 1

    for case_dir in candidates:
        result = compute_prompt_metrics(case_dir)
        table = format_comparison_table(result)
        print(table)

    return 0
