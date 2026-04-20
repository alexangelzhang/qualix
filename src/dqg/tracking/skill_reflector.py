"""Reflect→Write→Verify loop for automatic skill evolution.

Triggered when adaptive loop exhausts all iterations with FAIL.

Root cause taxonomy:
- SKILL_RULE: Worker repeatedly violates a rule that should be in the skill file.
  Write-back: append to anti-rationalization table or red-line rules in SKILL.md.
- CONTEXT: Worker lacks necessary context (missing code, upstream data, domain knowledge).
  Write-back: append to _context_hints.md in phase _internal/ dir.
- SCHEMA: Worker produces structurally wrong output (missing fields, wrong format).
  Write-back: append to _schema_hints.md in phase _internal/ dir.
- UNKNOWN: Cannot classify. Write suggestion file for human review.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.constants import CASES_DIR, PHASE_DIR_MAP, SKILL_FILE_MAP
from dqg.json_utils import save_json
from dqg.log import get_logger
from dqg.tracking.skill_evolution import HIGH_CONFIDENCE_THRESHOLD

log = get_logger(__name__)

ROOT_CAUSE_CLASSIFY_PROMPT = """你是质量分析专家。以下是一个 AI Agent 在多轮迭代后仍然失败的 Judge 评审问题列表：

{issues}

请分析这些问题的根本原因，从以下三类中选择最匹配的一类：

- SKILL_RULE：Agent 反复违反某条应该写入 Skill 文件的规则（如"必须包含X"、"禁止做Y"）
- CONTEXT：Agent 缺少必要的上下文信息（如缺少代码仓库、缺少上游数据、缺少领域知识）
- SCHEMA：Agent 产出的结构不符合要求（如缺少必填字段、格式错误、JSON 结构不对）

同时提取：
1. 核心失败模式（一句话）
2. 针对该根因的具体修复建议（一句话）

只输出 JSON，格式：
{{"root_cause": "SKILL_RULE|CONTEXT|SCHEMA|UNKNOWN", "pattern": "...", "fix": "..."}}"""


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
        """Analyze judge results, classify root cause via LLM, extract failure patterns."""
        all_issues = []
        for jr in judge_results:
            for issue in jr.get("issues", []):
                desc = issue.get("description", "")
                if desc:
                    all_issues.append(desc)

        if not all_issues:
            return ReflectResult(actionable=False)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_issues = []
        for issue in all_issues:
            key = issue[:60].lower()
            if key not in seen:
                seen.add(key)
                unique_issues.append(issue)

        root_cause, pattern, fix = self._classify_root_cause(unique_issues)

        if root_cause == "UNKNOWN":
            return ReflectResult(actionable=False, failure_patterns=unique_issues)

        return ReflectResult(
            actionable=True,
            root_cause=root_cause,
            failure_patterns=unique_issues,
            suggested_changes=[fix] if fix else [f"Address: {unique_issues[0][:100]}"],
        )

    def _classify_root_cause(self, issues: list[str]) -> tuple[str, str, str]:
        """Use LLM to classify root cause. Returns (root_cause, pattern, fix)."""
        from dqg.agents.llm_backends import LLMConfig, create_backend
        from dqg.constants import DEFAULT_RATIONALIZATION_CONFIRM_MODEL

        issues_text = "\n".join(f"- {i}" for i in issues[:10])
        prompt = ROOT_CAUSE_CLASSIFY_PROMPT.format(issues=issues_text)

        try:
            model = DEFAULT_RATIONALIZATION_CONFIRM_MODEL
            api_key = LLMConfig(primary=model)._resolve_api_key(model)
            backend = create_backend(model, api_key)
            content, _ = backend.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            # Extract JSON from response
            import re
            m = re.search(r'\{.*\}', content, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return (
                    data.get("root_cause", "UNKNOWN"),
                    data.get("pattern", ""),
                    data.get("fix", ""),
                )
        except Exception as e:
            log.warning("Root cause classification failed: %s, falling back to heuristic", e)

        # Heuristic fallback: keyword-based classification
        combined = " ".join(issues).lower()
        if any(k in combined for k in ("缺少", "没有提供", "上下文", "代码仓库", "缺乏")):
            return "CONTEXT", issues[0][:80], "补充上下文信息"
        if any(k in combined for k in ("格式", "字段", "结构", "json", "schema", "缺失字段")):
            return "SCHEMA", issues[0][:80], "修正输出结构"
        if len(issues) >= 2:
            return "SKILL_RULE", issues[0][:80], f"Add rule: {issues[0][:80]}"
        return "UNKNOWN", "", ""

    def write(self, reflect_result: ReflectResult, support_count: int) -> WriteResult:
        """Apply changes based on root_cause type and confidence level.

        SKILL_RULE + high confidence → append to SKILL.md (auto-apply)
        CONTEXT → append to _context_hints.md
        SCHEMA → append to _schema_hints.md
        Others → HUMAN_REVIEW suggestion file
        """
        root_cause = reflect_result.root_cause

        if root_cause == "CONTEXT":
            path = self._write_context_hints(reflect_result)
            return WriteResult(mode="AUTO_APPLY", path=path, changes=reflect_result.suggested_changes)

        if root_cause == "SCHEMA":
            path = self._write_schema_hints(reflect_result)
            return WriteResult(mode="AUTO_APPLY", path=path, changes=reflect_result.suggested_changes)

        if root_cause == "SKILL_RULE":
            if support_count < HIGH_CONFIDENCE_THRESHOLD:
                suggestion_path = self._write_suggestion_file(reflect_result)
                return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

            skill_path = SKILL_FILE_MAP.get(self.phase, "")
            if not skill_path:
                return WriteResult(mode="HUMAN_REVIEW", path="")

            # v1: auto-apply deferred until holdout replay is ready
            suggestion_path = self._write_suggestion_file(reflect_result)
            return WriteResult(
                mode="HUMAN_REVIEW",
                path=suggestion_path,
                changes=reflect_result.suggested_changes,
                target_files=[skill_path],
            )

        suggestion_path = self._write_suggestion_file(reflect_result)
        return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

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

        action = "AUTO_MERGED" if write_result.mode == "AUTO_APPLY" else "HUMAN_REVIEW"
        outcome = EvolutionOutcome(
            action=action,
            reason=f"root_cause={reflect_result.root_cause}, support={support_count}",
            suggestion_path=write_result.path,
            changes=write_result.changes,
        )

        # 写入完整推理链，形成可审计的 Markdown 记录
        self._write_evolution_trace(reflect_result, case_id, support_count, write_result, outcome)

        return outcome

    def _write_evolution_trace(
        self,
        reflect_result: ReflectResult,
        case_id: str,
        support_count: int,
        write_result: WriteResult,
        outcome: EvolutionOutcome,
    ) -> None:
        """写入完整推理链到 _skill_evolution_trace.md，可纳入 git 追踪."""
        dir_suffix = PHASE_DIR_MAP.get(self.phase, self.phase)
        trace_dir = Path("output") / self.project_id / dir_suffix / "_internal"
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = trace_dir / "_skill_evolution_trace.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"\n## [{timestamp}] Skill Evolution Trace — Phase {self.phase}",
            "",
            "### 触发条件",
            f"- 项目: {self.project_id}",
            f"- Adaptive Loop 全部迭代 FAIL，Judge 健康（SEMANTIC_FAIL）",
            "",
            "### 根因分类（LLM 推理）",
            f"- **Root Cause**: `{reflect_result.root_cause}`",
            f"- **失败模式**: {reflect_result.suggested_changes[0] if reflect_result.suggested_changes else '—'}",
            "",
            "### 失败证据（Judge Issues）",
        ]
        for i, p in enumerate(reflect_result.failure_patterns[:5], 1):
            lines.append(f"{i}. {p}")
        if len(reflect_result.failure_patterns) > 5:
            lines.append(f"... 共 {len(reflect_result.failure_patterns)} 条")

        lines += [
            "",
            "### Bug Case 写入",
            f"- Case ID: `{case_id}`",
            f"- 同指纹支撑数: {support_count} (阈值: {HIGH_CONFIDENCE_THRESHOLD})",
            "",
            "### 写回决策",
            f"- 模式: `{write_result.mode}`",
            f"- 目标文件: {', '.join(write_result.target_files) if write_result.target_files else write_result.path or '—'}",
        ]
        if write_result.changes:
            lines.append("- 变更内容:")
            for c in write_result.changes:
                lines.append(f"  - {c}")

        lines += [
            "",
            "### 最终结论",
            f"- Action: `{outcome.action}`",
            f"- Reason: {outcome.reason}",
            "",
            "---",
        ]

        with trace_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        log.info("Evolution trace written: %s", trace_path)

    def _write_context_hints(self, reflect_result: ReflectResult) -> str:
        """Append context hints to _context_hints.md in phase _internal/ dir."""
        dir_suffix = PHASE_DIR_MAP.get(self.phase, self.phase)
        hints_dir = Path("output") / self.project_id / dir_suffix / "_internal"
        hints_dir.mkdir(parents=True, exist_ok=True)
        path = hints_dir / "_context_hints.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{timestamp}] Auto-detected context gap\n\n"
        for p in reflect_result.failure_patterns[:3]:
            entry += f"- {p}\n"
        if reflect_result.suggested_changes:
            entry += f"\n**建议**: {reflect_result.suggested_changes[0]}\n"

        with path.open("a", encoding="utf-8") as f:
            f.write(entry)
        log.info("Context hints written: %s", path)
        return str(path)

    def _write_schema_hints(self, reflect_result: ReflectResult) -> str:
        """Append schema hints to _schema_hints.md in phase _internal/ dir."""
        dir_suffix = PHASE_DIR_MAP.get(self.phase, self.phase)
        hints_dir = Path("output") / self.project_id / dir_suffix / "_internal"
        hints_dir.mkdir(parents=True, exist_ok=True)
        path = hints_dir / "_schema_hints.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## [{timestamp}] Auto-detected schema issue\n\n"
        for p in reflect_result.failure_patterns[:3]:
            entry += f"- {p}\n"
        if reflect_result.suggested_changes:
            entry += f"\n**建议**: {reflect_result.suggested_changes[0]}\n"

        with path.open("a", encoding="utf-8") as f:
            f.write(entry)
        log.info("Schema hints written: %s", path)
        return str(path)

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
