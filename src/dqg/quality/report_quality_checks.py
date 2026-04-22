"""报告产物质量确定性检测 — 正则驱动，零 LLM 调用.

6 类硬性规则检测：
1. 来源标注缺失 — 结论行无 [来源: xxx] 标记
2. ID 格式违规 — REQ/BR/SE/GAP/OPEN 不符合 XXX-nnn 格式
3. GAP 缺风险等级 — GAP 条目无 P0/P1/P2 标注
4. 置信度缺失 — 结论无 High/Medium/Low 标注
5. 推理日志空壳 — 缺少关键步骤标记（Step N）
6. OPEN 缺决策方 — OPEN 条目无决策方标注

注册为 finalize handler（order=55），输出 _report_quality_checks.json。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dqg.core.state_machine import PHASE_DEFS, phase_dir as _phase_dir
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger
from dqg.path_utils import resolve_internal_file
from dqg.text_utils import REPORT_MAP, STRUCTURED_JSON_MAP

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# [来源: xxx] 或 [来源：xxx] 或 [Source: xxx]
_SOURCE_PATTERN = re.compile(r"\[来源[:：]\s*.+?\]|\[Source:\s*.+?\]", re.IGNORECASE)

# 合法 ID 格式: REQ-001, BR-002, SE-003, GAP-004, OPEN-005
_VALID_ID_PATTERN = re.compile(r"\b(REQ|BR|SE|GAP|OPEN)-\d{1,4}\b")

# 非法 ID: REQ_xxx, REQ xxx, req-xxx（小写）等
_INVALID_ID_PATTERN = re.compile(
    r"\b(REQ|BR|SE|GAP|OPEN)[_\s]\d+\b"  # 下划线或空格分隔
    r"|\b(req|br|se|gap|open)-\d+\b",     # 全小写
)

# 风险等级: P0/P1/P2
_RISK_LEVEL_PATTERN = re.compile(r"\bP[012]\b")

# 置信度: High/Medium/Low
_CONFIDENCE_PATTERN = re.compile(r"\b(High|Medium|Low)\b", re.IGNORECASE)

# 推理日志步骤标记: Step 0, Step 1, ... 或 ## Step
_STEP_PATTERN = re.compile(r"(?:^|\n)\s*#{1,3}\s*Step\s+\d", re.IGNORECASE)

# 决策方标记: 常见模式
_DECISION_OWNER_PATTERN = re.compile(
    r"决策方|负责人|Owner|Assignee|待.*确认|需.*决定",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 检测函数
# ---------------------------------------------------------------------------

def check_source_annotations(report_text: str) -> list[dict[str, Any]]:
    """检测结论行是否缺少来源标注."""
    issues = []
    # 找到包含判定性词汇的行
    conclusion_patterns = re.compile(
        r"(缺失|遗漏|未覆盖|不完整|风险|问题|建议|BLOCKER|CRITICAL|WARNING"
        r"|COVERED|NOT_COVERED|PARTIAL|WRONG_TARGET|CONFLICT)",
    )
    for i, line in enumerate(report_text.splitlines(), 1):
        if conclusion_patterns.search(line) and not _SOURCE_PATTERN.search(line):
            # 跳过表头、分隔线、空行
            stripped = line.strip()
            if stripped.startswith("|") and "---" in stripped:
                continue
            if stripped.startswith("#") or not stripped:
                continue
            # 跳过纯标签行（如 severity: HIGH）
            if ":" in stripped and len(stripped.split()) <= 3:
                continue
            issues.append({
                "check": "source_annotation",
                "line": i,
                "message": f"结论行缺少来源标注 [来源: 文件名:行号]",
                "content": stripped[:120],
            })
    return issues


def check_id_format(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    """检测 ID 格式是否合规."""
    issues = []

    def _scan_ids(items: list, field_name: str, expected_prefix: str):
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("req_id", "se_id", "gap_id", "open_id", "id"):
                val = item.get(key, "")
                if not val or not isinstance(val, str):
                    continue
                if expected_prefix and not val.startswith(expected_prefix):
                    issues.append({
                        "check": "id_format",
                        "message": f"{field_name} 中 ID '{val}' 不符合 {expected_prefix}-NNN 格式",
                        "id": val,
                    })
                elif not _VALID_ID_PATTERN.match(val):
                    issues.append({
                        "check": "id_format",
                        "message": f"{field_name} 中 ID '{val}' 格式不合规",
                        "id": val,
                    })

    # 扫描各类 ID
    _scan_ids(structured_data.get("requirements", []), "requirements", "")
    _scan_ids(structured_data.get("semantic_expectations", []), "semantic_expectations", "SE")
    _scan_ids(structured_data.get("gaps", []), "gaps", "GAP")
    _scan_ids(structured_data.get("open_items", []), "open_items", "OPEN")

    return issues


def check_gap_risk_level(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    """检测 GAP 条目是否标注了风险等级 P0/P1/P2."""
    issues = []
    for gap in structured_data.get("gaps", []):
        if not isinstance(gap, dict):
            continue
        gap_id = gap.get("gap_id", gap.get("id", "?"))
        severity = str(gap.get("severity", gap.get("risk_level", "")))
        description = str(gap.get("description", ""))
        # 检查 severity 字段或描述中是否有 P0/P1/P2
        if not _RISK_LEVEL_PATTERN.search(severity) and not _RISK_LEVEL_PATTERN.search(description):
            issues.append({
                "check": "gap_risk_level",
                "message": f"GAP {gap_id} 缺少风险等级标注（P0/P1/P2）",
                "id": gap_id,
            })
    return issues


def check_open_decision_owner(structured_data: dict[str, Any]) -> list[dict[str, Any]]:
    """检测 OPEN 条目是否标注了决策方."""
    issues = []
    for item in structured_data.get("open_items", []):
        if not isinstance(item, dict):
            continue
        open_id = item.get("open_id", item.get("id", "?"))
        # 检查所有文本字段
        text_fields = " ".join(
            str(item.get(k, ""))
            for k in ("description", "decision_owner", "owner", "assignee", "note")
        )
        if not _DECISION_OWNER_PATTERN.search(text_fields) and not item.get("decision_owner"):
            issues.append({
                "check": "open_decision_owner",
                "message": f"OPEN {open_id} 缺少决策方标注",
                "id": open_id,
            })
    return issues


def check_reasoning_log_quality(phase_dir: Path) -> list[dict[str, Any]]:
    """检测推理日志内容质量（不只是存在性，finalize_checks 已检查存在性）."""
    issues = []
    log_path = resolve_internal_file(phase_dir, "_reasoning_log.md")
    if not log_path.exists():
        return []  # 存在性由 finalize_checks 检查

    content = log_path.read_text(encoding="utf-8")
    lines = content.strip().splitlines()

    # 检查步骤标记数量
    step_matches = _STEP_PATTERN.findall(content)
    if len(step_matches) < 3:
        issues.append({
            "check": "reasoning_log_quality",
            "message": f"推理日志仅包含 {len(step_matches)} 个 Step 标记（建议至少 3 个）",
            "step_count": len(step_matches),
        })

    # 检查是否有实质性内容（不只是标题）
    content_lines = [
        l for l in lines
        if l.strip() and not l.strip().startswith("#") and not l.strip().startswith("---")
    ]
    if len(content_lines) < 10:
        issues.append({
            "check": "reasoning_log_quality",
            "message": f"推理日志实质内容仅 {len(content_lines)} 行（建议至少 10 行）",
            "content_lines": len(content_lines),
        })

    return issues


def check_confidence_annotations(report_text: str, phase_id: str) -> list[dict[str, Any]]:
    """检测报告中是否有置信度标注."""
    # 只对 Q01/Q04/Q03 检查（这些 Phase 要求置信度标注）
    if phase_id not in ("Q01", "Q04", "Q03"):
        return []

    issues = []
    # 检查整篇报告是否至少有一些置信度标注
    confidence_count = len(_CONFIDENCE_PATTERN.findall(report_text))
    # 检查结论行数量
    conclusion_patterns = re.compile(
        r"(COVERED|NOT_COVERED|PARTIAL|缺失|遗漏|未覆盖|风险)",
    )
    conclusion_lines = [
        l for l in report_text.splitlines()
        if conclusion_patterns.search(l)
    ]

    if conclusion_lines and confidence_count == 0:
        issues.append({
            "check": "confidence_annotation",
            "message": f"报告包含 {len(conclusion_lines)} 条结论但无置信度标注（High/Medium/Low）",
            "conclusion_count": len(conclusion_lines),
        })

    return issues


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def run_report_quality_checks(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """运行所有报告质量确定性检测.

    Returns:
        检测结果 dict，包含 issues 列表和统计信息
    """
    phase_def = PHASE_DEFS.get(phase_id)
    if not phase_def:
        return {"phase_id": phase_id, "issues": [], "total": 0}

    pd = _phase_dir(output_dir, project_id, phase_def)
    all_issues: list[dict[str, Any]] = []

    # 1. 读取报告文本
    report_file = REPORT_MAP.get(phase_id)
    report_text = ""
    if report_file:
        report_path = pd / report_file
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8")

    # 2. 读取结构化 JSON
    json_file = STRUCTURED_JSON_MAP.get(phase_id)
    structured_data: dict[str, Any] = {}
    if json_file:
        json_path = pd / json_file
        if json_path.exists():
            structured_data = load_json(json_path) or {}

    # 3. 运行各项检测
    if report_text:
        all_issues.extend(check_source_annotations(report_text))
        all_issues.extend(check_confidence_annotations(report_text, phase_id))

    if structured_data:
        all_issues.extend(check_id_format(structured_data))
        all_issues.extend(check_gap_risk_level(structured_data))
        all_issues.extend(check_open_decision_owner(structured_data))

    all_issues.extend(check_reasoning_log_quality(pd))

    # 4. 按 check 类型统计
    by_check: dict[str, int] = {}
    for issue in all_issues:
        check_name = issue.get("check", "unknown")
        by_check[check_name] = by_check.get(check_name, 0) + 1

    return {
        "phase_id": phase_id,
        "project_id": project_id,
        "issues": all_issues,
        "total": len(all_issues),
        "by_check": by_check,
    }
