"""Q05 覆盖率/目标模块/追溯 gate 检查."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
from dqg.log import get_logger

log = get_logger(__name__)

from ._checks_eut_basic import _IMPORT_CLASS_PATTERN, _INJECT_MOCKS_PATTERN
from ._checks_production import _IMPL_SUFFIXES, _SKIP_CLASS_PATTERNS, _SKIP_MODULE_PREFIXES
from ._collect import _collect_git_diff_basenames

_BACKEND_KWS: frozenset[str] = frozenset(
    {
        "接口",
        "Service",
        "数据库",
        "缓存",
        "校验",
        "验证",
        "validate",
        "domain",
        "Manager",
        "Mapper",
        "Gateway",
        "Repository",
        "save",
        "insert",
        "update",
        "delete",
        "query",
        "select",
        "事务",
        "transaction",
    }
)
_FRONTEND_EXCUSES: frozenset[str] = frozenset(
    {"前端逻辑", "前端", "UI", "BPM", "页面", "展示", "界面", "H5", "小程序", "配置项", "不在代码范围"}
)


def _check_target_modules_json(
    output_dir: Path,
    project_id: str,
    phase_def: dict,
    code_repos: list[str],
    test_files: list[Path],
    q01_data: dict | None,
) -> list[str]:
    """Step 0.5 核心 gate：三层驱动产物必须存在、完整、与测试代码交叉验证.

    三层防御：
    1. 基础：文件存在且覆盖全部 SE
    2. 中层：git_diff_files 非空（证明执行了 git diff）
    3. 深层：se_mappings 里的 impl_class 必须出现在新增测试文件中（交叉验证）
    """
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    target_path = int_dir / "_q05_target_modules.json"

    if not target_path.exists():
        return [
            "BLOCKED: Q05 missing_target_modules — "
            "_internal/_q05_target_modules.json 不存在。"
            "SKILL.md Step 0.5e 要求：三层驱动（REQ/BR→类 + SE→类 + git diff）完成后"
            "必须输出此文件，否则无法证明 Step 0.5 被真正执行。"
        ]

    data = load_json(target_path)
    if not data or not isinstance(data, dict):
        return ["BLOCKED: Q05 target_modules_empty — _q05_target_modules.json 为空或格式错误"]

    errors: list[str] = []

    # ── 层 1：SE 覆盖完整性 ─────────────────────────────────────────────────
    if q01_data:
        all_se_ids = {s["se_id"] for s in q01_data.get("semantic_expectations", [])}
        se_mappings = data.get("se_mappings", [])
        mapped_se_ids = {m.get("se_id", "") for m in se_mappings if isinstance(m, dict)}
        missing_se = sorted(all_se_ids - mapped_se_ids)
        if missing_se:
            errors.append(
                f"BLOCKED: Q05 target_modules_incomplete — "
                f"_q05_target_modules.json 缺少以下 SE 的类映射: {', '.join(missing_se)}。"
                "请在 Step 0.5b 中为每条 SE 搜索对应实现类（未找到填 found=false + gap_reason）。"
            )

    # ── 层 1b：BR 覆盖完整性 ─────────────────────────────────────────────────
    if q01_data:
        all_br_ids = {
            r["req_id"]
            for r in q01_data.get("requirements", [])
            if isinstance(r, dict) and r.get("req_id", "").startswith("BR-")
        }
        br_mappings = data.get("br_mappings", [])
        mapped_br_ids = {m.get("br_id", "") for m in br_mappings if isinstance(m, dict)}
        missing_br = sorted(all_br_ids - mapped_br_ids)
        if missing_br:
            errors.append(
                f"BLOCKED: Q05 target_modules_br_incomplete — "
                f"_q05_target_modules.json 缺少以下 BR 的类映射: {', '.join(missing_br)}。"
                "请在 Step 0.5a 中为每条 BR 搜索对应实现类（未找到填 found=false + gap_reason）。"
            )

    # ── 层 2：git_diff_files 非空（证明执行了 git diff） ─────────────────────
    diff_files = data.get("git_diff_files", [])
    if not diff_files and code_repos:
        errors.append(
            "BLOCKED: Q05 target_modules_no_diff — "
            "_q05_target_modules.json 的 git_diff_files 为空，"
            "说明 Step 0.5c 未执行 git diff。请执行 git diff --name-only 获取变更文件列表。"
        )

    # ── 层 3：交叉验证——impl_class 必须出现在新增测试文件中 ──────────────────
    se_mappings = data.get("se_mappings", [])
    found_classes = {
        m["impl_class"] for m in se_mappings if isinstance(m, dict) and m.get("found") and m.get("impl_class")
    }
    if found_classes and test_files:
        # 收集所有新增测试文件里出现的类名（@InjectMocks + import）
        tested_classes: set[str] = set()
        for path in test_files:
            if path.suffix != ".java":
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                tested_classes.update(m.group(1) for m in _INJECT_MOCKS_PATTERN.finditer(text))
                tested_classes.update(m.group(1) for m in _IMPORT_CLASS_PATTERN.finditer(text))
            except OSError:
                continue

        # 在映射里声明了 found=true 但测试文件里完全没有用到的类
        not_tested = sorted(found_classes - tested_classes)
        if not_tested and len(not_tested) / max(len(found_classes), 1) > 0.5:
            errors.append(
                f"WARNING: Q05 target_modules_not_tested — "
                f"se_mappings 声明的 {len(not_tested)}/{len(found_classes)} 个实现类"
                f"未出现在新增测试文件的 @InjectMocks/import 中: {', '.join(not_tested[:5])}。"
                "可能是 Step 0.5 的映射表与实际生成的测试代码不一致（映射了但未写测试）。"
            )

    return errors


def _check_uncovered_br_reasons(
    output_dir: Path,
    project_id: str,
    phase_def: dict,
    q01_data: dict | None,
) -> list[str]:
    """uncovered BR 理由合理性：reason 含"前端"但 BR 描述含后端语义 → WARNING."""
    if not q01_data:
        return []

    # 查找设计矩阵
    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    matrix = None
    for candidate in [pd / "_test_design_matrix.json", int_dir / "_test_design_matrix.json"]:
        matrix = load_json(candidate) if candidate.exists() else None
        if matrix:
            break
    if not matrix:
        return []

    br_descs = {
        r["req_id"]: r.get("description", "")
        for r in q01_data.get("requirements", [])
        if str(r.get("req_id", "")).startswith("BR")
    }
    req_coverage = matrix.get("req_coverage", [])
    suspicious: list[str] = []

    for entry in req_coverage:
        if not isinstance(entry, dict):
            continue
        uncovered_brs = entry.get("uncovered_brs", []) or []
        reasons = entry.get("uncovered_reasons", []) or []
        if not uncovered_brs:
            continue
        reason_text = " ".join(str(r) for r in reasons)
        is_frontend_excuse = any(kw in reason_text for kw in _FRONTEND_EXCUSES)
        if not is_frontend_excuse:
            continue
        for br_id in uncovered_brs:
            desc = br_descs.get(br_id, "")
            if any(kw in desc for kw in _BACKEND_KWS):
                suspicious.append(f"{br_id}（reason='{reason_text[:30]}'）")

    if suspicious:
        return [
            f"WARNING: Q05 uncovered_reason_mismatch — "
            f"{len(suspicious)} 个 BR 标注为前端/配置原因，但描述含后端语义（Service/接口/数据库等），"
            f"疑似错误排除: {', '.join(suspicious[:4])}。"
            "请确认这些 BR 确实无后端实现，否则应生成对应单测。"
        ]
    return []


def _check_branch_file_reality(
    output_dir: Path,
    project_id: str,
    phase_def: dict[str, Any],
    code_repos: list[str],
) -> list[str]:
    """Fix-6: 设计矩阵 code_branch_coverage[].file 必须在 git diff 变更文件里.

    防止 LLM 在设计矩阵里虚构不存在的文件名。
    """
    int_dir = _internal_dir(output_dir, project_id, phase_def)
    matrix_path = (
        int_dir / "_test_design_matrix.json"
        if (int_dir / "_test_design_matrix.json").exists()
        else (_phase_dir(output_dir, project_id, phase_def) / "_test_design_matrix.json")
    )
    matrix = load_json(matrix_path) if matrix_path.exists() else None
    if not matrix:
        return []

    branch_coverage = matrix.get("code_branch_coverage", [])
    if not branch_coverage or not code_repos:
        return []

    diff_basenames = _collect_git_diff_basenames(code_repos)
    if not diff_basenames:
        return []  # git diff 失败，不误报

    ghost_files: list[str] = []
    for entry in branch_coverage:
        if not isinstance(entry, dict):
            continue
        fname = str(entry.get("file", "") or "")
        if not fname:
            continue
        basename = Path(fname).name
        if basename and basename not in diff_basenames:
            ghost_files.append(basename)

    if ghost_files:
        unique_ghosts = sorted(set(ghost_files))
        return [
            f"WARNING: Q05 ghost_branch_file — 设计矩阵 code_branch_coverage 中 {len(unique_ghosts)} 个文件"
            f"不在 git diff 变更列表里，疑似虚构：{', '.join(unique_ghosts[:5])}。"
            "请确认分支清单对应的文件是本次实际变更的文件。"
        ]
    return []


def _check_q05_git_diff_coverage(
    data: dict[str, Any],
    target_modules_data: dict[str, Any] | None,
) -> list[str]:
    """C10: git diff 变更的实现类必须有对应 EUT when/given 字段引用.

    实现 SKILL.md Step 0.5 中文档化但未落地的 gate：
    'feature branch 新增/修改的每个 Java 类，必须在某条 EUT 的 when 字段里出现'

    只检查实现类（Service/Manager/Ext/Consumer/Impl 等后缀），
    排除接口定义模块、常量包、DTO/VO/Builder 等无业务逻辑类。
    级别：WARNING（允许 finalize，但标记盲区供开发者补充 EUT）
    """
    if not target_modules_data:
        return []

    diff_files: list[str] = target_modules_data.get("git_diff_files", [])
    if not diff_files:
        return []

    euts = data.get("eut_items", [])
    if not euts:
        return []

    # 从所有 EUT 的 when + given 字段提取被提及的类名
    _CLS = re.compile(r"\b([A-Z][a-zA-Z0-9]{3,})\b")
    eut_mentioned: set[str] = set()
    for e in euts:
        for field in ("when", "given"):
            text = str(e.get(field, "") or "")
            eut_mentioned.update(_CLS.findall(text))

    missing: list[tuple[str, str]] = []
    for f in diff_files:
        if not f.endswith(".java"):
            continue
        if "src/test/" in f:
            continue
        if any(f.startswith(skip) for skip in _SKIP_MODULE_PREFIXES):
            continue

        class_name = f.split("/")[-1].replace(".java", "")

        if not any(class_name.endswith(s) for s in _IMPL_SUFFIXES):
            continue
        if any(pat in class_name for pat in _SKIP_CLASS_PATTERNS):
            continue

        if class_name not in eut_mentioned:
            missing.append((class_name, f))

    if not missing:
        return []

    errors: list[str] = []
    for cls, path in missing:
        short_path = "/".join(path.split("/")[-3:])
        errors.append(
            f"BLOCKED: Q05 git_diff_not_covered — {cls} 在 git diff 中有变更"
            f"（{short_path}）但未出现在任何 EUT 的 when/given 字段。"
            "变更的实现类必须有对应 EUT，请补充到 EUT 矩阵后重新 finalize。"
        )

    return errors
