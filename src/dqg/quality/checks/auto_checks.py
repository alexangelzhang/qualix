"""AutoHarness: 从 Pydantic schema + phase_registry 自动推导 finalize 校验.

自动生成的校验覆盖：
1. Schema 校验：JSON 产物是否符合 Pydantic 数据契约
2. 交叉引用校验：GAP/OPEN 的 related_ids 是否指向存在的 REQ/BR
3. 完整性校验：approve_checklist 中可自动验证的条目
4. 严重等级校验：GAP/Issue 是否标注了严重等级（当 schema 有 severity 字段时）
"""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

if TYPE_CHECKING:
    from pydantic import BaseModel

from pydantic import ValidationError

from dqg.core.phase_registry import PHASE_DEFS
from dqg.core.state_machine import phase_dir as _phase_dir
from dqg.json_utils import load_json
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

        # --- Q01-1: SE/BR source 行号内容交叉验证（L1↔L0，最强反幻觉）---
        if phase_id == "Q01":
            errors.extend(_check_source_line_reality(output_dir, project_id, phase_id))

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


_SOURCE_LINE_RE = re.compile(r":(\d+)$")
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
    """Q01-1+Q01-4: SE/BR 的 source 行号内容与 plain_text.txt 交叉验证.

    L1（SE/BR 声明）↔ L0（PRD 原文）：
    - SE.source = "plain_text.txt:79" → 读第 79 行及附近 ±3 行
    - 检查描述关键词是否出现在该上下文里
    - 行号超出文件长度 → WARNING（幽灵行号）
    - 关键词完全不出现 → WARNING（声明与原文不符）
    """
    from dqg.core.state_machine import phase_dir as _pd
    from dqg.json_utils import load_json

    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return []
    pd = _pd(output_dir, project_id, phase_def)
    plain_text_path = pd / "plain_text.txt"
    if not plain_text_path.exists():
        return []  # 无 PRD 原文，跳过（飞书未 ingest 的场景）

    try:
        lines = plain_text_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    if not json_file:
        return []
    data = load_json(pd / json_file)
    if not data:
        return []

    errors: list[str] = []

    def _check_item(item_id: str, description: str, source: str) -> None:
        if not source:
            return
        m = _SOURCE_LINE_RE.search(source)
        if not m:
            return
        line_no = int(m.group(1))
        if line_no < 1 or line_no > len(lines):
            errors.append(
                f"WARNING: Q01 {item_id} source 行号 {line_no} 超出 plain_text.txt 总行数 {len(lines)}，疑似幽灵行号。"
            )
            return
        # 取 ±3 行上下文
        context = "\n".join(lines[max(0, line_no - 4) : line_no + 3])
        keywords = _extract_keywords(description)
        matched = [kw for kw in keywords if kw in context]
        if keywords and len(matched) < _MIN_KEYWORD_MATCH:
            errors.append(
                f"WARNING: Q01 {item_id} source 行号 {line_no} 附近内容"
                f"不含描述关键词（{keywords[:3]}），疑似 source 行号虚报。"
                "请核实来源是否正确。"
            )

    # 验证 SE.source
    for se in data.get("semantic_expectations", []):
        _check_item(se.get("se_id", "SE-?"), se.get("description", ""), se.get("source", ""))

    # 验证 BR.source（Q01-4，对称）
    for req in data.get("requirements", []):
        if str(req.get("req_id", "")).startswith("BR"):
            _check_item(req.get("req_id", "BR-?"), req.get("description", ""), req.get("source", ""))

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
