"""AutoHarness: 从 Pydantic schema + phase_registry 自动推导 finalize 校验.

自动生成的校验覆盖：
1. Schema 校验：JSON 产物是否符合 Pydantic 数据契约
2. 交叉引用校验：GAP/OPEN 的 related_ids 是否指向存在的 REQ/BR
3. 完整性校验：approve_checklist 中可自动验证的条目
4. 严重等级校验：GAP/Issue 是否标注了严重等级（当 schema 有 severity 字段时）
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pydantic import BaseModel

from pydantic import ValidationError

from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import internal_dir as _internal_dir
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger
from dqg.text_utils import STRUCTURED_JSON_MAP

log = get_logger(__name__)

# Phase → Pydantic 模型类（延迟导入避免循环）
_SCHEMA_MAP: Final = MappingProxyType(
    {
        "Q01": "dqg.schemas.phase_q01:PhaseAOutput",
        "Q02": "dqg.schemas.phase_q02:PhaseA3Output",
        "Q04": "dqg.schemas.phase_q04:PhaseA5Output",
        "Q03": "dqg.schemas.phase_q03:PhaseA6Output",
        "Q05": "dqg.schemas.phase_q05:PhaseBOutput",
        "Q06": "dqg.schemas.phase_q06:PhaseCOutput",
        "Q07": "dqg.schemas.phase_q07:PhaseDOutput",
    }
)


def _import_schema(phase_id: str):
    """动态导入 Phase 对应的 Pydantic 模型."""
    module_path = _SCHEMA_MAP.get(phase_id)
    if not module_path:
        return None
    module_name, class_name = module_path.rsplit(":", 1)
    import importlib

    mod = importlib.import_module(module_name)
    return getattr(mod, class_name, None)


def auto_derive_checks(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str]:
    """从 schema + registry 自动推导校验，返回错误列表.

    校验层次：
    1. Schema 合规性（Pydantic 校验）
    2. 交叉引用完整性（related_ids 指向存在的 ID）
    3. 严重等级标注（有 severity 字段的条目必须非空）
    4. 最小产物要求（deliverables 文件是否存在）
    """
    errors: list[str] = []
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return errors

    pd = _phase_dir(output_dir, project_id, phase_def)

    # --- 1. 交付物文件存在性检查 ---
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if json_file:
        json_path = pd / json_file
        if not json_path.exists():
            errors.append(f"MISSING: 结构化产物 {json_file} 不存在")
            return errors  # 没有 JSON 就无法做后续校验

        # --- 2. Schema 合规性校验 ---
        data = load_json(json_path)
        if data is None:
            errors.append(f"INVALID: {json_file} 无法解析为 JSON")
            return errors

        schema_cls = _import_schema(phase_id)
        if schema_cls:
            try:
                validated = schema_cls.model_validate(data)
            except ValidationError as e:
                for err in e.errors()[:5]:  # 最多报 5 个
                    loc = " → ".join(str(x) for x in err["loc"])
                    errors.append(f"SCHEMA: {loc}: {err['msg']}")
                return errors  # schema 不过就不做后续检查
            else:
                # --- 3. 交叉引用校验 ---
                errors.extend(_check_cross_references(validated, phase_id))
                # --- 4. 严重等级标注校验 ---
                errors.extend(_check_severity_annotations(validated, phase_id))
                # --- 5. Location 覆盖校验（Q06 COVERED 必须有 test_location）---
                errors.extend(_check_location_coverage(validated, phase_id))
                # --- 6. Q01 SE verification / bound_reqs / GAP 语义质量校验 ---
                errors.extend(_check_se_verification_quality(validated, phase_id))
                errors.extend(_check_se_bound_reqs_nonempty(validated, phase_id))
                errors.extend(_check_gap_semantic_quality(validated, phase_id))
                # --- Change 3: Q01 summary 派生字段一致性 ---
                errors.extend(_check_q01_summary_derivation(validated, phase_id))
                # --- G8: Q06 findings.severity 分布合理性（需要 validated 对象）---
                errors.extend(_check_findings_severity_distribution(validated, phase_id))

        # --- Q01-1: SE/BR source 行号内容交叉验证（L1↔L0，最强反幻觉）---
        if phase_id == "Q01":
            errors.extend(_check_source_line_reality(output_dir, project_id, phase_id))
            # --- Change 2: SE.source evidence 快照（每条 SE 的行号和内容哈希存档）---
            _save_se_source_evidence(output_dir, project_id, phase_id)
            # --- Q01-2: SE/BR 描述中代码标识符反推检测 ---
            errors.extend(_check_code_identifier_leakage(output_dir, project_id, phase_id))
            # --- Q01-4: BR 数量与 PRD 信息密度合理性检查 ---
            errors.extend(_check_br_density_ratio(output_dir, project_id, phase_id))

        # --- Q05: REQ+BR+SE × 代码路径完整性（Happy/Exception/Boundary/并发幂等）---
        if phase_id == "Q05":
            errors.extend(_check_q05_req_br_se_coverage(validated, phase_id, output_dir, project_id))

        # --- Q06: coverage_gate 自报 ↔ JaCoCo 一致性 (G2) ---
        if phase_id == "Q06":
            errors.extend(_check_coverage_gate_consistency(output_dir, project_id, phase_id))
            # --- Q06: audit_items 数量 ≥ Q05 EUT 数量 (G7) ---
            errors.extend(_check_audit_items_count(output_dir, project_id, phase_id))
            # --- Q06: evidence 行号内容验证 (G5) ---
            errors.extend(_check_evidence_line_reality(output_dir, project_id, phase_id))

    # --- 5. RSM 覆盖率校验（跨 Phase，在 A.5/B/D finalize 时触发）---
    if phase_id in {"Q04", "Q05", "Q06", "Q07"}:
        errors.extend(_check_rsm_coverage(output_dir, project_id, phase_id))

    return errors


def _check_cross_references(validated: BaseModel, phase_id: str) -> list[str]:
    """检查 related_ids 是否指向存在的 ID."""
    errors: list[str] = []

    if phase_id == "Q01":
        # 收集所有已定义的 ID
        all_ids: set[str] = set()
        for req in getattr(validated, "requirements", []):
            all_ids.add(req.req_id)
        for se in getattr(validated, "semantic_expectations", []):
            all_ids.add(se.se_id)

        # 检查 GAP 的 related_ids
        for gap in getattr(validated, "gaps", []):
            for ref_id in gap.related_ids:
                if ref_id and ref_id not in all_ids:
                    errors.append(f"XREF: {gap.gap_id} 引用了不存在的 ID '{ref_id}'")

        # 检查 OPEN 的 related_ids
        for item in getattr(validated, "open_items", []):
            for ref_id in item.related_ids:
                if ref_id and ref_id not in all_ids:
                    errors.append(f"XREF: {item.open_id} 引用了不存在的 ID '{ref_id}'")

    return errors


def _check_severity_annotations(validated: BaseModel, phase_id: str) -> list[str]:
    """检查有 severity 字段的条目是否都标注了严重等级."""
    errors: list[str] = []

    if phase_id == "Q03":
        for issue in getattr(validated, "issues", []):
            if not issue.severity:
                errors.append(f"SEVERITY: {issue.issue_id} 未标注严重等级")
        # Failure Mode 必须有 status
        for fm in getattr(validated, "failure_modes", []):
            if not fm.failure_scenario:
                errors.append(f"SEVERITY: failure_mode '{fm.business_path}' 缺少 failure_scenario")

    if phase_id == "Q01":
        # GAP 应该有 required_clarification
        for gap in getattr(validated, "gaps", []):
            if not gap.required_clarification:
                errors.append(f"INCOMPLETE: {gap.gap_id} 缺少 required_clarification（需要说明需要澄清什么）")

    return errors


def _check_location_coverage(validated: BaseModel, phase_id: str) -> list[str]:
    """Q06 COVERED 判定必须有 test_location，否则降级为 PARTIAL."""
    if phase_id != "Q06":
        return []
    errors: list[str] = []
    for item in getattr(validated, "audit_items", []):
        status = getattr(item, "status", None)
        test_location = getattr(item, "test_location", None)
        eut_id = getattr(item, "eut_id", "unknown")
        if str(status) == "COVERED" and test_location is None:
            errors.append(
                f"LOCATION: {eut_id}: status=COVERED 但 test_location 为空，降级为 PARTIAL。请补充测试代码坐标。"
            )
    return errors


_VERIFICATION_STRONG_ANCHORS: Final = (
    "断言",
    "assert",
    "SELECT",
    "HTTP",
    "errorCode",
    "参数化",
    "Mock",
    "verify(",
    "CountDownLatch",
    "断点",
    "DB",
)


def _check_se_verification_quality(validated: BaseModel, phase_id: str) -> list[str]:
    """Q01-2: SE.verification 字段质量升级为 FAIL 级（对标 Q05 then_must_be_concrete）.

    - 空字符串 → FAIL（不再向后兼容，每条 SE 必须有可执行验证步骤）
    - 非空但弱（<20字 且无强锚点词）→ FAIL
    强锚点词：断言/assert/SELECT/HTTP/errorCode/Mock/verify/CountDownLatch 等
    """
    if phase_id != "Q01":
        return []
    errors: list[str] = []
    for se in getattr(validated, "semantic_expectations", []):
        se_id = getattr(se, "se_id", "SE-?")
        verification = (getattr(se, "verification", "") or "").strip()
        if not verification:
            errors.append(
                f"FAIL: Q01 {se_id} verification 为空。"
                "每条 SE 必须填写可执行验证步骤（如：调用接口 + 断言 HTTP 状态码/errorCode/DB 字段）。"
            )
            continue
        weak = len(verification) < 20 or not any(anchor in verification for anchor in _VERIFICATION_STRONG_ANCHORS)
        if weak:
            errors.append(
                f"FAIL: Q01 {se_id} verification 写法弱（长度={len(verification)}，"
                "无断言/SQL/HTTP/errorCode/Mock 等强锚点）。"
                "请补至可执行步骤（参考 se_checklist ✓ 示例）。"
            )
    return errors


# ---------------------------------------------------------------------------
# Q06 专项检查函数
# ---------------------------------------------------------------------------


def _check_coverage_gate_consistency(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """Change 3: coverage_gate.line_coverage（LLM 自报）与 JaCoCo 实际结果交叉验证，升级为 BLOCKED.

    Summary 是派生字段——从数组重算，自报与实际不一致 → BLOCKED（原为 WARNING）。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return ["NOT_APPLICABLE: Q06 phase_def not found"]
    pd = _phase_dir(output_dir, project_id, phase_def)
    int_dir = _internal_dir(output_dir, project_id, phase_def)

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return ["NOT_APPLICABLE: Q06 structured JSON not configured"]
    data = load_json(pd / json_file)
    if not data:
        return ["NOT_APPLICABLE: Q06 structured JSON not found"]

    gate = data.get("coverage_gate", {}) or {}
    reported_line = gate.get("line_coverage")
    if reported_line is None:
        return ["NOT_APPLICABLE: coverage_gate.line_coverage not set (LLM did not report a number)"]

    # 读 JaCoCo 实际结果（finalize 写入 _internal）
    for candidate in ["_incremental_coverage.json", "_coverage.json"]:
        cov = load_json(int_dir / candidate)
        if cov:
            actual_line = cov.get("line_coverage") or cov.get("overall_line_rate")
            if actual_line is not None:
                if actual_line <= 1.0:
                    actual_line *= 100
                diff = abs(float(reported_line) - float(actual_line))
                if diff > 15:
                    return [
                        f"BLOCKED: Q06 coverage_gate_mismatch — phase_c_structured.json 自报覆盖率"
                        f" {reported_line:.1f}% 与 JaCoCo 实际 {actual_line:.1f}% 偏差 {diff:.1f}%（阈值 15%）。"
                        "coverage_gate 是派生字段，必须从 JaCoCo 报告派生，禁止手动填写。"
                    ]
                return []
    return ["NOT_APPLICABLE: JaCoCo coverage data not yet available in _internal/"]


def _check_q01_summary_derivation(validated: Any, phase_id: str) -> list[str]:
    """Change 3: Q01 summary.counts 派生字段校验——从数组重算，自报与实际不一致 → FAIL.

    防止 LLM 在 summary 里填虚高的数字（如 total_se=10 但实际只有 8 条 SE）。
    """
    if phase_id != "Q01":
        return []
    ses = getattr(validated, "semantic_expectations", [])
    reqs = getattr(validated, "requirements", [])
    gaps = getattr(validated, "gaps", [])
    opens = getattr(validated, "open_items", [])

    # 尝试读取 summary 字段（如果 schema 有的话）
    summary = getattr(validated, "summary", None) or {}
    if not isinstance(summary, dict) or not summary:
        return []  # 无 summary 字段，不检查

    errors: list[str] = []
    checks = [
        ("total_se", len(ses), "semantic_expectations"),
        ("total_req", sum(1 for r in reqs if str(r.req_id).startswith("REQ")), "requirements[REQ]"),
        ("total_br", sum(1 for r in reqs if str(r.req_id).startswith("BR")), "requirements[BR]"),
        ("total_gap", len(gaps), "gaps"),
        ("total_open", len(opens), "open_items"),
    ]
    for key, actual, label in checks:
        reported = summary.get(key)
        if reported is not None and int(reported) != actual:
            errors.append(
                f"FAIL: Q01 summary.{key}={reported} 与 {label} 数组实际长度 {actual} 不一致。"
                f"summary 是派生字段，必须与数组一致，不允许手动填写。"
            )
    return errors


def _check_audit_items_count(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """G7: Q06 audit_items 数量应 ≥ Q05 eut_items 数量（允许 ≤10% 的漏审）.

    防止 LLM 只审计部分 EUT，跳过质量最差的测试使覆盖率数字虚高。
    """
    from dqg.constants import PHASE_DIR_MAP
    from dqg.core.state_machine import phase_dir as _pd

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    q06_count = len(data.get("audit_items", []))

    # 读 Q05 EUT 数量
    q05_json = STRUCTURED_JSON_MAP.get("Q05")
    q05_dir = PHASE_DIR_MAP.get("Q05")
    if not q05_json or not q05_dir:
        return []
    phase_b = load_json(output_dir / project_id / q05_dir / q05_json)
    if not phase_b:
        return []
    q05_count = len(phase_b.get("eut_items", []))
    if q05_count == 0:
        return []

    if q06_count < q05_count * 0.9:
        return [
            f"FAIL: Q06 audit_items_insufficient — Q06 审计了 {q06_count} 条 EUT，"
            f"但 Q05 共有 {q05_count} 条（覆盖率 {q06_count * 100 // q05_count}%，要求 ≥90%）。"
            "Q06 必须覆盖 Q05 绝大多数 EUT，不能跳过质量差的测试。"
        ]
    return []


def _check_evidence_line_reality(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """G5: audit_items.evidence 行号内容验证（对标 Q01-1 SE.source 验证）.

    COVERED 条目的 evidence = "[file:line]" → 验证该行附近确有断言关键词。
    """
    from dqg.core.state_machine import phase_dir as _pd

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    # 读 code_repos
    from dqg.core.state_machine import internal_dir as _internal_dir

    int_dir = _internal_dir(output_dir, project_id, phase_def)
    inputs = load_json(int_dir / "_inputs.json") or {}
    code_repos: list[str] = inputs.get("code_repos") or []
    if not code_repos and inputs.get("code_repo"):
        code_repos = [inputs["code_repo"]]

    _ASSERT_KW = re.compile(r"\bassert\w+\s*\(|\bverify\s*\(", re.IGNORECASE)
    _EV_RE = re.compile(r"\[?([^:\[\]]+\.java):(\d+)\]?")

    suspicious: list[str] = []
    for item in data.get("audit_items", []):
        if not isinstance(item, dict) or str(item.get("status", "")).upper() != "COVERED":
            continue
        evidence = str(item.get("evidence", "") or "")
        m = _EV_RE.search(evidence)
        if not m:
            continue
        fname, lineno = m.group(1), int(m.group(2))

        found = False
        for repo_str in code_repos:
            repo = Path(repo_str).expanduser().resolve()
            # 在 src/test/ 下递归找该文件
            for candidate in repo.rglob(f"*{Path(fname).name}"):
                try:
                    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                    ctx = "\n".join(lines[max(0, lineno - 4) : lineno + 3])
                    if _ASSERT_KW.search(ctx):
                        found = True
                except OSError:
                    pass
                if found:
                    break
            if found:
                break

        if not found:
            eut_id = item.get("eut_id", "?")
            suspicious.append(f"{eut_id}({fname}:{lineno})")

    if suspicious:
        return [
            f"WARNING: Q06 evidence_line_no_assert — {len(suspicious)} 个 COVERED 条目的"
            f" evidence 行号附近无断言关键词，疑似虚报来源: {', '.join(suspicious[:4])}。"
        ]
    return []


def _check_findings_severity_distribution(validated: Any, phase_id: str) -> list[str]:
    """G8: Q06 findings.severity 分布合理性检查.

    防止 LLM 系统性低报问题（全标 LOW）让审计看起来"几乎无问题"。
    """
    if phase_id != "Q06":
        return []
    findings = getattr(validated, "findings", [])
    if len(findings) < 3:
        return []

    severities = [str(f.severity).upper() for f in findings if hasattr(f, "severity")]
    if not severities:
        return []

    low_count = sum(1 for s in severities if s in ("LOW", "INFO", "MINOR"))
    if low_count / len(severities) >= 0.9:
        return [
            f"WARNING: Q06 severity_all_low — {low_count}/{len(severities)} 个 finding 均为 LOW/INFO，"
            "疑似系统性低报问题严重性。如果存在 MISSING/WRONG_TARGET 条目，至少应有 MEDIUM 以上 finding。"
        ]
    return []


# ---------------------------------------------------------------------------
# Q05: REQ+BR+SE × 代码路径完整性检查
# ---------------------------------------------------------------------------

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
    if phase_id != "Q05":
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
                f"FAIL: Q05 {item_id} 缺少 Happy Path EUT（直接 bound_item 或通过 SE.bound_reqs 间接覆盖均可）。"
            )

        # Exception（100%，直接 or 间接）
        if not _has_route_coverage(item_id, "Exception"):
            errors.append(
                f"FAIL: Q05 {item_id} 缺少 Exception EUT（要求 100%）。必须覆盖该条目实现代码的所有异常/错误分支。"
            )

        # Boundary（有边界语义时 100%，直接 or 间接）
        has_boundary = any(kw in desc for kw in _BOUNDARY_KEYWORDS)
        if has_boundary and not _has_route_coverage(item_id, "Boundary"):
            errors.append(f"FAIL: Q05 {item_id} 描述含边界语义但缺少 Boundary EUT（要求 100%）。")

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
                    f"FAIL: Q05 {item_id} 有并发/幂等语义（含关键词「{concurrent_kw}」）"
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


_SOURCE_LINE_RE = re.compile(r":(\d+)$")


def _save_se_source_evidence(output_dir: Path, project_id: str, phase_id: str) -> None:
    """Change 2: Q01 finalize 时将每条 SE.source 的行内容和 context_hash 存档.

    产物：_internal/_se_source_evidence.json
    Schema: [{se_id, source_file, source_line, line_text, context_hash, verified_at}]

    下游 Phase（Q05/Q06）引用 SE 时可通过 se_id → evidence 查到原始 PRD 依据，
    而不依赖自由文本 source 字段（自由文本可以被随意修改）。
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return
    pd = _phase_dir(output_dir, project_id, phase_def)
    plain_text_path = pd / "plain_text.txt"
    if not plain_text_path.exists():
        return

    try:
        prd_lines = plain_text_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return
    data = load_json(pd / json_file)
    if not data:
        return

    evidence_list = []
    now = datetime.utcnow().isoformat()
    for se in data.get("semantic_expectations", []):
        se_id = se.get("se_id", "")
        source = se.get("source", "") or ""
        m = _SOURCE_LINE_RE.search(source)
        if not m:
            evidence_list.append(
                {
                    "se_id": se_id,
                    "source_file": None,
                    "source_line": None,
                    "line_text": None,
                    "context_hash": None,
                    "verified_at": now,
                }
            )
            continue
        line_no = int(m.group(1))
        if line_no < 1 or line_no > len(prd_lines):
            evidence_list.append(
                {
                    "se_id": se_id,
                    "source_file": "plain_text.txt",
                    "source_line": line_no,
                    "line_text": None,
                    "context_hash": None,
                    "verified_at": now,
                }
            )
            continue
        line_text = prd_lines[line_no - 1]
        ctx = "\n".join(prd_lines[max(0, line_no - 3) : line_no + 3])
        ctx_hash = hashlib.sha256(ctx.encode()).hexdigest()[:16]
        evidence_list.append(
            {
                "se_id": se_id,
                "source_file": source.split(":")[0],
                "source_line": line_no,
                "line_text": line_text[:200],
                "context_hash": ctx_hash,
                "verified_at": now,
            }
        )

    if evidence_list:
        int_dir = _internal_dir(output_dir, project_id, phase_def)
        int_dir.mkdir(parents=True, exist_ok=True)
        save_json(int_dir / "_se_source_evidence.json", evidence_list)
        log.info("Q01: saved SE source evidence for %d SE items", len(evidence_list))


_MIN_KEYWORD_MATCH = 1  # 至少匹配 1 个关键词才算来源有效


_GAP_SEMANTIC_KWS: frozenset[str] = frozenset(
    {"缺少", "不明确", "未定义", "需要", "待确认", "缺乏", "缺失", "没有说明", "未说明", "不清楚", "没有明确"}
)


def _check_gap_semantic_quality(validated: BaseModel, phase_id: str) -> list[str]:
    """Q01-5: GAP 描述必须含缺口语义词，防止 LLM 虚构假 GAP."""
    if phase_id != "Q01":
        return []
    errors: list[str] = []
    for gap in getattr(validated, "gaps", []):
        gap_id = getattr(gap, "gap_id", "GAP-?")
        desc = getattr(gap, "description", "") or ""
        if desc and not any(kw in desc for kw in _GAP_SEMANTIC_KWS):
            errors.append(
                f"WARNING: Q01 {gap_id} 描述不含缺口语义词（缺少/不明确/未定义等），"
                "疑似非真实 GAP。GAP 应描述 PRD 里明显缺失的信息。"
            )
    return errors


def _check_se_bound_reqs_nonempty(validated: BaseModel, phase_id: str) -> list[str]:
    """Q01-3: 每条 SE 必须绑定至少一个 REQ 或 BR（bound_reqs 非空）."""
    if phase_id != "Q01":
        return []
    errors: list[str] = []
    for se in getattr(validated, "semantic_expectations", []):
        se_id = getattr(se, "se_id", "SE-?")
        bound_reqs = getattr(se, "bound_reqs", []) or []
        if not bound_reqs:
            errors.append(
                f"FAIL: Q01 {se_id} bound_reqs 为空。每条 SE 必须绑定至少一个 REQ 或 BR，否则 Q05 BR 覆盖率链路断裂。"
            )
    return errors


def _extract_keywords(text: str) -> list[str]:
    """从描述文本提取关键词（4字以上的中文词组 或 英文单词）."""
    import re as _re

    cn_words = _re.findall(r"[一-鿿]{3,}", text)
    en_words = _re.findall(r"[A-Za-z]{4,}", text)
    return (cn_words + en_words)[:6]  # 最多取 6 个


def _check_source_line_reality(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """Q01-1+Q01-4: SE/BR source 行号内容验证（Change 1: SE→BLOCKED, plain_text缺失→BLOCKED）.

    阻断级别：SE 比 BR 严格（SE 是需求推理核心，必须硬阻断）：
    - plain_text.txt 缺失且有 SE → BLOCKED
    - SE.source 为空 → BLOCKED
    - SE.source 行号超出文件 → BLOCKED（幽灵行号）
    - SE.source 关键词不匹配 → BLOCKED（声明与原文不符）
    - BR source 问题 → WARNING（宽松一级）
    - 无 SE 且无 plain_text → NOT_APPLICABLE
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return ["NOT_APPLICABLE: Q01 phase_def not found"]
    pd = _phase_dir(output_dir, project_id, phase_def)

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return ["NOT_APPLICABLE: Q01 structured JSON file not configured"]
    data = load_json(pd / json_file)
    if not data:
        return ["NOT_APPLICABLE: Q01 structured JSON not found or empty"]

    plain_text_path = pd / "plain_text.txt"
    ses = data.get("semantic_expectations", [])

    if not plain_text_path.exists():
        ses_with_source = [s for s in ses if (s.get("source") or "").strip()]
        if ses_with_source:
            return [
                f"BLOCKED: Q01 source_prd_missing — plain_text.txt 不存在，"
                f"无法验证 {len(ses_with_source)} 条 SE.source 的真实性。"
                "SE 是需求推理的核心，必须有可追溯的 PRD 原文。"
                "请确认飞书文档已正确 ingest（运行 feishu_direct_ingest）。"
            ]
        if ses:
            return ["NOT_APPLICABLE: plain_text.txt not found; SE.source empty check will run separately"]
        return ["NOT_APPLICABLE: plain_text.txt not found (no SE to validate)"]

    try:
        prd_lines = plain_text_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ["INFRA_FAILURE: plain_text.txt 存在但读取失败"]

    errors: list[str] = []

    def _check_source_ref(item_id: str, description: str, source: str, *, strict: bool) -> None:
        """统一的 source 行号校验：strict=True → BLOCKED（SE），strict=False → WARNING（BR）。"""
        level = "BLOCKED" if strict else "WARNING"
        if not source.strip():
            if strict:
                errors.append(f"BLOCKED: Q01 {item_id} source 为空——SE 必须填写 PRD 来源（plain_text.txt:行号）。")
            return
        m = _SOURCE_LINE_RE.search(source)
        if not m:
            if strict:
                errors.append(f"BLOCKED: Q01 {item_id} source 格式无效: '{source}'（要求 plain_text.txt:行号）。")
            return
        line_no = int(m.group(1))
        if line_no < 1 or line_no > len(prd_lines):
            suffix = "，幽灵行号。" if strict else "。"
            errors.append(f"{level}: Q01 {item_id} source 行号 {line_no} 超出文件总行数 {len(prd_lines)}{suffix}")
            return
        context = "\n".join(prd_lines[max(0, line_no - 4) : line_no + 3])
        keywords = _extract_keywords(description)
        if keywords and not any(kw in context for kw in keywords):
            tail = "，疑似 source 虚报或 SE 从代码反推。" if strict else "。"
            errors.append(f"{level}: Q01 {item_id} source 行号 {line_no} 附近不含描述关键词（{keywords[:3]}）{tail}")

    for se in ses:
        _check_source_ref(se.get("se_id", "SE-?"), se.get("description", ""), se.get("source", ""), strict=True)

    for req in data.get("requirements", []):
        if str(req.get("req_id", "")).startswith("BR"):
            _check_source_ref(
                req.get("req_id", "BR-?"), req.get("description", ""), req.get("source", ""), strict=False
            )

    return errors


# Q1-2: 代码标识符泄漏检测
# 强代码标识符：驼峰方法名（≥3个大写字母段）、@注解、下划线常量
_CODE_IDENT_PATTERN = re.compile(
    r"\b([a-z][a-zA-Z0-9]{4,}[A-Z][a-zA-Z0-9]{3,})\b"  # camelCase 方法/类名
    r"|(@[A-Z][a-zA-Z]{3,})"  # @Annotation
    r"|\b([A-Z_]{4,})\b"  # SNAKE_CASE 常量
)
# 过滤掉的通用词（不是代码标识符）
_CODE_WHITELIST = frozenset(
    {
        "HTTP",
        "HTTPS",
        "JSON",
        "XML",
        "SQL",
        "API",
        "URL",
        "SDK",
        "LLM",
        "NULL",
        "TRUE",
        "FALSE",
        "POST",
        "GET",
        "PUT",
        "OPEN",
    }
)


def _check_code_identifier_leakage(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str]:
    """Q1-2: 检测 SE/BR 描述中是否混入了代码反推的标识符.

    如果 SE/BR 描述里出现了驼峰方法名/类名/注解（如 identifyByPrecheckAndFulfillment、
    @DistributedLocked），但这些词在 PRD 原文里不存在，高度疑似 LLM 从代码反推。
    业务需求语言不应该包含代码实现标识符。
    """
    from dqg.core.state_machine import phase_dir as _pd
    from dqg.json_utils import load_json

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    plain_text_path = pd / "plain_text.txt"

    prd_text = ""
    if plain_text_path.exists():
        with contextlib.suppress(OSError):
            prd_text = plain_text_path.read_text(encoding="utf-8", errors="replace")

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    suspicious: list[str] = []

    def _scan(item_id: str, text: str) -> None:
        for m in _CODE_IDENT_PATTERN.finditer(text):
            ident = next(g for g in m.groups() if g)
            ident_clean = ident.lstrip("@")
            if ident_clean in _CODE_WHITELIST:
                continue
            # 标识符在 PRD 原文里不存在 → 疑似代码反推
            if prd_text and ident_clean not in prd_text:
                suspicious.append(f"{item_id}('{ident}'不在PRD原文)")

    for se in data.get("semantic_expectations", []):
        _scan(se.get("se_id", "SE-?"), se.get("description", "") or "")
    for req in data.get("requirements", []):
        req_id = str(req.get("req_id", ""))
        if req_id.startswith("BR"):
            _scan(req_id, req.get("description", "") or "")

    if suspicious:
        unique = sorted(set(suspicious))
        return [
            f"WARNING: Q01 code_identifier_leakage — {len(unique)} 处 SE/BR 描述包含 PRD 原文不存在的"
            f"代码标识符，疑似从代码反推而非 PRD 推理: {', '.join(unique[:5])}。"
            "业务需求描述不应出现驼峰类名/方法名/@注解，请改用业务语言描述。"
        ]
    return []


def _check_br_density_ratio(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> list[str]:
    """Q1-4: BR 数量与 PRD 信息密度合理性检查.

    合理比例：每 20~300 行 PRD 对应 1 条 BR。
    - < 10 行/BR（膨胀）：LLM 把一个场景拆成太多 BR，虚增覆盖感
    - > 300 行/BR（压缩）：LLM 把多个场景合并，降低后续测试工作量
    """
    from dqg.core.state_machine import phase_dir as _pd
    from dqg.json_utils import load_json

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    plain_text_path = pd / "plain_text.txt"
    if not plain_text_path.exists():
        return []

    try:
        prd_lines = len(plain_text_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return []

    if prd_lines < 20:
        return []  # PRD 太短，不做密度检查

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    br_count = sum(1 for r in data.get("requirements", []) if str(r.get("req_id", "")).startswith("BR"))
    if br_count == 0:
        return []

    lines_per_br = prd_lines / br_count
    errors: list[str] = []

    if lines_per_br < 10:
        errors.append(
            f"WARNING: Q01 br_density_inflated — PRD {prd_lines} 行产生了 {br_count} 条 BR"
            f"（每 {lines_per_br:.1f} 行/BR），密度过高（阈值 ≥10）。"
            "疑似 LLM 将一个场景拆分为过多 BR，虚增覆盖感。"
        )
    elif lines_per_br > 300:
        errors.append(
            f"WARNING: Q01 br_density_insufficient — PRD {prd_lines} 行仅产生了 {br_count} 条 BR"
            f"（每 {lines_per_br:.0f} 行/BR），密度过低（阈值 ≤300）。"
            "疑似 LLM 将多个场景合并或跳过了关键分支需求。"
        )
    return errors


def _check_rsm_coverage(output_dir: Path, project_id: str, phase_id: str) -> list[str]:
    """RSM 覆盖率校验：检查跨 Phase 的需求追踪完整性.

    发现缺口时自动生成补充任务文件（_coverage_gap_tasks.json），
    下游 Phase 可消费这些任务做定向补充。
    """
    errors: list[str] = []

    try:
        from dqg.schemas.rsm import compute_coverage, load_rsm

        lifecycle = load_rsm(output_dir, project_id)
        if not lifecycle:
            return errors  # Phase A 还没跑，无法计算

        coverage = compute_coverage(lifecycle, project_id)
    except Exception:
        return errors  # RSM 计算失败不阻断 finalize

    # 保存覆盖率快照（趋势追踪）
    try:
        from dqg.store.store_coverage import save_coverage_snapshot

        save_coverage_snapshot(output_dir, project_id, phase_id, coverage)
    except Exception:
        log.debug("coverage snapshot 保存失败", exc_info=True)

    gap_tasks: list[dict[str, Any]] = []

    if phase_id == "Q04":
        # A.5 finalize 时：REQ 覆盖率不应低于 80%
        if coverage.total_reqs > 0 and coverage.req_coverage_rate < 0.8:
            errors.append(
                f"RSM_COVERAGE: REQ 覆盖率 {coverage.req_coverage_rate:.0%} "
                f"低于阈值 80%（{coverage.reqs_covered}/{coverage.total_reqs}）"
            )
            # 收集未覆盖的 REQ，生成补充任务
            for item in lifecycle.values():
                if item.id_type == "REQ" and item.coverage_status not in ("COVERED", "IMPLICIT"):
                    gap_tasks.append(
                        {
                            "target_id": item.req_id,
                            "target_phase": "Q04",
                            "action": "补充技术方案覆盖",
                            "description": f"{item.req_id}: {item.description}",
                            "current_status": item.coverage_status or "UNKNOWN",
                        }
                    )
        # GAP 闭环率
        if coverage.total_gaps > 0 and coverage.gap_closure_rate < 0.5:
            errors.append(
                f"RSM_COVERAGE: GAP 闭环率 {coverage.gap_closure_rate:.0%} "
                f"低于阈值 50%（{coverage.gaps_closed}/{coverage.total_gaps}）"
            )
            for item in lifecycle.values():
                if item.id_type == "GAP" and item.closure_status != "已闭环":
                    gap_tasks.append(
                        {
                            "target_id": item.req_id,
                            "target_phase": "Q04",
                            "action": "闭环 GAP",
                            "description": f"{item.req_id}: {item.description}",
                            "current_status": item.closure_status or "未闭环",
                        }
                    )

    if phase_id in ("Q05", "Q06") and coverage.total_ses > 0 and coverage.test_coverage_rate < 0.6:
        # B/C finalize 时：SE 应该有对应 EUT
        errors.append(
            f"RSM_COVERAGE: SE→EUT 测试覆盖率 {coverage.test_coverage_rate:.0%} "
            f"低于阈值 60%（{coverage.ses_with_eut}/{coverage.total_ses}）"
        )
        for item in lifecycle.values():
            if item.id_type == "SE" and not item.eut_ids:
                gap_tasks.append(
                    {
                        "target_id": item.req_id,
                        "target_phase": "Q05",
                        "action": "补充 EUT",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": "NO_EUT",
                    }
                )

    if phase_id == "Q07" and coverage.total_reqs > 0 and coverage.review_coverage_rate < 0.5:
        # D finalize 时：REQ 应该有对应 finding
        errors.append(
            f"RSM_COVERAGE: REQ→Finding 评审覆盖率 {coverage.review_coverage_rate:.0%} "
            f"低于阈值 50%（{coverage.reqs_with_finding}/{coverage.total_reqs}）"
        )
        for item in lifecycle.values():
            if item.id_type == "REQ" and not item.finding_ids:
                gap_tasks.append(
                    {
                        "target_id": item.req_id,
                        "target_phase": "Q07",
                        "action": "补充代码评审",
                        "description": f"{item.req_id}: {item.description}",
                        "current_status": "NOT_REVIEWED",
                    }
                )

    # 保存补充任务文件（供下游 Phase 或 Adaptive Loop 消费）
    if gap_tasks:
        _save_gap_tasks(output_dir, project_id, phase_id, gap_tasks)

    return errors


def _save_gap_tasks(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    tasks: list[dict[str, Any]],
) -> None:
    """保存覆盖率缺口补充任务."""
    from dqg.core.state_machine import PHASE_DEFS
    from dqg.core.state_machine import phase_dir as _phase_dir
    from dqg.json_utils import save_json

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return
    pd = _phase_dir(output_dir, project_id, phase_def)
    pd.mkdir(parents=True, exist_ok=True)
    path = pd / "_coverage_gap_tasks.json"
    save_json(path, {"phase_id": phase_id, "tasks": tasks})
