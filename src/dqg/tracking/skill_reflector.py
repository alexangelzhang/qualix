"""Reflect→Write→Verify loop for automatic skill evolution.

Triggered when adaptive loop exhausts all iterations with FAIL.
Only SKILL_RULE root cause can be auto-merged (v1).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.constants import CASES_DIR, PHASE_DIR_MAP, SKILL_FILE_MAP
from dqg.json_utils import save_json
from dqg.log import get_logger
from dqg.tracking.skill_evolution import HIGH_CONFIDENCE_THRESHOLD

log = get_logger(__name__)


def compute_case_fingerprint(
    phase: str, error_type: str, root_cause: str, lesson: str,
) -> str:
    """Compute dedupe fingerprint for a failure case."""
    normalized = f"{phase}|{error_type}|{root_cause}|{lesson.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class ReflectResult:
    actionable: bool
    root_cause: str = ""
    failure_patterns: list[str] = field(default_factory=list)
    suggested_changes: list[str] = field(default_factory=list)


@dataclass
class WriteResult:
    mode: str  # AUTO_APPLY | HUMAN_REVIEW
    path: str = ""
    changes: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)


@dataclass
class EvolutionOutcome:
    action: str  # SKIP | HUMAN_REVIEW | AUTO_MERGED | REVERTED
    reason: str = ""
    suggestion_path: str = ""
    changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "suggestion_path": self.suggestion_path,
            "changes": self.changes,
        }


class SkillReflector:
    """Analyzes adaptive loop failures and auto-evolves skill rules."""

    def __init__(self, phase: str, project_id: str):
        self.phase = phase
        self.project_id = project_id

    def reflect(self, judge_results: list[dict]) -> ReflectResult:
        """Analyze judge results, extract repeated failure patterns."""
        all_issues = []
        for jr in judge_results:
            for issue in jr.get("issues", []):
                all_issues.append(issue.get("description", ""))

        if not all_issues:
            return ReflectResult(actionable=False)

        words: Counter = Counter()
        for desc in all_issues:
            for word in desc.split():
                if len(word) > 3:
                    words[word] += 1

        common = words.most_common(5)
        if common and common[0][1] >= 2:
            return ReflectResult(
                actionable=True,
                root_cause="SKILL_RULE",
                failure_patterns=all_issues,
                suggested_changes=[f"Add rule to address: {all_issues[0][:100]}"],
            )

        return ReflectResult(actionable=False, failure_patterns=all_issues)

    def write(self, reflect_result: ReflectResult, support_count: int) -> WriteResult:
        """Apply changes based on root_cause type and confidence level.

        v1: Only SKILL_RULE with support >= HIGH_CONFIDENCE_THRESHOLD can auto-apply.
        All other types → HUMAN_REVIEW.
        """
        if reflect_result.root_cause != "SKILL_RULE":
            suggestion_path = self._write_suggestion_file(reflect_result)
            return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

        if support_count < HIGH_CONFIDENCE_THRESHOLD:
            suggestion_path = self._write_suggestion_file(reflect_result)
            return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

        skill_path = SKILL_FILE_MAP.get(self.phase, "")
        if not skill_path:
            return WriteResult(mode="HUMAN_REVIEW", path="")

        return WriteResult(
            mode="AUTO_APPLY",
            changes=reflect_result.suggested_changes,
            target_files=[skill_path],
        )

    def snapshot_targets(self, target_files: list[str]) -> dict[str, str]:
        """Save original content of target files for rollback."""
        snapshots = {}
        for fp in target_files:
            p = Path(fp)
            if p.exists():
                snapshots[fp] = p.read_text(encoding="utf-8")
        return snapshots

    def rollback(self, snapshot: dict[str, str]) -> None:
        """Restore files from snapshot."""
        for fp, content in snapshot.items():
            Path(fp).write_text(content, encoding="utf-8")
            log.info("Rolled back: %s", fp)

    def persist_as_bug_case(self, reflect_result: ReflectResult) -> str:
        """Persist failure as bug case in failure-library."""
        case_id = f"AUTO-{self.phase}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        case_dir = Path(CASES_DIR) / f"phase{self.phase}" / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        fingerprint = compute_case_fingerprint(
            self.phase, "FN", reflect_result.root_cause,
            reflect_result.failure_patterns[0] if reflect_result.failure_patterns else "",
        )

        case_data = {
            "case_id": case_id,
            "phase": self.phase,
            "error_type": "FN",
            "root_cause": reflect_result.root_cause,
            "lesson": reflect_result.failure_patterns[0] if reflect_result.failure_patterns else "",
            "fingerprint": fingerprint,
            "source_signature": self.project_id,
            "auto_generated": True,
            "timestamp": datetime.now().isoformat(),
        }
        save_json(case_dir / "case.json", case_data)
        return case_id

    def cluster_and_count_support(self, case_id: str) -> int:
        """Count distinct source signatures for cases with same fingerprint."""
        case_path = Path(CASES_DIR) / f"phase{self.phase}" / case_id / "case.json"
        if not case_path.exists():
            return 1

        current = json.loads(case_path.read_text())
        fingerprint = current.get("fingerprint", "")
        if not fingerprint:
            return 1

        phase_dir = Path(CASES_DIR) / f"phase{self.phase}"
        if not phase_dir.exists():
            return 1

        signatures = set()
        for case_dir in phase_dir.iterdir():
            cf = case_dir / "case.json"
            if not cf.exists():
                continue
            try:
                data = json.loads(cf.read_text())
                if data.get("fingerprint") == fingerprint:
                    sig = data.get("source_signature", "")
                    if sig:
                        signatures.add(sig)
            except (json.JSONDecodeError, OSError):
                continue

        return len(signatures)

    def reflect_and_write(self, judge_results: list[dict]) -> EvolutionOutcome:
        """Full Reflect→Persist→Cluster→Write pipeline."""
        reflect_result = self.reflect(judge_results)
        if not reflect_result.actionable:
            return EvolutionOutcome(action="SKIP", reason="No actionable pattern found")

        case_id = self.persist_as_bug_case(reflect_result)
        support_count = self.cluster_and_count_support(case_id)

        write_result = self.write(reflect_result, support_count)
        if write_result.mode == "HUMAN_REVIEW":
            return EvolutionOutcome(
                action="HUMAN_REVIEW", suggestion_path=write_result.path,
            )

        # v1: auto-apply deferred until holdout replay is ready
        return EvolutionOutcome(
            action="HUMAN_REVIEW",
            reason="v1: auto-apply deferred until holdout replay is ready",
            changes=write_result.changes,
        )

    def _write_suggestion_file(self, reflect_result: ReflectResult) -> str:
        """Write suggestion file for human review."""
        suggestion_dir = Path("output") / self.project_id / PHASE_DIR_MAP.get(self.phase, self.phase)
        suggestion_dir.mkdir(parents=True, exist_ok=True)
        path = suggestion_dir / f"_skill_suggestions_{self.phase}.md"

        content = f"# Skill Evolution Suggestions — Phase {self.phase}\n\n"
        content += f"Root Cause: {reflect_result.root_cause}\n\n"
        content += "## Failure Patterns\n\n"
        for p in reflect_result.failure_patterns:
            content += f"- {p}\n"
        content += "\n## Suggested Changes\n\n"
        for c in reflect_result.suggested_changes:
            content += f"- {c}\n"

        path.write_text(content, encoding="utf-8")
        return str(path)
