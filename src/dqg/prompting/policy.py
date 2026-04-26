"""Prompt Policy Gate checks."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from dqg.json_utils import load_json

if TYPE_CHECKING:
    from pathlib import Path

_STRUCTURED_PROMPT_TYPES = {"judge", "critique", "preference"}
_EVIDENCE_PROMPT_TYPES = {"judge", "critique", "review_chain"}
_PROTOCOL_PROMPT_TYPES = {"judge", "critique", "review_chain"}
_REQUIRED_MANIFEST_FIELDS = {
    "prompt_id",
    "prompt_type",
    "phase_id",
    "role",
    "version",
    "prompt_hash",
    "asset_hashes",
}
_EVIDENCE_TERMS = ("证据", "引用", "evidence", "source", "citation")
_PERSONA_PATTERNS = (
    "你的身份",
    "你是一位",
    "你是一个",
    "资深",
    "专家",
    "多年经验",
    "年经验",
)
_PROTOCOL_TERMS = ("检查清单", "行为红线")


@dataclass(frozen=True)
class PromptPolicyIssue:
    """Single prompt policy violation."""

    code: str
    message: str
    severity: str = "BLOCKED"

    def to_payload(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class PromptPolicyResult:
    """Policy result for one prompt artifact."""

    prompt_path: str
    manifest_path: str
    issues: list[PromptPolicyIssue]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "BLOCKED" for issue in self.issues)

    def to_payload(self) -> dict[str, object]:
        return {
            "prompt_path": self.prompt_path,
            "manifest_path": self.manifest_path,
            "passed": self.passed,
            "issues": [issue.to_payload() for issue in self.issues],
        }


def validate_prompt_artifact(prompt_path: Path) -> PromptPolicyResult:
    """Validate one prompt file against deterministic policy rules."""
    manifest_path = prompt_path.parent / "_internal" / "_prompt_manifests" / f"{prompt_path.stem}.json"
    issues: list[PromptPolicyIssue] = []

    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        return PromptPolicyResult(
            prompt_path=str(prompt_path),
            manifest_path=str(manifest_path),
            issues=[PromptPolicyIssue("missing_manifest", f"Missing or invalid prompt manifest: {manifest_path}")],
        )

    missing_fields = sorted(field for field in _REQUIRED_MANIFEST_FIELDS if field not in manifest)
    if missing_fields:
        issues.append(
            PromptPolicyIssue(
                "incomplete_manifest",
                f"Prompt manifest missing required fields: {', '.join(missing_fields)}",
            )
        )

    prompt_hash = manifest.get("prompt_hash")
    if isinstance(prompt_hash, str) and prompt_hash != _sha256_text(prompt_text):
        issues.append(PromptPolicyIssue("prompt_hash_mismatch", "Prompt text does not match manifest prompt_hash"))

    prompt_type = manifest.get("prompt_type")
    if prompt_type in _STRUCTURED_PROMPT_TYPES and not manifest.get("output_schema"):
        issues.append(PromptPolicyIssue("missing_output_schema", f"{prompt_type} prompt must bind output_schema"))

    if prompt_type in _EVIDENCE_PROMPT_TYPES and not _contains_evidence_contract(prompt_text):
        issues.append(
            PromptPolicyIssue(
                "missing_evidence_contract",
                f"{prompt_type} prompt must require evidence-backed conclusions",
            )
        )

    if prompt_type in _PROTOCOL_PROMPT_TYPES and not _contains_protocol_contract(prompt_text):
        issues.append(
            PromptPolicyIssue(
                "missing_protocol_contract",
                f"{prompt_type} prompt must include concrete checklist and red-line constraints",
            )
        )

    if _contains_expert_persona(prompt_text):
        issues.append(
            PromptPolicyIssue(
                "expert_persona_label",
                "Prompt must use concrete evaluation criteria instead of expert persona labels",
            )
        )

    return PromptPolicyResult(prompt_path=str(prompt_path), manifest_path=str(manifest_path), issues=issues)


def discover_prompt_artifacts(phase_root: Path) -> list[Path]:
    """Return prompt files that should have policy manifests."""
    candidates = list(phase_root.glob("_*_prompt.md"))
    review_chain = phase_root / "_review_chain.md"
    if review_chain.exists():
        candidates.append(review_chain)
    return sorted({path for path in candidates if path.is_file()})


def _contains_evidence_contract(prompt_text: str) -> bool:
    lowered = prompt_text.lower()
    return any(term in lowered for term in _EVIDENCE_TERMS)


def _contains_protocol_contract(prompt_text: str) -> bool:
    return all(term in prompt_text for term in _PROTOCOL_TERMS)


def _contains_expert_persona(prompt_text: str) -> bool:
    return any(pattern in prompt_text for pattern in _PERSONA_PATTERNS)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
