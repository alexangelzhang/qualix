"""Prompt Policy Gate finalize handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dqg.json_utils import save_json
from dqg.prompting.policy import discover_prompt_artifacts, validate_prompt_artifact

if TYPE_CHECKING:
    from dqg.runtime.execution_context import ExecutionContext
    from dqg.runtime.result import PhaseResult


def handle_prompt_policy(ctx: ExecutionContext, result: PhaseResult) -> None:
    """Validate prompt manifests and core prompt safety contracts."""
    if ctx.phase_root is None:
        return

    policy_results = [validate_prompt_artifact(path) for path in discover_prompt_artifacts(ctx.phase_root)]
    if not policy_results:
        return

    internal_dir = ctx.internal_dir or (ctx.phase_root / "_internal")
    policy_path = internal_dir / "_prompt_policy.json"
    save_json(policy_path, [item.to_payload() for item in policy_results])
    result.add_artifact("prompt_policy", str(policy_path))

    for policy_result in policy_results:
        for issue in policy_result.issues:
            if issue.severity == "BLOCKED":
                result.add_error(
                    f"BLOCKED: Prompt Policy failed for {policy_result.prompt_path}: {issue.code} — {issue.message}"
                )
