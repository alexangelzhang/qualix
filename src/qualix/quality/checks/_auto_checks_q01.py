"""Q01 专属 auto_check 函数（auto_checks.py 内部实现模块，不直接被外部调用）."""

from __future__ import annotations

import contextlib
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pydantic import BaseModel

from qualix.core.phase_registry import PHASE_DEFS
from qualix.core.state_machine import internal_dir as _internal_dir
from qualix.core.state_machine import phase_dir as _phase_dir
from qualix.json_utils import load_json, save_json
from qualix.log import get_logger
from qualix.text_utils import STRUCTURED_JSON_MAP

log = get_logger(__name__)

_SOURCE_LINE_RE = re.compile(r":(\d+)$")

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
    from qualix.core.state_machine import phase_dir as _pd
    from qualix.json_utils import load_json

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
    from qualix.core.state_machine import phase_dir as _pd
    from qualix.json_utils import load_json

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
