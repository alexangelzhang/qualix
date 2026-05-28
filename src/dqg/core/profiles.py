"""Pluggable DQG profiles."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dqg.core.resource_resolver import ResourceResolver
from dqg.json_utils import dump_json_str, load_json_strict

_LANGUAGE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_REQUIRED_PROFILE_FIELDS = {
    "profile_id",
    "version",
    "name",
    "description",
    "language",
    "baseline_path",
    "risk_catalog_path",
    "quality_thresholds",
}
_resolver = ResourceResolver()


@dataclass(frozen=True)
class DqgProfile:
    profile_id: str
    name: str
    description: str
    baseline_path: Path
    risk_catalog_path: Path
    quality_thresholds: dict[str, Any]
    language: str = "java"
    version: str = "1.0.0"


def _profiles_root() -> Path:
    return _resolver.resolve_dir("profiles")


def _repo_root() -> Path:
    """Root containing regression/ and knowledge/ — base for profile relative paths."""
    try:
        return _resolver.resolve_dir("regression").parent
    except FileNotFoundError:
        return _resolver.global_root


def _load_profile(path: Path) -> DqgProfile:
    data = load_json_strict(path)
    root = _repo_root()
    return DqgProfile(
        profile_id=data["profile_id"],
        name=data["name"],
        description=data["description"],
        baseline_path=root / data["baseline_path"],
        risk_catalog_path=root / data["risk_catalog_path"],
        quality_thresholds=data.get("quality_thresholds", {}),
        language=data.get("language", "java"),
        version=data.get("version", "1.0.0"),
    )


@lru_cache(maxsize=1)
def list_profiles() -> list[DqgProfile]:
    profiles = []
    for path in sorted(_profiles_root().glob("*/profile.json")):
        profiles.append(_load_profile(path))
    return profiles


def get_profile(profile_id: str | None = None) -> DqgProfile:
    target = profile_id or "java-ddd-tmf"
    for profile in list_profiles():
        if profile.profile_id == target:
            return profile
    raise ValueError(f"Unknown profile: {target}")


def validate_profile_file(path: Path, repo_root: Path | None = None) -> list[str]:
    """Validate one profile.json and return human-readable schema issues."""
    root = repo_root or _repo_root()
    issues: list[str] = []

    try:
        data = load_json_strict(path)
    except Exception as exc:
        return [f"{path}: invalid JSON: {exc}"]

    for field in sorted(_REQUIRED_PROFILE_FIELDS):
        if field not in data:
            issues.append(f"{path}: missing required field: {field}")

    for field in ("profile_id", "name", "description", "baseline_path", "risk_catalog_path"):
        value = data.get(field)
        if field in data and (not isinstance(value, str) or not value.strip()):
            issues.append(f"{path}: field {field} must be a non-empty string")

    version = data.get("version", "1.0.0")
    if not isinstance(version, str) or not _SEMVER_RE.match(version):
        issues.append(f"{path}: version must use semantic format MAJOR.MINOR.PATCH")

    language = data.get("language")
    if "language" in data and (not isinstance(language, str) or not _LANGUAGE_ID_RE.match(language)):
        issues.append(f"{path}: language must be a lowercase provider id, e.g. java, go, typescript")

    thresholds = data.get("quality_thresholds")
    if "quality_thresholds" in data:
        if not isinstance(thresholds, dict) or not thresholds:
            issues.append(f"{path}: quality_thresholds must be a non-empty object")
        else:
            for key, value in thresholds.items():
                if not isinstance(value, int | float) or not 0 <= float(value) <= 1:
                    issues.append(f"{path}: quality_thresholds.{key} must be a number between 0 and 1")

    for field in ("baseline_path", "risk_catalog_path"):
        value = data.get(field)
        if isinstance(value, str) and value.strip() and not (root / value).exists():
            issues.append(f"{path}: {field} does not exist: {value}")

    return issues


def validate_all_profiles(profiles_root: Path | None = None, repo_root: Path | None = None) -> dict[str, list[str]]:
    """Validate all profile.json files and return only profiles with issues."""
    root = repo_root or _repo_root()
    profile_root = profiles_root or _profiles_root()
    issues_by_profile: dict[str, list[str]] = {}

    for path in sorted(profile_root.glob("*/profile.json")):
        issues = validate_profile_file(path, repo_root=root)
        if issues:
            issues_by_profile[path.parent.name] = issues

    return issues_by_profile


@lru_cache(maxsize=32)
def _load_profile_context_cached(
    payload_json: str,
    baseline_path: str,
    baseline_mtime_ns: int,
    risk_catalog_path: str,
    risk_catalog_mtime_ns: int,
) -> str:
    """按文件路径 + mtime 缓存 profile 上下文全文。"""
    payload = json.loads(payload_json)
    payload["baseline_excerpt"] = Path(baseline_path).read_text(encoding="utf-8")
    payload["risk_catalog_excerpt"] = Path(risk_catalog_path).read_text(encoding="utf-8")
    # mtime 只用于缓存 key，避免文件内容变更后仍复用旧结果。
    _ = baseline_mtime_ns, risk_catalog_mtime_ns
    return dump_json_str(payload)


def load_profile_context(profile: DqgProfile) -> str:
    payload = profile_to_payload(profile)
    payload_json = dump_json_str(payload)
    baseline_mtime_ns = profile.baseline_path.stat().st_mtime_ns
    risk_catalog_mtime_ns = profile.risk_catalog_path.stat().st_mtime_ns
    return _load_profile_context_cached(
        payload_json,
        str(profile.baseline_path),
        baseline_mtime_ns,
        str(profile.risk_catalog_path),
        risk_catalog_mtime_ns,
    )


def profile_to_payload(profile: DqgProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "name": profile.name,
        "description": profile.description,
        "language": profile.language,
        "baseline_path": str(profile.baseline_path),
        "risk_catalog_path": str(profile.risk_catalog_path),
        "coverage_thresholds": profile.quality_thresholds,
    }


def render_profile_context_markdown(profile: DqgProfile) -> str:
    lines = [
        "## PROFILE_CONTEXT",
        "",
        f"- Profile: `{profile.profile_id}`",
        f"- Version: `{profile.version}`",
        f"- Name: {profile.name}",
        f"- Description: {profile.description}",
        f"- Language: `{profile.language}`",
        f"- Baseline: `{profile.baseline_path}`",
        f"- Risk Catalog: `{profile.risk_catalog_path}`",
        "- Quality Thresholds:",
    ]
    for key, value in profile.quality_thresholds.items():
        lines.append(f"  - `{key}`: `{value}`")
    lines.append("")
    lines.append("> 将本节放在报告开头，用于声明本次评审/审计所采用的基线与阈值。")
    return "\n".join(lines) + "\n"


# Rule Hash：按 Markdown 标题拆分规则块，计算 SHA256 指纹


def _split_md_rules(text: str) -> dict[str, str]:
    """按 ## 或 ### 标题拆分 Markdown 为独立规则块."""
    blocks: dict[str, str] = {}
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if re.match(r"^#{2,3}\s+", line):
            if current_title is not None:
                blocks[current_title] = "\n".join(current_lines).strip()
            current_title = line.lstrip("#").strip()
            current_lines = [line]
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        blocks[current_title] = "\n".join(current_lines).strip()

    return blocks


def _hash_block(text: str) -> str:
    """SHA256 前 12 位."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def compute_rule_hash(profile_id: str) -> dict[str, str]:
    """计算 profile 的 baseline + risk_catalog 每条规则的 SHA256 hash.

    返回 {rule_title: hash_12} 映射。
    """
    profile = get_profile(profile_id)
    hashes: dict[str, str] = {}

    for path in (profile.baseline_path, profile.risk_catalog_path):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            for title, block in _split_md_rules(text).items():
                hashes[title] = _hash_block(block)

    return hashes


# L0 压缩：把 baseline + risk catalog 压缩为结构化元规则

_L0_CACHE: dict[str, str] = {}


def compress_to_l0(profile: DqgProfile) -> str:
    """将 profile 的 baseline + risk catalog 压缩为 L0 元规则.

    L0 层只保留最精炼的规则摘要，而非全文注入。
    压缩策略：
    1. 提取 markdown 标题结构（## / ### 层级）
    2. 提取表格行（规则定义）
    3. 提取"禁止/必须/强制"等强约束句
    4. 丢弃示例代码块、说明性段落
    """
    cache_key = profile.profile_id
    if cache_key in _L0_CACHE:
        return _L0_CACHE[cache_key]

    parts: list[str] = []

    # Baseline L0
    if profile.baseline_path.exists():
        baseline_text = profile.baseline_path.read_text(encoding="utf-8")
        parts.append(f"# L0 Baseline: {profile.profile_id}")
        parts.append("")
        parts.extend(_extract_l0_rules(baseline_text))

    # Risk catalog L0
    if profile.risk_catalog_path.exists():
        risk_text = profile.risk_catalog_path.read_text(encoding="utf-8")
        parts.append("")
        parts.append("# L0 Risk Catalog")
        parts.append("")
        parts.extend(_extract_l0_rules(risk_text))

    # Quality thresholds（已经是结构化的，直接保留）
    if profile.quality_thresholds:
        parts.append("")
        parts.append("# L0 Quality Thresholds")
        for k, v in profile.quality_thresholds.items():
            parts.append(f"- {k}: {v}")

    result = "\n".join(parts)
    _L0_CACHE[cache_key] = result
    return result


def _extract_l0_rules(text: str) -> list[str]:
    """从 markdown 文本中提取 L0 元规则."""
    lines: list[str] = []
    in_code_block = False

    # 强约束关键词
    constraint_pattern = re.compile(
        r"(禁止|必须|强制|不得|不允许|务必|严禁|"
        r"MUST|SHALL|REQUIRED|FORBIDDEN|NEVER|ALWAYS)",
        re.IGNORECASE,
    )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        # 跳过代码块
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # 保留标题
        if stripped.startswith("#"):
            lines.append(stripped)
            continue

        # 保留表格行（规则定义）
        if stripped.startswith("|") and "---" not in stripped:
            lines.append(stripped)
            continue

        # 保留强约束句
        if constraint_pattern.search(stripped):
            lines.append(f"- {stripped}" if not stripped.startswith("-") else stripped)
            continue

        # 保留编号规则（1. 2. 3.）
        if re.match(r"^\d+\.\s", stripped) and len(stripped) > 10:
            lines.append(stripped)
            continue

    return lines


def load_profile_context_l0(profile: DqgProfile) -> str:
    """加载 L0 压缩版 profile context（用于 token 紧张场景）."""
    l0 = compress_to_l0(profile)
    payload = profile_to_payload(profile)
    payload["baseline_excerpt"] = "[L0 compressed — see rules below]"
    payload["risk_catalog_excerpt"] = "[L0 compressed — see rules below]"
    payload["l0_rules"] = l0
    return dump_json_str(payload)


# Phase → relevant baseline section keywords for L1 filtering
_PHASE_RELEVANT_SECTIONS: dict[str, set[str]] = {
    "Q01": {"需求", "需求歧义", "验收", "语义", "风险分级"},
    "Q03": {"架构", "DDD", "TMF", "编排", "异常场景", "Checklist", "评审", "风险"},
    "Q04": {"覆盖", "断言", "单测", "异常场景", "风险"},
    "Q05": {"单测", "断言", "Mock", "DDD", "TMF", "变异", "覆盖率"},
    "Q05a": {"单测", "断言", "Mock", "DDD", "TMF", "变异", "覆盖率"},
    "Q05b": {"单测", "断言", "Mock", "DDD", "TMF", "编译", "覆盖率"},
    "Q06": {"单测", "断言", "Mock", "覆盖率", "变异", "异常"},
    "Q07": {"架构", "DDD", "TMF", "Checklist", "评审", "异常场景", "覆盖率", "风险"},
}


def compress_to_l1(profile: DqgProfile, phase_id: str | None = None) -> str:
    """L1 压缩：在 L0 基础上按 Phase 过滤相关 sections + 去掉空标题."""
    l0 = compress_to_l0(profile)
    relevant_kw = _PHASE_RELEVANT_SECTIONS.get(phase_id or "")
    if not relevant_kw:
        return l0
    filtered: list[str] = []
    in_relevant = True  # top-level content before first ## is always relevant
    for line in l0.split("\n"):
        if line.startswith("# L0 ") or (line.startswith("# ") and not line.startswith("## ")):
            filtered.append(line)
            in_relevant = True
        elif line.startswith("## "):
            in_relevant = any(kw in line for kw in relevant_kw)
            if in_relevant:
                filtered.append(line)
        elif line.startswith("### "):
            # Sub-sections inherit parent relevance
            if in_relevant:
                filtered.append(line)
        elif in_relevant and line.strip():
            filtered.append(line)
    return "\n".join(filtered)


def load_profile_context_l1(profile: DqgProfile, phase_id: str | None = None) -> str:
    """加载 L1 压缩版 profile context（Phase 感知过滤）."""
    l1 = compress_to_l1(profile, phase_id)
    parts = [f"# Profile: {profile.profile_id} ({profile.name})", l1]
    if profile.quality_thresholds:
        parts.append("# Quality Thresholds")
        parts.extend(f"- {k}: {v}" for k, v in profile.quality_thresholds.items())
    return "\n".join(parts)
