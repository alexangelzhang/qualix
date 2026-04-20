"""Bootstrap Context：Phase 启动时预注入上下文，减少 Agent 自探索 LLM 调用.

生成 _bootstrap_context.md，包含：
1. 项目目录结构快照（2层深度）
2. 语言/框架检测结果
3. 上一 Phase 产出摘要（REQ/SE/GAP 数量 + 关键结论）
4. Blast Radius 摘要（如有）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

# 上一 Phase 的产出文件映射
_PREV_PHASE_STRUCTURED: dict[str, tuple[str, str]] = {
    "Q02": ("phaseA", "phase_a_structured.json"),
    "Q03": ("phaseA3", "phase_a3_structured.json"),
    "Q04": ("phaseA6", "phase_a6_structured.json"),
    "Q05": ("phaseA", "phase_a_structured.json"),
    "Q06": ("phaseB", "phase_b_structured.json"),
    "Q07": ("phaseA", "phase_a_structured.json"),
}


def _detect_language_framework(code_repo: str | None) -> str:
    if not code_repo:
        return "未提供代码仓库"
    repo = Path(code_repo)
    if not repo.exists():
        return "代码仓库路径不存在"

    indicators = []
    if (repo / "pom.xml").exists():
        indicators.append("Java (Maven)")
    if (repo / "build.gradle").exists() or (repo / "build.gradle.kts").exists():
        indicators.append("Java/Kotlin (Gradle)")
    if (repo / "package.json").exists():
        indicators.append("Node.js")
    if (repo / "pyproject.toml").exists() or (repo / "setup.py").exists():
        indicators.append("Python")
    if (repo / "go.mod").exists():
        indicators.append("Go")

    # DDD 特征
    for pattern in ["domain", "application", "infrastructure", "interfaces"]:
        if any(repo.rglob(pattern)):
            indicators.append("DDD 分层架构")
            break

    return "、".join(indicators) if indicators else "未识别"


def _dir_snapshot(path: Path, depth: int = 2, _current: int = 0) -> list[str]:
    """生成目录结构快照，忽略 .git / target / node_modules 等。"""
    IGNORE = {".git", "target", "node_modules", "__pycache__", ".idea", ".vscode", "build", "dist"}
    lines = []
    try:
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return lines
    for entry in entries[:30]:  # 每层最多 30 个
        if entry.name in IGNORE or entry.name.startswith("."):
            continue
        indent = "  " * _current
        if entry.is_dir():
            lines.append(f"{indent}📁 {entry.name}/")
            if _current < depth - 1:
                lines.extend(_dir_snapshot(entry, depth, _current + 1))
        else:
            lines.append(f"{indent}📄 {entry.name}")
    return lines


def _summarize_prev_phase(output_dir: Path, project_id: str, phase_id: str) -> str:
    prev = _PREV_PHASE_STRUCTURED.get(phase_id)
    if not prev:
        return ""
    dir_suffix, filename = prev
    path = output_dir / project_id / dir_suffix / filename
    data = load_json(path)
    if not data:
        return ""

    lines = [f"### 上一 Phase 产出摘要（来自 {filename}）"]
    stats = data.get("statistics", {})
    if stats:
        for k, v in stats.items():
            lines.append(f"- {k}: {v}")

    reqs = data.get("requirements", [])
    ses = data.get("semantic_expectations", [])
    gaps = data.get("gaps", [])
    issues = data.get("issues", [])

    if reqs:
        lines.append(f"- 需求点(REQ): {len(reqs)} 条")
    if ses:
        lines.append(f"- 关键语义(SE): {len(ses)} 条")
        for se in ses[:5]:
            lines.append(f"  - {se.get('se_id', se.get('id', ''))} {se.get('description', '')[:60]}")
        if len(ses) > 5:
            lines.append(f"  - ...共 {len(ses)} 条")
    if gaps:
        lines.append(f"- 缺口(GAP): {len(gaps)} 条")
    if issues:
        critical = [i for i in issues if i.get("severity") in ("CRITICAL", "BLOCKER")]
        lines.append(f"- 质量问题: {len(issues)} 条（严重: {len(critical)}）")

    return "\n".join(lines)


def _summarize_blast_radius(output_dir: Path, project_id: str, phase_id: str) -> str:
    from dqg.constants import PHASE_DIR_MAP
    dir_suffix = PHASE_DIR_MAP.get(phase_id, "")
    if not dir_suffix:
        return ""
    path = output_dir / project_id / dir_suffix / "_internal" / "_blast_radius.json"
    data = load_json(path)
    if not data:
        return ""

    lines = ["### Blast Radius 分析"]
    changed = data.get("changed_files", [])
    affected = data.get("affected_classes", [])
    risk = data.get("risk_level", "")
    if changed:
        lines.append(f"- 变更文件: {len(changed)} 个")
        for f in changed[:5]:
            lines.append(f"  - {f}")
    if affected:
        lines.append(f"- 影响类: {len(affected)} 个")
    if risk:
        lines.append(f"- 风险等级: {risk}")
    return "\n".join(lines)


def write_bootstrap_context(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    code_repo: str | None = None,
) -> Path | None:
    """生成并写入 _bootstrap_context.md，返回文件路径。"""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.phase_registry import PHASE_DEFS

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return None

    dir_suffix = PHASE_DIR_MAP.get(phase_id, phase_def.get("dir_suffix", ""))
    internal_dir = output_dir / project_id / dir_suffix / "_internal"
    internal_dir.mkdir(parents=True, exist_ok=True)

    sections: list[str] = [
        f"# Bootstrap Context — Phase {phase_id}: {phase_def.get('name', '')}",
        "",
        "> 本文件由 DQG 自动生成，提供 Phase 启动所需的项目上下文，无需 Agent 自行探索。",
        "",
    ]

    # 1. 语言/框架
    sections += [
        "## 技术栈",
        f"- 检测结果: {_detect_language_framework(code_repo)}",
        "",
    ]

    # 2. 代码仓库目录结构
    if code_repo and Path(code_repo).exists():
        snapshot = _dir_snapshot(Path(code_repo), depth=2)
        if snapshot:
            sections += ["## 代码仓库结构（2层）", "```"] + snapshot[:60] + ["```", ""]

    # 3. 上一 Phase 产出摘要
    prev_summary = _summarize_prev_phase(output_dir, project_id, phase_id)
    if prev_summary:
        sections += [prev_summary, ""]

    # 4. Blast Radius
    blast_summary = _summarize_blast_radius(output_dir, project_id, phase_id)
    if blast_summary:
        sections += [blast_summary, ""]

    content = "\n".join(sections)
    path = internal_dir / "_bootstrap_context.md"
    path.write_text(content, encoding="utf-8")
    log.info("Bootstrap context written: %s (%d chars)", path, len(content))
    return path
