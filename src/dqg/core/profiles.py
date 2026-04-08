"""Pluggable DQG profiles."""

from __future__ import annotations

import json
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dqg.json_utils import dump_json_str, load_json_strict


@dataclass(frozen=True)
class DqgProfile:
    profile_id: str
    name: str
    description: str
    baseline_path: Path
    risk_catalog_path: Path
    quality_thresholds: dict[str, Any]


def _profiles_root() -> Path:
    return Path(__file__).resolve().parents[3] / "profiles"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


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
    )


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
        "name": profile.name,
        "description": profile.description,
        "baseline_path": str(profile.baseline_path),
        "risk_catalog_path": str(profile.risk_catalog_path),
        "coverage_thresholds": profile.quality_thresholds,
    }


def render_profile_context_markdown(profile: DqgProfile) -> str:
    lines = [
        "## PROFILE_CONTEXT",
        "",
        f"- Profile: `{profile.profile_id}`",
        f"- Name: {profile.name}",
        f"- Description: {profile.description}",
        f"- Baseline: `{profile.baseline_path}`",
        f"- Risk Catalog: `{profile.risk_catalog_path}`",
        "- Quality Thresholds:",
    ]
    for key, value in profile.quality_thresholds.items():
        lines.append(f"  - `{key}`: `{value}`")
    lines.append("")
    lines.append("> 将本节放在报告开头，用于声明本次评审/审计所采用的基线与阈值。")
    return "\n".join(lines) + "\n"
