"""覆盖率门禁：解析 JaCoCo XML 报告，finalize 时硬性校验覆盖率阈值.

支持 JaCoCo XML 格式（Java 项目标准覆盖率工具）。
Phase C finalize 时自动检查 line/branch 覆盖率是否达标。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from qualix.json_utils import load_json
from qualix.log import get_logger

log = get_logger(__name__)

# 默认覆盖率阈值
DEFAULT_LINE_THRESHOLD = 1.0  # 公司硬性指标：增量行覆盖率必须 100%
DEFAULT_BRANCH_THRESHOLD = 1.0  # 公司硬性指标：增量分支覆盖率必须 100%


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


def parse_jacoco_per_line(report_path: Path) -> dict[str, dict[int, dict[str, int]]] | None:
    """解析 JaCoCo XML，提取每个 sourcefile 的逐行覆盖数据.

    Returns:
        {"com/example/MyClass.java": {265: {"ci": 1, "mi": 0, "cb": 1, "mb": 0}, ...}}
    只包含可执行行（ci+mi>0 或 cb+mb>0）。
    cb/mb 为该行的分支覆盖数（JaCoCo <line cb="N" mb="N"/>）。
    """
    if not report_path.exists():
        return None
    try:
        tree = ET.parse(report_path)
    except ET.ParseError as exc:
        log.warning("Failed to parse JaCoCo XML for line data %s: %s", report_path, exc)
        return None
    root = tree.getroot()
    result: dict[str, dict[int, dict[str, int]]] = {}
    for package in root.findall(".//package"):
        pkg_name = package.get("name", "")
        for sourcefile in package.findall("sourcefile"):
            sf_name = sourcefile.get("name", "")
            qualified = f"{pkg_name}/{sf_name}" if pkg_name else sf_name
            lines: dict[int, dict[str, int]] = {}
            for line in sourcefile.findall("line"):
                nr = int(line.get("nr", 0))
                ci = int(line.get("ci", 0))
                mi = int(line.get("mi", 0))
                cb = int(line.get("cb", 0))
                mb = int(line.get("mb", 0))
                if ci > 0 or mi > 0 or cb > 0 or mb > 0:
                    lines[nr] = {"ci": ci, "mi": mi, "cb": cb, "mb": mb}
            if lines:
                result[qualified] = lines
    return result if result else None


def parse_git_diff_changed_lines(repo_path: Path, base_ref: str = "origin/master") -> dict[str, set[int]]:
    """通过 git diff 获取本次改动中每个 Java 源文件的变更行号集合.

    Returns:
        {"com/mi/maf/srv/Foo.java": {265, 266, ...}}
    只包含新增/修改的行（+行），不含删除行。
    """
    import re
    import subprocess

    result: dict[str, set[int]] = {}
    try:
        proc = subprocess.run(
            ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", "*.java"],
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=30,
        )
        if not proc.stdout:
            return result
    except Exception as exc:
        log.debug("git diff failed in %s: %s", repo_path, exc)
        return result

    current_file: str | None = None
    for raw_line in proc.stdout.splitlines():
        if raw_line.startswith("+++ b/"):
            path = raw_line[6:]
            parts = path.split("/")
            for i, p in enumerate(parts):
                if p in ("java", "kotlin", "scala"):
                    current_file = "/".join(parts[i + 1 :])
                    result.setdefault(current_file, set())
                    break
            else:
                current_file = None
        elif raw_line.startswith("@@ ") and current_file is not None:
            m = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) is not None else 1
                for nr in range(start, start + count):
                    result[current_file].add(nr)
    return result


def compute_incremental_coverage_linelevel(
    per_line: dict[str, dict[int, dict[str, int]]],
    diff_lines: dict[str, set[int]],
    blast_radius: dict[str, Any],
) -> dict[str, Any]:
    """行级增量覆盖率：只统计 git diff 变更行的覆盖情况.

    分母 = diff 中的可执行变更行数（ci+mi>0 的行）
    分子 = 其中 ci>0 的行数

    Returns 与 compute_incremental_coverage 结构兼容，result["mode"]="line_level" 标识来源。
    """
    affected_sources: set[str] = set()
    for f in blast_radius.get("changed_files", []):
        parts = f.split("/")
        for i, p in enumerate(parts):
            if p in ("java", "kotlin", "scala"):
                affected_sources.add("/".join(parts[i + 1 :]))
                break
        else:
            affected_sources.add(parts[-1])

    line_covered = 0
    line_missed = 0
    branch_covered = 0
    branch_missed = 0
    matched: list[str] = []

    for qualified, line_data in per_line.items():
        filename = qualified.rsplit("/", 1)[-1]
        is_affected = (
            qualified in affected_sources
            or filename in affected_sources
            or any(qualified.endswith(s) for s in affected_sources if "/" in s)
        )
        if not is_affected:
            continue

        diff_key: str | None = None
        for dk in diff_lines:
            dk_fn = dk.rsplit("/", 1)[-1]
            if dk_fn == filename or qualified.endswith(dk) or dk.endswith(qualified):
                diff_key = dk
                break
        if diff_key is None:
            continue

        changed_nrs = diff_lines[diff_key]
        fc = fm = 0
        bc = bm = 0
        for nr, ctr in line_data.items():
            if nr in changed_nrs:
                if ctr["ci"] > 0:
                    fc += 1
                else:
                    fm += 1
                # branch data per line (cb/mb from JaCoCo <line cb="N" mb="N"/>)
                bc += ctr.get("cb", 0)
                bm += ctr.get("mb", 0)
        if fc + fm > 0:
            matched.append(qualified)
            line_covered += fc
            line_missed += fm
            branch_covered += bc
            branch_missed += bm

    line_total = line_covered + line_missed
    branch_total = branch_covered + branch_missed
    return {
        "incremental": {
            "line": {
                "covered": line_covered,
                "missed": line_missed,
                "total": line_total,
                "rate": round(line_covered / line_total, 4) if line_total > 0 else 0.0,
            },
            "branch": {
                "covered": branch_covered,
                "missed": branch_missed,
                "total": branch_total,
                "rate": round(branch_covered / branch_total, 4) if branch_total > 0 else 0.0,
            },
        },
        "matched_files": matched,
        "unmatched_files_count": 0,
        "mode": "line_level",
    }


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


def parse_istanbul_json(report_path: Path) -> dict[str, Any] | None:
    """解析 Istanbul/c8 的 coverage-summary.json，转为与 parse_jacoco_xml 一致的结构.

    Istanbul 格式:
    {"total": {"lines": {"total": 100, "covered": 80, "pct": 80}, "branches": {...}, ...}}
    """
    if not report_path.exists():
        return None
    data = load_json(report_path)
    if not isinstance(data, dict):
        log.warning("Failed to parse Istanbul JSON %s: not a dict", report_path)
        return None

    total = data.get("total", {})
    if not total:
        return None

    def _section(key: str) -> dict[str, Any]:
        s = total.get(key, {})
        pct = s.get("pct")
        covered = s.get("covered", 0)
        tot = s.get("total", 0)
        rate = round(float(pct) / 100.0, 4) if pct is not None else (round(covered / tot, 4) if tot else 0.0)
        return {"covered": covered, "missed": tot - covered, "total": tot, "rate": rate}

    return {
        "line": _section("lines"),
        "branch": _section("branches"),
        "instruction": _section("statements"),
        "method": _section("functions"),
    }


def find_coverage_report(code_repo: Path) -> Path | None:
    """在代码仓库中查找覆盖率报告（JaCoCo XML 或 Istanbul JSON）."""
    jacoco_candidates = [
        "target/site/jacoco/jacoco.xml",
        "target/jacoco.xml",
        "build/reports/jacoco/test/jacocoTestReport.xml",
        "build/reports/jacoco/jacocoTestReport.xml",
    ]
    for candidate in jacoco_candidates:
        path = code_repo / candidate
        if path.exists():
            return path

    istanbul_candidates = [
        "coverage/coverage-summary.json",
        "coverage-summary.json",
        ".nyc_output/coverage-summary.json",
    ]
    for candidate in istanbul_candidates:
        path = code_repo / candidate
        if path.exists():
            return path

    for xml_path in code_repo.rglob("jacoco*.xml"):
        if xml_path.stat().st_size > 100:
            return xml_path

    return None


# 向后兼容别名
find_jacoco_report = find_coverage_report


def check_phase_c_coverage(
    output_dir: Path,
    project_id: str,
    code_repo: str | None = None,
    coverage_report: str | None = None,
) -> list[str]:
    """Phase C finalize 时的覆盖率门禁.

    优先尝试增量模式（仅检查 blast radius 内文件），fallback 到全量模式。

    Args:
        output_dir: Qualix 输出目录
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
        report_path = find_coverage_report(repo_path)

    if not report_path:
        return []  # 无覆盖率报告，跳过检查（不阻断）

    # 按文件类型路由解析器
    if report_path.suffix == ".json":
        coverage = parse_istanbul_json(report_path)
    else:
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

    # 尝试增量覆盖率分析（优先行级，fallback 文件级）
    incremental_result = _try_incremental_coverage(output_dir, project_id, report_path, code_repo=code_repo)
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
        # 增量覆盖率低于阈值时 BLOCKED（本次改动的文件/行必须达标）
        mode = incremental_result.get("mode", "file_level")
        mode_label = "（行级增量）" if mode == "line_level" else f"（blast radius 内 {len(matched)} 文件）"
        if inc_line < DEFAULT_LINE_THRESHOLD and matched:
            errors.append(f"BLOCKED: 增量行覆盖率 {inc_line:.1%}{mode_label}低于阈值 {DEFAULT_LINE_THRESHOLD:.0%}")
        if inc_branch < DEFAULT_BRANCH_THRESHOLD and matched:
            errors.append(
                f"BLOCKED: 增量分支覆盖率 {inc_branch:.1%}{mode_label}低于阈值 {DEFAULT_BRANCH_THRESHOLD:.0%}"
            )
        # 写入增量结果供 verification_bundle 消费
        _write_incremental_result(output_dir, project_id, incremental_result)

    return errors


def _try_incremental_coverage(
    output_dir: Path,
    project_id: str,
    report_path: Path,
    code_repo: str | None = None,
) -> dict[str, Any] | None:
    """尝试加载 blast_radius 并计算增量覆盖率.

    优先使用行级增量（git diff 变更行 × JaCoCo 行级数据），
    若无法获取 diff 数据则 fallback 到文件级增量。
    """
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import load_json

    dir_suffix = PHASE_DIR_MAP.get("Q06", "phaseC")
    blast_path = output_dir / project_id / dir_suffix / "_internal" / "_blast_radius.json"
    if not blast_path.exists():
        return None

    blast_data = load_json(blast_path)
    if not blast_data or not blast_data.get("changed_files"):
        return None

    # 优先尝试行级增量
    if code_repo:
        repo_path = Path(code_repo).expanduser().resolve()
        if repo_path.is_dir():
            diff_lines = parse_git_diff_changed_lines(repo_path)
            if diff_lines:
                per_line = parse_jacoco_per_line(report_path)
                if per_line:
                    result = compute_incremental_coverage_linelevel(per_line, diff_lines, blast_data)
                    if result["incremental"]["line"]["total"] > 0:
                        log.info(
                            "Coverage (line-level incremental, %d changed lines): line=%.1f%%",
                            result["incremental"]["line"]["total"],
                            result["incremental"]["line"]["rate"] * 100,
                        )
                        return result

    # Fallback: 文件级增量
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
    from qualix.constants import PHASE_DIR_MAP
    from qualix.json_utils import save_json

    dir_suffix = PHASE_DIR_MAP.get("Q06", "phaseC")
    int_dir = output_dir / project_id / dir_suffix / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)
    save_json(int_dir / "_incremental_coverage.json", result)
