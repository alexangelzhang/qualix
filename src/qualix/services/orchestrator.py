#!/usr/bin/env python3
"""
流程编排器：自动检测已完成的阶段，提示下一步，传入上一阶段报告路径。

用法:
    python3 scripts/orchestrator.py <project_id>
    python3 scripts/orchestrator.py <project_id> --next        # 自动进入下一阶段
    python3 scripts/orchestrator.py <project_id> --status      # 仅显示状态
    python3 scripts/orchestrator.py <project_id> --skip A.6    # 跳过指定阶段

示例:
    python3 scripts/orchestrator.py KMgHd
    python3 scripts/orchestrator.py KMgHd --next
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Final

from qualix.constants import PHASE_DIR_MAP, REPORT_MAP
from qualix.core.state_machine import PHASE_DEFS

# orchestrator 专用字段（command / description），依赖关系从 PHASE_DEFS.depends_on 读取
_ORCH_EXTRA: Final = MappingProxyType(
    {
        "Q01": {"command": "/qualix", "description": "PRD → 需求点/关键语义/缺口/待确认项"},
        "Q04": {"command": "/tech-coverage-audit", "description": "验证技术方案有没有漏掉需求"},
        "Q03": {"command": "/tech-quality-review", "description": "审架构/接口/数据/异常/性能"},
        "Q05": {"command": "/ut-generator", "description": "从需求生成测试大纲和单测代码"},
        "Q05a": {"command": "/ut-design", "description": "设计 EUT 矩阵（三层驱动），approve 后锁定为 Q05b 规格"},
        "Q05b": {"command": "/ut-codegen", "description": "按 EUT 矩阵逐条生成 @Test 代码，Ralph Loop 直到 C9 全通过"},
        "Q06": {"command": "/ut-audit-zh", "description": "验证单测是否真正测对了业务场景"},
        "Q07": {"command": "/review-zh", "description": "验证代码是否与需求和设计一致"},
    }
)

# Phase 名称映射
_PHASE_NAMES: Final = MappingProxyType(
    {
        "Q01": "需求结构化",
        "Q04": "技术方案覆盖度审计",
        "Q03": "技术方案质量评审",
        "Q05": "单测生成",
        "Q05a": "EUT 矩阵设计",
        "Q05b": "单测代码生成",
        "Q06": "单测覆盖审计",
        "Q07": "代码评审",
    }
)

# 组装 PHASES 列表（权威数据来自 constants.py，orchestrator 只补充自己的字段）
PHASES = [
    {
        "id": pid,
        "name": _PHASE_NAMES[pid],
        "dir_suffix": PHASE_DIR_MAP[pid],
        "key_file": REPORT_MAP[pid],
        **_ORCH_EXTRA[pid],
    }
    for pid in ["Q01", "Q04", "Q03", "Q05", "Q05a", "Q05b", "Q06", "Q07"]
]


@dataclass
class PhaseStatus:
    phase_id: str
    name: str
    completed: bool
    dir_path: str | None = None
    key_file_path: str | None = None
    modified_time: str | None = None
    skipped: bool = False


def find_output_dir(base_dir: Path, project_id: str) -> Path:
    return base_dir / "output"


def detect_phase_status(output_dir: Path, project_id: str, phase: dict) -> PhaseStatus:
    """检测某个阶段的完成状态。支持标准命名和旧版命名。"""

    # 标准命名：<project_id>/<phase_dir>
    # 旧版命名：<project_id>_requirements*, <project_id>_larkkit_cli, 等
    candidates = [
        # 标准命名
        output_dir / project_id / phase["dir_suffix"],
    ]

    # 旧版命名兼容（仅 Phase A）
    if phase["id"] == "Q01":
        # 匹配 <id>_requirements*, <id>_larkkit_cli 等旧目录
        for p in sorted(output_dir.iterdir()):
            if not p.is_dir():
                continue
            name = p.name
            if not name.startswith(project_id):
                continue
            if name == project_id:
                continue  # 已在标准候选中（作为父目录）
            # 旧版目录：含 requirements, larkkit, 或直接是 project_id
            if any(tag in name for tag in ["requirements", "larkkit", "_cli"]):
                candidates.append(p)

    # A.5/A.6 也检查扁平目录（报告放在 phaseA 目录下）
    if phase["id"] in ("Q04", "Q03"):
        phase_a_dir = output_dir / project_id / PHASE_DIR_MAP["Q01"]
        if phase_a_dir.is_dir() and phase_a_dir not in candidates:
            candidates.append(phase_a_dir)

    for candidate in candidates:
        if candidate and candidate.is_dir():
            key_file = candidate / phase["key_file"]
            if key_file.exists():
                mtime = datetime.fromtimestamp(key_file.stat().st_mtime)
                return PhaseStatus(
                    phase_id=phase["id"],
                    name=phase["name"],
                    completed=True,
                    dir_path=str(candidate),
                    key_file_path=str(key_file),
                    modified_time=mtime.strftime("%Y-%m-%d %H:%M"),
                )

    # 检查是否有目录存在但关键文件缺失（正在进行中）
    primary = output_dir / project_id / phase["dir_suffix"]
    if primary.is_dir():
        # 有 ingest 数据说明至少跑过 Step 0
        has_ingest = (primary / "ingest.json").exists() or (primary / "aggregate_ingest.json").exists()
        return PhaseStatus(
            phase_id=phase["id"],
            name=phase["name"],
            completed=False,
            dir_path=str(primary),
            modified_time="有数据" if has_ingest else None,
        )

    # 旧版目录有 ingest 数据但无报告
    if phase["id"] == "Q01":
        for candidate in candidates[1:]:  # 跳过标准命名（已检查）
            if candidate and candidate.is_dir():
                has_ingest = (candidate / "ingest.json").exists() or (candidate / "aggregate_ingest.json").exists()
                if has_ingest:
                    return PhaseStatus(
                        phase_id=phase["id"],
                        name=phase["name"],
                        completed=False,
                        dir_path=str(candidate),
                        modified_time="有数据(旧版目录)",
                    )

    return PhaseStatus(
        phase_id=phase["id"],
        name=phase["name"],
        completed=False,
    )


def print_status_dashboard(statuses: list[PhaseStatus], skip_phases: list[str]):
    """打印流程状态看板。"""
    print()
    print("=" * 64)
    print("  流程编排状态看板")
    print("=" * 64)
    print(f"  {'阶段':<8} {'名称':<20} {'状态':<10} {'完成时间':<18}")
    print("-" * 64)

    for s in statuses:
        if s.phase_id in skip_phases:
            status_str = "⏭ 已跳过"
        elif s.completed:
            status_str = "✅ 已完成"
        elif s.dir_path and s.modified_time and "有数据" in s.modified_time:
            status_str = "🔶 有数据未完成"
        elif s.dir_path:
            status_str = "🔶 进行中"
        else:
            status_str = "⬜ 未开始"

        time_str = s.modified_time or "—"
        print(f"  {s.phase_id:<8} {s.name:<20} {status_str:<10} {time_str:<18}")

    print("=" * 64)


_tracked_ids: frozenset[str] = frozenset(p["id"] for p in PHASES)


def find_next_phase(statuses: list[PhaseStatus], skip_phases: list[str]) -> dict | None:
    """找到下一个应该执行的阶段。"""
    completed_ids = {s.phase_id for s in statuses if s.completed}
    completed_ids.update(skip_phases)

    for phase in PHASES:
        if phase["id"] in completed_ids:
            continue
        if phase["id"] in skip_phases:
            continue
        # 从 PHASE_DEFS 读取依赖（权威来源）。
        # 不在 PHASES 里的 Phase（如 Q02 可选阶段）视为已满足，让下游 Phase 可用。
        deps = PHASE_DEFS.get(phase["id"], {}).get("depends_on", [])
        if all(dep in completed_ids or dep not in _tracked_ids for dep in deps):
            return phase

    return None


def build_next_command(phase: dict, statuses: list[PhaseStatus], project_id: str) -> str:
    """构建下一阶段的执行提示。"""
    deps = PHASE_DEFS.get(phase["id"], {}).get("depends_on", [])
    input_files = []
    for dep_id in deps:
        for s in statuses:
            if s.phase_id == dep_id and s.key_file_path:
                input_files.append(s.key_file_path)

    cmd = f"触发命令: {phase['command']}"
    if input_files:
        cmd += "\n  输入文件:"
        for f in input_files:
            cmd += f"\n    - {f}"

    return cmd


def save_orchestration_state(output_dir: Path, project_id: str, statuses: list[PhaseStatus], skip_phases: list[str]):
    """持久化编排状态到 JSON。"""
    state = {
        "project_id": project_id,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "phases": [],
        "skipped": skip_phases,
    }
    for s in statuses:
        state["phases"].append(
            {
                "id": s.phase_id,
                "name": s.name,
                "completed": s.completed,
                "skipped": s.phase_id in skip_phases,
                "dir_path": s.dir_path,
                "key_file_path": s.key_file_path,
                "modified_time": s.modified_time,
            }
        )

    state_file = output_dir / project_id / "orchestration.json"
    (output_dir / project_id).mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return state_file


def discover_projects(output_dir: Path) -> list[dict]:
    """扫描 output 目录，发现所有项目及其命名模式。"""
    projects = {}

    for p in sorted(output_dir.iterdir()):
        if not p.is_dir():
            continue
        name = p.name
        # 跳过隐藏目录
        if name.startswith("."):
            continue

        # 新版命名：<project_id>/<phaseX> （项目是一级目录）
        phase_dirs = [d for d in p.iterdir() if d.is_dir() and re.match(r"^(phase[A-D]\d?|Q\d{2})$", d.name)]
        if phase_dirs:
            pid = name
            if pid not in projects:
                projects[pid] = {"id": pid, "dirs": [], "naming": "standard"}
            projects[pid]["dirs"].extend([d.name for d in phase_dirs])
            continue

        # 旧版命名：<id>_phase<X>
        m = re.match(r"^(.+?)_(phaseA\d?|phaseB|phaseC|phaseD)$", name)
        if m:
            pid = m.group(1)
            if pid not in projects:
                projects[pid] = {"id": pid, "dirs": [], "naming": "legacy"}
            projects[pid]["dirs"].append(name)
            continue

        # 旧版命名：<id>_requirements*, <id>_larkkit_cli, etc.
        parts = name.split("_", 1)
        if len(parts) >= 2:
            pid = parts[0]
            if pid not in projects:
                projects[pid] = {"id": pid, "dirs": [], "naming": "legacy"}
            projects[pid]["dirs"].append(name)

    return list(projects.values())


def print_project_list(output_dir: Path):
    """打印所有发现的项目。"""
    projects = discover_projects(output_dir)

    print()
    print("=" * 64)
    print("  项目列表")
    print("=" * 64)
    print(f"  {'项目 ID':<16} {'命名规范':<12} {'目录数':<8} {'目录'}")
    print("-" * 64)

    for proj in projects:
        dirs_str = ", ".join(proj["dirs"][:3])
        if len(proj["dirs"]) > 3:
            dirs_str += f" (+{len(proj['dirs']) - 3})"
        naming = "标准" if proj["naming"] == "standard" else "旧版"
        print(f"  {proj['id']:<16} {naming:<12} {len(proj['dirs']):<8} {dirs_str}")

    print("=" * 64)
    print(f"\n  共 {len(projects)} 个项目")

    # 提示旧版命名的项目
    legacy = [p for p in projects if p["naming"] == "legacy"]
    if legacy:
        print(f"\n  ⚠️  {len(legacy)} 个项目使用旧版命名，建议迁移为 <id>/phaseA 格式")


def main():
    parser = argparse.ArgumentParser(description="流程编排器")
    parser.add_argument("project_id", nargs="?", help="项目 ID（如 KMgHd）")
    parser.add_argument("--next", action="store_true", help="显示下一步操作")
    parser.add_argument("--status", action="store_true", help="仅显示状态看板")
    parser.add_argument("--skip", nargs="*", default=[], help="跳过指定阶段（如 Q03）")
    parser.add_argument("--list-projects", action="store_true", help="列出所有项目")
    parser.add_argument("--base-dir", default=".", help="项目根目录")

    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    output_dir = base_dir / "output"

    if not output_dir.exists():
        print(f"错误: output 目录不存在: {output_dir}", file=sys.stderr)
        sys.exit(1)

    # 列出所有项目
    if args.list_projects:
        print_project_list(output_dir)
        return

    # 需要 project_id
    if not args.project_id:
        print("错误: 请指定项目 ID，或使用 --list-projects 查看所有项目", file=sys.stderr)
        sys.exit(1)

    # 检测各阶段状态
    statuses = []
    for phase in PHASES:
        status = detect_phase_status(output_dir, args.project_id, phase)
        statuses.append(status)

    # 打印状态看板
    print_status_dashboard(statuses, args.skip)

    # 保存编排状态
    state_file = save_orchestration_state(output_dir, args.project_id, statuses, args.skip)
    print(f"\n  编排状态已保存: {state_file}")

    if args.status:
        return

    # 找下一步
    next_phase = find_next_phase(statuses, args.skip)

    if next_phase is None:
        completed = sum(1 for s in statuses if s.completed or s.phase_id in args.skip)
        if completed == len(PHASES):
            print("\n  🎉 所有阶段已完成！")
        else:
            print("\n  ⚠️  存在未满足前置依赖的阶段，请检查。")
        return

    print(f"\n  📋 下一步: Phase {next_phase['id']} — {next_phase['name']}")
    print(f"  {next_phase['description']}")
    print()
    print(f"  {build_next_command(next_phase, statuses, args.project_id)}")
    print()


if __name__ == "__main__":
    main()
