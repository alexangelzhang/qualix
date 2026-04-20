"""Dashboard 常量定义与工具函数."""

from __future__ import annotations

from pathlib import Path

from dqg.constants import LEGACY_PHASE_ID_MAP as LEGACY_PHASE_MAP, PHASE_DIR_MAP as PHASE_DIR
from dqg.json_utils import load_json

OUTPUT_DIR = Path("output")

PHASE_NAMES = {
    "Q01": "需求结构化",
    "Q02": "技术方案生成",
    "Q03": "技术方案质量评审",
    "Q04": "技术方案覆盖度审计",
    "Q05": "单测生成",
    "Q06": "单测覆盖审计",
    "Q07": "代码评审",
}

STATUS_LABEL = {
    "approved": "已完成",
    "skipped": "已跳过",
    "pending_review": "待审核",
    "in_progress": "执行中",
    "not_started": "未开始",
}

STATUS_COLOR = {
    "approved": "#28a745",
    "skipped": "#6c757d",
    "pending_review": "#ffc107",
    "in_progress": "#17a2b8",
    "not_started": "#dee2e6",
}

DAG_COMMENT_TRANSLATE = {
    "FAIL": "未通过",
    "PASS": "通过",
    "WARN": "警告",
    "SKIP": "已跳过",
    "BLOCKED": "阻断",
    "CRITICAL_GAP": "严重缺口",
    "CRITICAL_GAPS": "严重缺口",
    "HIGH_GAP": "高危缺口",
    "MISSING": "缺失",
    "PARTIAL": "部分覆盖",
    "with": "共",
}

EVAL_METRIC_ZH = {
    "req_count": "需求点数", "br_count": "业务规则数", "se_count": "SE 数",
    "gap_count": "缺口数", "open_count": "待确认数",
    "se_with_basis": "SE 有依据率", "gap_with_risk": "GAP 有风险率",
    "open_with_owner": "OPEN 有负责人率",
    "critical_count": "严重问题数", "important_count": "重要问题数",
    "total_issues": "问题总数", "fm_count": "Failure Mode 数",
    "req_coverage_rate": "需求覆盖率", "se_coverage_rate": "SE 覆盖率",
    "gap_closure_rate": "GAP 闭环率", "missing_count": "未覆盖数",
}

EVAL_STATUS_ZH = {
    "NEW": "首次", "OK": "正常", "IMPROVED": "改善",
    "REGRESSION": "退化", "WARNING": "警告",
}

EVAL_STATUS_COLOR = {
    "NEW": "#6c757d", "OK": "#28a745", "IMPROVED": "#17a2b8",
    "REGRESSION": "#dc3545", "WARNING": "#ffc107",
}

DIM_NAMES = {
    "REQ": "需求覆盖",
    "BR": "业务规则",
    "SE": "场景覆盖",
    "GAP": "缺口项",
    "OPEN": "待确认项",
}

SEV_ZH = {
    "CRITICAL": "严重",
    "HIGH": "高",
    "MEDIUM": "中",
    "LOW": "低",
    "BLOCKER": "阻断",
    "MAJOR": "主要",
    "MINOR": "次要",
    "INFO": "建议",
}

UT_STATUS_ZH = {
    "COVERED": "已覆盖",
    "MISSING": "未覆盖",
    "PARTIAL": "部分覆盖",
    "CONFLICT": "冲突",
}


def _normalize_phase_id(pid: str) -> str:
    """将旧格式 phase_id 转换为 Q01-Q07 格式。"""
    return LEGACY_PHASE_MAP.get(str(pid), str(pid))


def _format_dag_comment(comment: str, max_len: int = 40) -> str:
    """翻译英文状态词并截断 DAG 备注。"""
    if not comment:
        return ""
    result = comment
    for en, zh in DAG_COMMENT_TRANSLATE.items():
        result = result.replace(en, zh)
    if len(result) > max_len:
        result = result[:max_len] + "…"
    return result


def _load_phase_scoring(output_dir: Path, pid: str, qid: str) -> dict:
    """加载某个 Phase 的全量评分数据。优先用 Q01-Q07 目录，不存在则 fallback 到旧 A-D 目录。"""
    dir_suffix = PHASE_DIR.get(qid)
    if not dir_suffix:
        return {}

    # 旧格式目录（A, A.3, A.5, A.6, B, C, D）
    legacy_dir_suffix = PHASE_DIR.get(qid, dir_suffix)

    # 优先新目录，fallback 旧目录
    candidate_dirs = []
    new_dir = output_dir / pid / dir_suffix / "_internal"
    legacy_dir = output_dir / pid / legacy_dir_suffix / "_internal"
    if new_dir.exists():
        candidate_dirs.append(new_dir)
    if legacy_dir != new_dir and legacy_dir.exists():
        candidate_dirs.append(legacy_dir)

    result = {"qid": qid}
    for internal in candidate_dirs:
        if "bundle" not in result:
            bundle_path = internal / "_verification_bundle.json"
            if bundle_path.exists():
                result["bundle"] = load_json(bundle_path)
        if "eval" not in result:
            eval_path = internal / "_eval_metrics.json"
            if eval_path.exists():
                result["eval"] = load_json(eval_path)
        if "judge" not in result:
            judge_path = internal / "_judge_result.json"
            if judge_path.exists():
                result["judge"] = load_json(judge_path)

    return result
