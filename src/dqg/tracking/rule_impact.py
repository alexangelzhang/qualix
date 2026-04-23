"""Rule Impact：Profile 规则变更 → 指标影响关联报告."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json, save_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_rule_impact(profile_id: str, output_dir_arg: str | None) -> int:
    """生成 rule change → metric impact 关联报告."""
    from dqg.constants import RULE_HASHES_FILENAME
    from dqg.core.profiles import compute_rule_hash

    current_hashes = compute_rule_hash(profile_id)
    if not current_hashes:
        print(f"Profile '{profile_id}' 无可解析的规则块")
        return 1

    # 扫描所有项目目录下的 _rule_hashes.json，收集历史 hash
    repo_root = _repo_root()
    output_base = repo_root / "output"
    saved_map: dict[str, dict[str, str]] = {}
    if output_base.exists():
        for hash_file in output_base.rglob(RULE_HASHES_FILENAME):
            project_id = hash_file.parent.name
            data = load_json(hash_file)
            if isinstance(data, dict):
                saved_map[project_id] = data

    # 计算变更
    all_titles = set(current_hashes)
    for saved in saved_map.values():
        all_titles |= set(saved)

    changes = _diff_rule_hashes(current_hashes, saved_map, all_titles)

    # 输出
    output_dir = Path(output_dir_arg) if output_dir_arg else repo_root / "regression" / "rule-impact" / profile_id
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "rule_impact.json"
    md_path = output_dir / "rule_impact.md"

    payload = {
        "profile_id": profile_id,
        "timestamp": datetime.now().isoformat(),
        "total_rules": len(all_titles),
        "changed_rules": sum(1 for c in changes if c["status"] != "UNCHANGED"),
        "changes": changes,
    }
    save_json(json_path, payload)
    _write_md_report(md_path, profile_id, all_titles, changes)

    print(f"Rule impact JSON: {json_path}")
    print(f"Rule impact report: {md_path}")
    return 0


def _diff_rule_hashes(
    current: dict[str, str],
    saved_map: dict[str, dict[str, str]],
    all_titles: set[str],
) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for title in sorted(all_titles):
        cur = current.get(title)
        prev = _find_saved(title, saved_map)

        if cur and not prev:
            changes.append({"rule": title, "status": "ADDED", "current_hash": cur, "previous_hash": "-"})
        elif prev and not cur:
            changes.append({"rule": title, "status": "REMOVED", "current_hash": "-", "previous_hash": prev})
        elif cur != prev:
            changes.append(
                {"rule": title, "status": "MODIFIED", "current_hash": cur or "-", "previous_hash": prev or "-"}
            )
        else:
            changes.append(
                {"rule": title, "status": "UNCHANGED", "current_hash": cur or "-", "previous_hash": prev or "-"}
            )
    return changes


def _find_saved(title: str, saved_map: dict[str, dict[str, str]]) -> str | None:
    for saved in saved_map.values():
        if title in saved:
            return saved[title]
    return None


def _write_md_report(
    md_path: Path,
    profile_id: str,
    all_titles: set[str],
    changes: list[dict[str, Any]],
) -> None:
    modified = [c for c in changes if c["status"] != "UNCHANGED"]
    lines = [
        f"# Rule Impact Report: {profile_id}",
        "",
        f"Total rules: {len(all_titles)} | Changed: {len(modified)}",
        "",
        "| Rule | Status | Previous Hash | Current Hash |",
        "| --- | --- | --- | --- |",
    ]
    for c in changes:
        lines.append(f"| {c['rule']} | {c['status']} | `{c['previous_hash']}` | `{c['current_hash']}` |")
    lines.append("")
    md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
