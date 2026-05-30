"""Q05 专属 auto_check 函数（auto_checks.py 内部实现模块，不直接被外部调用）."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json
from qualix.log import get_logger
from qualix.text_utils import STRUCTURED_JSON_MAP

log = get_logger(__name__)

_CONCURRENT_KEYWORDS: Final = frozenset(
    {
        "幂等",
        "并发",
        "重复提交",
        "并行",
        "concurrent",
        "idempotent",
        "CountDownLatch",
        "重复建单",
        "重复创建",
        "多线程",
        "thread",
        "race condition",
        "竞态",
    }
)

_CONCURRENT_THEN_PATTERNS: Final = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"CountDownLatch",
        r"ExecutorService",
        r"Thread\s*\.",
        r"AtomicInteger|AtomicLong",
        r"concurrent",
        r"\d+\s*线程|线程\s*\d+",
        r"times\s*\(\s*1\s*\).*countDown|countDown.*times\s*\(\s*1\s*\)",
    ]
]

_BOUNDARY_KEYWORDS: Final = frozenset(
    {"null", "空", "最大", "最小", "边界", "上限", "下限", "0条", "空集", "为空", "为零", "empty", "boundary"}
)


def _check_q05_req_br_se_coverage(
    validated: Any,
    phase_id: str,
    output_dir: Path,
    project_id: str,
) -> list[str]:
    """Q05 核心覆盖完整性：REQ+BR+SE × 代码路径（Happy/Exception/Boundary/并发幂等）.

    原则（不可违反）：
    - 每条 REQ/BR/SE 必须有 Exception EUT（100%）
    - 每条 REQ/BR/SE 必须有 Happy Path EUT（全局 ≥80%）
    - 有边界语义的条目必须有 Boundary EUT（100%）
    - 有并发/幂等语义的 SE 必须有并发测试（CountDownLatch/ExecutorService 等）
    """
    if phase_id not in {"Q05", "Q05a"}:
        return []

    # 读 Q01 upstream JSON 获取 REQ/BR/SE 完整列表
    q01_def = PHASE_DEFS.get("Q01")
    if not q01_def:
        return ["NOT_APPLICABLE: Q01 phase_def not found，无法验证 REQ+BR+SE 覆盖完整性"]

    q01_pd = _phase_dir(output_dir, project_id, q01_def)
    q01_json_file = STRUCTURED_JSON_MAP.get("Q01")
    if not q01_json_file:
        return ["NOT_APPLICABLE: Q01 structured JSON not configured"]

    q01_data = load_json(q01_pd / q01_json_file)
    if not q01_data:
        return ["NOT_APPLICABLE: Q01 structured JSON not found，无法验证覆盖完整性"]

    # 构建 Q01 所有条目: item_id → 描述文本（用于检测并发/幂等语义）
    all_items: dict[str, str] = {}
    for req in q01_data.get("requirements", []):
        item_id = req.get("req_id", "")
        if item_id:
            all_items[item_id] = req.get("description", "")
    for se in q01_data.get("semantic_expectations", []):
        se_id = se.get("se_id", "")
        if se_id:
            all_items[se_id] = se.get("description", "") + " " + se.get("verification", "")

    if not all_items:
        return ["NOT_APPLICABLE: Q01 中无 REQ/BR/SE 条目"]

    eut_items = getattr(validated, "eut_items", []) or []

    # 按 bound_item/bound_se 聚合：item_id → 已有的路径类型集合
    coverage: dict[str, set[str]] = {}
    for eut in eut_items:
        item_id = getattr(eut, "bound_item", "") or getattr(eut, "bound_se", "")
        if not item_id:
            continue
        rt = getattr(eut, "route_type", None)
        rt_str = rt.value if hasattr(rt, "value") else str(rt)
        coverage.setdefault(item_id, set()).add(rt_str)

    # SE → bound_reqs 反向映射：支持间接覆盖判断
    # 若 BR-003 在 SE-001.bound_reqs 中，且 SE-001 有对应路径的 EUT，则 BR-003 间接覆盖
    req_covered_by_se: dict[str, set[str]] = {}
    for se_data in q01_data.get("semantic_expectations", []):
        se_id = se_data.get("se_id", "")
        for br_id in se_data.get("bound_reqs", []):
            req_covered_by_se.setdefault(br_id, set()).add(se_id)

    def _has_route_coverage(item_id: str, route: str) -> bool:
        """直接覆盖 OR 通过 SE.bound_reqs 间接覆盖."""
        if route in coverage.get(item_id, set()):
            return True
        return any(route in coverage.get(se_id, set()) for se_id in req_covered_by_se.get(item_id, set()))

    errors: list[str] = []
    happy_covered = 0
    total = len(all_items)

    for item_id, desc in all_items.items():
        # Happy Path（直接 or 间接，统计全局覆盖率）
        if _has_route_coverage(item_id, "Happy Path"):
            happy_covered += 1
        else:
            errors.append(
                f"BLOCKED: Q05 {item_id} 缺少 Happy Path EUT（直接 bound_item 或通过 SE.bound_reqs 间接覆盖均可）。"
            )

        # Exception（100%，直接 or 间接）
        if not _has_route_coverage(item_id, "Exception"):
            errors.append(
                f"BLOCKED: Q05 {item_id} 缺少 Exception EUT（要求 100%）。必须覆盖该条目实现代码的所有异常/错误分支。"
            )

        # Boundary（有边界语义时 100%，直接 or 间接）
        has_boundary = any(kw in desc for kw in _BOUNDARY_KEYWORDS)
        if has_boundary and not _has_route_coverage(item_id, "Boundary"):
            errors.append(f"BLOCKED: Q05 {item_id} 描述含边界语义但缺少 Boundary EUT（要求 100%）。")

        # 并发/幂等/多线程（有相关语义时必须有并发测试）
        concurrent_kw = next((kw for kw in _CONCURRENT_KEYWORDS if kw in desc), None)
        if concurrent_kw:
            item_euts = [
                e for e in eut_items if (getattr(e, "bound_item", "") or getattr(e, "bound_se", "")) == item_id
            ]
            has_concurrent = any(
                any(pat.search(getattr(e, "then", "") or "") for pat in _CONCURRENT_THEN_PATTERNS) for e in item_euts
            )
            if not has_concurrent:
                errors.append(
                    f"BLOCKED: Q05 {item_id} 有并发/幂等语义（含关键词「{concurrent_kw}」）"
                    "但缺少并发测试（then 须含 CountDownLatch/ExecutorService/AtomicInteger 等强并发断言）。"
                )

    # 全局 Happy Path 覆盖率门禁（≥80%）
    happy_rate = happy_covered / total if total > 0 else 0.0
    if happy_rate < 0.8:
        errors.insert(
            0,
            f"BLOCKED: Q05 REQ+BR+SE Happy Path 覆盖率 {happy_rate:.0%} < 80%"
            f"（已覆盖 {happy_covered}/{total} 条）。"
            "每条 REQ/BR/SE 的实现代码必须有正向路径测试。",
        )

    # --- git diff 维度：变更的类/方法必须出现在某条 EUT 的 when 字段中 ---
    errors.extend(_check_q05_git_diff_coverage(validated, output_dir, project_id))

    return errors


def _check_q05_git_diff_coverage(
    validated: Any,
    output_dir: Path,
    project_id: str,
) -> list[str]:
    """Q05 代码维度覆盖：git diff 变更的类/方法必须在 EUT when 字段中出现.

    覆盖源 = REQ+BR+SE（需求维度）+ git diff 变更方法（代码维度），两者等权。
    每个在 feature branch 新增/修改的 public 方法，必须有对应 EUT 的 when 字段引用它。
    """
    import subprocess

    q05_def = PHASE_DEFS.get("Q05")
    if not q05_def:
        return []

    int_dir = _internal_dir(output_dir, project_id, q05_def)
    inputs_data = load_json(int_dir / "_inputs.json") or {}
    code_repos: list[str] = inputs_data.get("code_repos", [])
    if not code_repos and inputs_data.get("code_repo"):
        code_repos = [inputs_data["code_repo"]]
    if not code_repos:
        return ["NOT_APPLICABLE: Q05 git diff 覆盖检查——无 code_repo 配置"]

    eut_items = getattr(validated, "eut_items", []) or []

    # 按 when 字段中出现的类名聚合：class_name → 路径类型集合
    class_coverage: dict[str, set[str]] = {}
    for eut in eut_items:
        when_text = getattr(eut, "when", "") or ""
        rt = getattr(eut, "route_type", None)
        rt_str = rt.value if hasattr(rt, "value") else str(rt)
        # 扫描 when 字段中出现的类名（大写开头的 Java 类名）
        for cls in re.findall(r"\b([A-Z][A-Za-z0-9]+)\b", when_text):
            class_coverage.setdefault(cls, set()).add(rt_str)

    errors: list[str] = []

    for repo in code_repos:
        repo_path = Path(repo).expanduser().resolve()
        if not repo_path.is_dir():
            continue
        try:
            result = subprocess.run(
                ["git", "diff", "origin/master...HEAD", "--name-only", "--diff-filter=AM"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=15,
            )
            changed_files = [f for f in result.stdout.splitlines() if f.endswith(".java") and "/test/" not in f]
        except Exception:
            continue

        for java_file in changed_files:
            class_name = Path(java_file).stem
            if not class_name:
                continue

            # 跳过无业务逻辑的辅助类：DTO/VO/Param/Enum/Config/Constants/Interface/Builder
            _SKIP_SUFFIXES = (
                "DTO",
                "Dto",
                "VO",
                "Vo",
                "Param",
                "Enum",
                "Config",
                "Constants",
                "Constant",
                "Builder",
                "Interface",
                "Service" if class_name.endswith("Interface") else "",
            )
            _SKIP_EXACT = {
                "OpCode",
                "SrvTagEnum",
                "InterConstants",
                "Rules",
                "ExchangeSrvVo",
                "OtherDTO",
                "OcItemVo",
                "OrderDetail",
                # Dubbo service impl 门面类（无独立业务逻辑）
                "SrvCommonDubboServiceImpl",
                "SrvDetailDubboServiceImpl",
                "SrvElasticsearchDubboServiceImpl",
                "SrvListDubboServiceImpl",
                "SrvListSmartServiceDubboServiceImpl",
            }
            if class_name in _SKIP_EXACT or any(class_name.endswith(s) for s in _SKIP_SUFFIXES if s):
                continue
            # 纯接口定义（不含 Impl）跳过
            if "Service" in class_name and "Impl" not in class_name and "Consumer" not in class_name:
                continue

            routes = class_coverage.get(class_name, set())

            # 变更类未出现在任何 EUT when 字段中
            if not routes:
                errors.append(
                    f"FAIL: Q05 git diff — {class_name} 变更类未在任何 EUT when 字段中出现。"
                    "每个 feature branch 变更的业务类必须有 EUT 覆盖其主要方法。"
                )
                continue

            # 有 EUT 但缺少 Happy Path
            if "Happy Path" not in routes:
                errors.append(f"FAIL: Q05 git diff — {class_name} 有 EUT 但缺少 Happy Path（正常流程测试）。")

            # 有 EUT 但缺少 Exception
            if "Exception" not in routes:
                errors.append(f"FAIL: Q05 git diff — {class_name} 有 EUT 但缺少 Exception EUT（异常/错误分支测试）。")

    return errors
