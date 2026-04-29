"""覆盖率门禁：解析 JaCoCo XML 报告，finalize 时硬性校验覆盖率阈值.

支持 JaCoCo XML 格式（Java 项目标准覆盖率工具）。
Phase C finalize 时自动检查 line/branch 覆盖率是否达标。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# 默认覆盖率阈值
DEFAULT_LINE_THRESHOLD = 0.80
DEFAULT_BRANCH_THRESHOLD = 0.80


def parse_jacoco_xml(report_path: Path) -> dict[str, Any] | None:
    """解析 JaCoCo XML 报告，提取覆盖率数据.

    Returns:
        {
            "line": {"covered": N, "missed": M, "rate": float},
            "branch": {"covered": N, "missed": M, "rate": float},
            "instruction": {"covered": N, "missed": M, "rate": float},
            "method": {"covered": N, "missed": M, "rate": float},
            "class": {"covered": N, "missed": M, "rate": float},
        }
    """
    if not report_path.exists():
        return None

    try:
        tree = ET.parse(report_path)
    except ET.ParseError as exc:
        log.warning("Failed to parse JaCoCo XML %s: %s", report_path, exc)
        return None

    root = tree.getroot()
    result: dict[str, Any] = {}

    # JaCoCo XML 的顶层 <counter> 元素包含汇总数据
    for counter in root.findall("counter"):
        counter_type = counter.get("type", "").lower()
        covered = int(counter.get("covered", "0"))
        missed = int(counter.get("missed", "0"))
        total = covered + missed
        rate = covered / total if total > 0 else 0.0
        result[counter_type] = {
            "covered": covered,
            "missed": missed,
            "total": total,
            "rate": round(rate, 4),
        }

    if not result:
        # 尝试从 package 级别聚合
        for counter in root.iter("counter"):
            counter_type = counter.get("type", "").lower()
            if counter_type not in result:
                result[counter_type] = {"covered": 0, "missed": 0, "total": 0, "rate": 0.0}
            result[counter_type]["covered"] += int(counter.get("covered", "0"))
            result[counter_type]["missed"] += int(counter.get("missed", "0"))

        for data in result.values():
            data["total"] = data["covered"] + data["missed"]
            data["rate"] = round(data["covered"] / data["total"], 4) if data["total"] > 0 else 0.0

    return result if result else None


def check_coverage_gate(
    coverage: dict[str, Any],
    line_threshold: float = DEFAULT_LINE_THRESHOLD,
    branch_threshold: float = DEFAULT_BRANCH_THRESHOLD,
) -> list[str]:
    """检查覆盖率是否达标.

    Returns:
        错误列表。BLOCKED 前缀的错误会阻断 finalize。
    """
    errors: list[str] = []

    line_data = coverage.get("line", {})
    line_rate = line_data.get("rate", 0.0)
    if line_rate < line_threshold:
        errors.append(
            f"BLOCKED: 行覆盖率 {line_rate:.1%} 低于阈值 {line_threshold:.0%}"
            f"（covered={line_data.get('covered', 0)}, missed={line_data.get('missed', 0)}）"
        )

    branch_data = coverage.get("branch", {})
    branch_rate = branch_data.get("rate", 0.0)
    if branch_rate < branch_threshold:
        errors.append(
            f"BLOCKED: 分支覆盖率 {branch_rate:.1%} 低于阈值 {branch_threshold:.0%}"
            f"（covered={branch_data.get('covered', 0)}, missed={branch_data.get('missed', 0)}）"
        )

    return errors


def parse_jacoco_per_file(report_path: Path) -> dict[str, dict[str, Any]] | None:
    """解析 JaCoCo XML，提取每个 sourcefile 的覆盖率数据.

    Returns:
        {
            "com/example/MyClass.java": {
                "line": {"covered": N, "missed": M, "rate": float},
                "branch": {"covered": N, "missed": M, "rate": float},
                ...
            }
        }
    """
    if not report_path.exists():
        return None

    try:
        tree = ET.parse(report_path)
    except ET.ParseError as exc:
        log.warning("Failed to parse JaCoCo XML %s: %s", report_path, exc)
        return None

    root = tree.getroot()
    result: dict[str, dict[str, Any]] = {}

    for package in root.findall(".//package"):
        pkg_name = package.get("name", "")
        for sourcefile in package.findall("sourcefile"):
            sf_name = sourcefile.get("name", "")
            qualified = f"{pkg_name}/{sf_name}" if pkg_name else sf_name
            counters: dict[str, Any] = {}
            for counter in sourcefile.findall("counter"):
                counter_type = counter.get("type", "").lower()
                covered = int(counter.get("covered", "0"))
                missed = int(counter.get("missed", "0"))
                total = covered + missed
                rate = covered / total if total > 0 else 0.0
                counters[counter_type] = {
                    "covered": covered,
                    "missed": missed,
                    "total": total,
                    "rate": round(rate, 4),
                }
            if counters:
                result[qualified] = counters

    return result if result else None


def compute_incremental_coverage(
    per_file: dict[str, dict[str, Any]],
    blast_radius: dict[str, Any],
) -> dict[str, Any]:
    """基于 blast radius 计算增量覆盖率.

    只对 blast radius 内的文件（changed + affected callers 所在文件）计算覆盖率，
    其余文件继承全量结果。

    Returns:
        {
            "incremental": {"line": {...}, "branch": {...}},
            "matched_files": [...],
            "unmatched_files": [...],
        }
    """
    # 从 blast radius 提取受影响的文件名（不含路径前缀）
    affected_sources: set[str] = set()
    for f in blast_radius.get("changed_files", []):
        # "src/main/java/com/example/Foo.java" → "com/example/Foo.java"
        parts = f.split("/")
        # 找到 java 源码根目录后的部分
        for i, p in enumerate(parts):
            if p in ("java", "kotlin", "scala"):
                affected_sources.add("/".join(parts[i + 1 :]))
                break
        else:
            # fallback: 用文件名匹配
            affected_sources.add(parts[-1])

    # 从 affected_callers/affected_tests 提取类名
    for method_ref in (
        *blast_radius.get("affected_callers", []),
        *blast_radius.get("affected_tests", []),
    ):
        class_name = method_ref.split(".")[0] if "." in method_ref else method_ref
        affected_sources.add(f"{class_name}.java")

    # blast radius 中的测试文件名（用于 mock shadow 检测）
    test_basenames: set[str] = set()
    for f in blast_radius.get("changed_files", []):
        basename = f.rsplit("/", 1)[-1]
        if "Test" in basename and basename.endswith(".java"):
            test_basenames.add(basename)

    # 匹配 JaCoCo sourcefile
    matched: list[str] = []
    mock_shadowed: list[str] = []
    unmatched: list[str] = []
    agg: dict[str, dict[str, int]] = {}

    for qualified, counters in per_file.items():
        # qualified = "com/example/Foo.java"
        filename = qualified.rsplit("/", 1)[-1]
        is_affected = (
            qualified in affected_sources
            or filename in affected_sources
            or any(qualified.endswith(s) for s in affected_sources if "/" in s)
        )
        if is_affected:
            # mock shadow 检测：JaCoCo 全 0 且有对应测试文件
            if _is_mock_shadowed(filename, counters, test_basenames):
                mock_shadowed.append(qualified)
                continue
            matched.append(qualified)
            for counter_type, data in counters.items():
                if counter_type not in agg:
                    agg[counter_type] = {"covered": 0, "missed": 0}
                agg[counter_type]["covered"] += data["covered"]
                agg[counter_type]["missed"] += data["missed"]
        else:
            unmatched.append(qualified)

    incremental: dict[str, Any] = {}
    for counter_type, data in agg.items():
        total = data["covered"] + data["missed"]
        incremental[counter_type] = {
            "covered": data["covered"],
            "missed": data["missed"],
            "total": total,
            "rate": round(data["covered"] / total, 4) if total > 0 else 0.0,
        }

    result: dict[str, Any] = {
        "incremental": incremental,
        "matched_files": matched,
        "unmatched_files_count": len(unmatched),
    }
    if mock_shadowed:
        result["mock_shadowed_files"] = mock_shadowed
    return result


def _is_mock_shadowed(
    filename: str,
    counters: dict[str, Any],
    test_basenames: set[str],
) -> bool:
    """检测 Mockito CALLS_REAL_METHODS 导致的 JaCoCo 覆盖率假阴性.

    条件：JaCoCo 所有计数器 covered=0 且 blast radius 中存在对应测试文件。
    """
    all_zero = all(c.get("covered", 0) == 0 for c in counters.values())
    if not all_zero:
        return False
    class_name = filename.removesuffix(".java")
    return any(t.startswith(class_name) and "Test" in t for t in test_basenames)


def find_jacoco_report(code_repo: Path) -> Path | None:
    """在代码仓库中查找 JaCoCo XML 报告.

    常见路径：
    - target/site/jacoco/jacoco.xml (Maven)
    - build/reports/jacoco/test/jacocoTestReport.xml (Gradle)
    """
    candidates = [
        "target/site/jacoco/jacoco.xml",
        "target/jacoco.xml",
        "build/reports/jacoco/test/jacocoTestReport.xml",
        "build/reports/jacoco/jacocoTestReport.xml",
    ]
    for candidate in candidates:
        path = code_repo / candidate
        if path.exists():
            return path

    # 递归搜索（最多 3 层）
    for xml_path in code_repo.rglob("jacoco*.xml"):
        if xml_path.stat().st_size > 100:  # 排除空文件
            return xml_path

    return None


def check_phase_c_coverage(
    output_dir: Path,
    project_id: str,
    code_repo: str | None = None,
    coverage_report: str | None = None,
) -> list[str]:
    """Phase C finalize 时的覆盖率门禁.

    优先尝试增量模式（仅检查 blast radius 内文件），fallback 到全量模式。

    Args:
        output_dir: DQG 输出目录
        project_id: 项目 ID
        code_repo: 代码仓库路径
        coverage_report: 覆盖率报告路径（优先使用）

    Returns:
        错误列表。
    """
    report_path: Path | None = None

    if coverage_report:
        report_path = Path(coverage_report).expanduser().resolve()
        if not report_path.exists():
            return [f"WARNING: 指定的覆盖率报告不存在: {report_path}"]
    elif code_repo:
        repo_path = Path(code_repo).expanduser().resolve()
        report_path = find_jacoco_report(repo_path)

    if not report_path:
        return []  # 无覆盖率报告，跳过检查（不阻断）

    coverage = parse_jacoco_xml(report_path)
    if not coverage:
        return [f"WARNING: 无法解析覆盖率报告: {report_path}"]

    log.info(
        "Coverage (full): line=%.1f%% branch=%.1f%% (from %s)",
        coverage.get("line", {}).get("rate", 0) * 100,
        coverage.get("branch", {}).get("rate", 0) * 100,
        report_path,
    )

    # 全量覆盖率仅做 WARNING（不 BLOCK，整仓库覆盖率不是本次改动的责任）
    errors: list[str] = []
    full_errors = check_coverage_gate(coverage)
    for e in full_errors:
        errors.append(e.replace("BLOCKED:", "WARNING:"))

    # 尝试增量覆盖率分析
    incremental_result = _try_incremental_coverage(output_dir, project_id, report_path)
    if incremental_result:
        inc = incremental_result["incremental"]
        inc_line = inc.get("line", {}).get("rate", 0)
        inc_branch = inc.get("branch", {}).get("rate", 0)
        matched = incremental_result["matched_files"]
        log.info(
            "Coverage (incremental, %d files): line=%.1f%% branch=%.1f%%",
            len(matched),
            inc_line * 100,
            inc_branch * 100,
        )
        # 增量覆盖率低于阈值时 BLOCKED（本次改动的文件必须达标）
        if inc_line < DEFAULT_LINE_THRESHOLD and matched:
            errors.append(
                f"BLOCKED: 增量行覆盖率 {inc_line:.1%}（blast radius 内 {len(matched)} 文件）"
                f"低于阈值 {DEFAULT_LINE_THRESHOLD:.0%}"
            )
        if inc_branch < DEFAULT_BRANCH_THRESHOLD and matched:
            errors.append(
                f"BLOCKED: 增量分支覆盖率 {inc_branch:.1%}（blast radius 内 {len(matched)} 文件）"
                f"低于阈值 {DEFAULT_BRANCH_THRESHOLD:.0%}"
            )
        # 写入增量结果供 verification_bundle 消费
        _write_incremental_result(output_dir, project_id, incremental_result)

    return errors


def _try_incremental_coverage(
    output_dir: Path,
    project_id: str,
    report_path: Path,
) -> dict[str, Any] | None:
    """尝试加载 blast_radius 并计算增量覆盖率."""
    from dqg.constants import PHASE_DIR_MAP

    dir_suffix = PHASE_DIR_MAP.get("Q06", "phaseC")
    blast_path = output_dir / project_id / dir_suffix / "_internal" / "_blast_radius.json"
    if not blast_path.exists():
        return None

    from dqg.json_utils import load_json

    blast_data = load_json(blast_path)
    if not blast_data or not blast_data.get("changed_files"):
        return None

    per_file = parse_jacoco_per_file(report_path)
    if not per_file:
        return None

    return compute_incremental_coverage(per_file, blast_data)


def _write_incremental_result(
    output_dir: Path,
    project_id: str,
    result: dict[str, Any],
) -> None:
    """写入增量覆盖率结果到 _internal 目录."""
    from dqg.constants import PHASE_DIR_MAP
    from dqg.json_utils import save_json

    dir_suffix = PHASE_DIR_MAP.get("Q06", "phaseC")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)
    save_json(int_dir / "_incremental_coverage.json", result)
