"""Reflect→Write→Verify loop for automatic skill evolution.

Triggered when adaptive loop exhausts all iterations with FAIL.
Root cause taxonomy: SKILL_RULE / CONTEXT / SCHEMA / UNKNOWN.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from qualix.constants import CASES_DIR, PHASE_DIR_MAP, SKILL_AUTO_MERGE_ENABLED, SKILL_FILE_MAP
from qualix.json_utils import load_json, save_json
from qualix.log import get_logger
from qualix.tracking.skill_evolution import HIGH_CONFIDENCE_THRESHOLD

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
    phase: str,
    error_type: str,
    root_cause: str,
    lesson: str,
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
    evidence_warning: str = ""  # 非空表示输入契约质量不足


@dataclass
class WriteResult:
    mode: str  # AUTO_APPLY | HUMAN_REVIEW | REVERTED | NOOP_DEDUPED
    path: str = ""
    changes: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)
    inserted_entries: list[str] = field(default_factory=list)
    rendered_diff: str = ""


@dataclass
class EvolutionOutcome:
    action: str  # SKIP | HUMAN_REVIEW | AUTO_MERGED | REVERTED | NOOP_DEDUPED
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


# 输入契约阈值
_MIN_EVIDENCE_DESC_LEN = 30  # description 少于此长度视为"纯摘要"
_MIN_EVIDENCE_RATIO = 0.5  # 低于此比例触发警告


def _check_evidence_quality(judge_results: list[dict]) -> tuple[int, int, str]:
    """校验 judge_results 中 issue 的证据质量.

    判断标准：
    - 有 source_excerpt / original_text 字段（非空）→ 强证据
    - description 长度 >= _MIN_EVIDENCE_DESC_LEN → 视为有效观察（可能包含原始引用）
    - 两者均不满足 → 纯摘要

    Returns:
        (with_evidence, total, warning_msg)
        warning_msg 为空表示质量合格。
    """
    total = with_evidence = 0
    for jr in judge_results:
        for issue in jr.get("issues", []):
            total += 1
            desc = issue.get("description", "")
            has_excerpt = bool(issue.get("source_excerpt") or issue.get("original_text"))
            if has_excerpt or len(desc) >= _MIN_EVIDENCE_DESC_LEN:
                with_evidence += 1

    if total == 0:
        return 0, 0, ""

    ratio = with_evidence / total
    if ratio == 0:
        return (
            0,
            total,
            (
                f"输入契约违反：{total} 条 issue 均无原始片段（source_excerpt）且 description 过短，"
                "无法生成可信 skill 规则。请在 judge_results 中提供 source_excerpt 字段或完整描述。"
            ),
        )
    if ratio < _MIN_EVIDENCE_RATIO:
        return (
            with_evidence,
            total,
            (
                f"输入契约警告：{with_evidence}/{total} 条 issue 有证据支撑（{ratio:.0%}），"
                f"低于阈值 {_MIN_EVIDENCE_RATIO:.0%}。建议补充 source_excerpt 字段以提升规则质量。"
            ),
        )
    return with_evidence, total, ""


class SkillReflector:
    """Analyzes adaptive loop failures and auto-evolves skill rules."""

    def __init__(self, phase: str, project_id: str):
        self.phase = phase
        self.project_id = project_id

    def reflect(self, judge_results: list[dict]) -> ReflectResult:
        """Analyze judge results, classify root cause via LLM, extract failure patterns.

        输入契约：judge_results 中的 issue 应包含 source_excerpt 字段或足够长的 description，
        以防止基于纯摘要生成不可信的 skill 规则。
        """
        # 输入契约检查
        _, _, warning = _check_evidence_quality(judge_results)
        if warning and "违反" in warning:
            log.warning("SkillReflector.reflect: %s", warning)
            return ReflectResult(actionable=False, evidence_warning=warning)
        if warning:
            log.warning("SkillReflector.reflect: %s", warning)

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

        root_cause, _pattern, fix = self._classify_root_cause(unique_issues)

        if root_cause == "UNKNOWN":
            return ReflectResult(actionable=False, failure_patterns=unique_issues)

        return ReflectResult(
            actionable=True,
            root_cause=root_cause,
            failure_patterns=unique_issues,
            suggested_changes=[fix] if fix else [f"Address: {unique_issues[0][:100]}"],
            evidence_warning=warning,
        )

    def _classify_root_cause(self, issues: list[str]) -> tuple[str, str, str]:
        """Use LLM to classify root cause. Returns (root_cause, pattern, fix)."""
        from qualix.agents.llm_backends import LLMConfig, create_backend
        from qualix.constants import DEFAULT_RATIONALIZATION_CONFIRM_MODEL

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

            m = re.search(r"\{.*\}", content, re.DOTALL)
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

        SKILL_RULE + high confidence + auto-merge enabled → apply to SKILL.md + holdout verify
        CONTEXT → append to _context_hints.md
        SCHEMA → append to _schema_hints.md
        Others → HUMAN_REVIEW suggestion file
        """
        from qualix.tracking.skill_auto_merge import (
            apply_to_skill_file,
            verify_with_holdout,
            write_context_hints,
            write_schema_hints,
            write_suggestion_file,
        )

        root_cause = reflect_result.root_cause

        def _suggestion() -> str:
            return write_suggestion_file(
                self.project_id,
                self.phase,
                root_cause,
                reflect_result.failure_patterns,
                reflect_result.suggested_changes,
            )

        if root_cause == "CONTEXT":
            path = write_context_hints(
                self.project_id,
                self.phase,
                reflect_result.failure_patterns,
                reflect_result.suggested_changes,
            )
            return WriteResult(mode="AUTO_APPLY", path=path, changes=reflect_result.suggested_changes)

        if root_cause == "SCHEMA":
            path = write_schema_hints(
                self.project_id,
                self.phase,
                reflect_result.failure_patterns,
                reflect_result.suggested_changes,
            )
            return WriteResult(mode="AUTO_APPLY", path=path, changes=reflect_result.suggested_changes)

        if root_cause == "SKILL_RULE":
            if support_count < HIGH_CONFIDENCE_THRESHOLD:
                suggestion_path = _suggestion()
                return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

            skill_path = SKILL_FILE_MAP.get(self.phase, "")
            if not skill_path:
                suggestion_path = _suggestion()
                return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

            if not SKILL_AUTO_MERGE_ENABLED:
                suggestion_path = _suggestion()
                return WriteResult(
                    mode="HUMAN_REVIEW",
                    path=suggestion_path,
                    changes=reflect_result.suggested_changes,
                    target_files=[skill_path],
                )

            # Auto-merge: snapshot → apply → holdout verify → revert if overfitting
            snapshot = self.snapshot_targets([skill_path])
            apply_result = apply_to_skill_file(skill_path, reflect_result.suggested_changes)
            if not apply_result.applied:
                # 全部被幂等检查跳过（或无效输入） → NOOP_DEDUPED，不跑 holdout
                if apply_result.skipped_duplicates and not apply_result.inserted_entries:
                    return WriteResult(
                        mode="NOOP_DEDUPED",
                        path=skill_path,
                        changes=reflect_result.suggested_changes,
                        target_files=[skill_path],
                        skipped_duplicates=list(apply_result.skipped_duplicates),
                        rendered_diff=apply_result.rendered_diff,
                    )
                self.rollback(snapshot)
                suggestion_path = _suggestion()
                return WriteResult(mode="HUMAN_REVIEW", path=suggestion_path)

            holdout_ok = verify_with_holdout(self.phase)
            if not holdout_ok:
                self.rollback(snapshot)
                log.warning("Auto-merge reverted for %s: holdout overfitting detected", self.phase)
                suggestion_path = _suggestion()
                return WriteResult(
                    mode="REVERTED",
                    path=suggestion_path,
                    changes=reflect_result.suggested_changes,
                    target_files=[skill_path],
                    skipped_duplicates=list(apply_result.skipped_duplicates),
                    inserted_entries=list(apply_result.inserted_entries),
                    rendered_diff=apply_result.rendered_diff,
                )

            log.info("Auto-merged skill rules for %s (support=%d)", self.phase, support_count)
            return WriteResult(
                mode="AUTO_APPLY",
                path=skill_path,
                changes=reflect_result.suggested_changes,
                target_files=[skill_path],
                skipped_duplicates=list(apply_result.skipped_duplicates),
                inserted_entries=list(apply_result.inserted_entries),
                rendered_diff=apply_result.rendered_diff,
            )

        suggestion_path = _suggestion()
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
            self.phase,
            "FN",
            reflect_result.root_cause,
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

        current = load_json(case_path)
        if not current:
            return 1
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
            data = load_json(cf)
            if not data:
                continue
            if data.get("fingerprint") == fingerprint:
                sig = data.get("source_signature", "")
                if sig:
                    signatures.add(sig)

        return len(signatures)

    def reflect_and_write(self, judge_results: list[dict]) -> EvolutionOutcome:
        """Full Reflect→Persist→Cluster→Write pipeline."""
        reflect_result = self.reflect(judge_results)
        if not reflect_result.actionable:
            return EvolutionOutcome(action="SKIP", reason="No actionable pattern found")

        case_id = self.persist_as_bug_case(reflect_result)
        support_count = self.cluster_and_count_support(case_id)

        write_result = self.write(reflect_result, support_count)

        if write_result.mode == "AUTO_APPLY":
            action = "AUTO_MERGED"
        elif write_result.mode == "REVERTED":
            action = "REVERTED"
        elif write_result.mode == "NOOP_DEDUPED":
            action = "NOOP_DEDUPED"
        else:
            action = "HUMAN_REVIEW"
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
            "- Adaptive Loop 全部迭代 FAIL，Judge 健康（SEMANTIC_FAIL）",
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

        if write_result.skipped_duplicates:
            lines.append("- 幂等跳过（已存在的规则）:")
            for s in write_result.skipped_duplicates:
                lines.append(f"  - {s}")

        if write_result.rendered_diff:
            lines += [
                "",
                "### Apply Diff",
                "",
                "```",
                write_result.rendered_diff,
                "```",
            ]

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
