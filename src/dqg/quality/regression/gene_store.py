"""Gene Store: Critique 反馈结晶为可复用的评审基因.

核心概念：
- Gene: 从高置信度 Critique 中提取的结构化策略模板
  (target_pattern + error_type + action + patch_template)
- Capsule: 成功的 Critique→修正 快照，作为 few-shot 示例

匹配机制：新 Phase 执行时，用代码/需求模式匹配已有 Gene，
命中则直接注入 context，减少 LLM 重复推理。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

log = get_logger(__name__)

GENE_DIR = "regression/genes"
CAPSULE_DIR = "regression/capsules"

# Gene 提取的最低置信度
GENE_MIN_CONFIDENCE = "medium"
GENE_MIN_IMPACT = "medium"

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
_IMPACT_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


# ---------------------------------------------------------------------------
# Gene 数据结构
# ---------------------------------------------------------------------------


def _make_gene_id(phase_id: str, error_type: str, idx: int) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"GENE-{phase_id}-{error_type}-{ts}-{idx:02d}"


def extract_genes_from_preference(
    preference: dict[str, Any],
    critique: dict[str, Any],
    phase_id: str,
    project_id: str,
    agent_role: str = "judge",
) -> list[dict[str, Any]]:
    """从 preference + critique 结果中提取 Gene.

    只提取满足条件的高价值 critique：
    - preference.preferred == "v2"（修正版更好）
    - critique_effectiveness.was_valid == True
    - critique_effectiveness.should_persist == True
    - impact >= medium, confidence >= medium
    """
    if preference.get("preferred") != "v2":
        return []

    confidence = preference.get("confidence", "low")
    if _CONFIDENCE_ORDER.get(confidence, 0) < _CONFIDENCE_ORDER["medium"]:
        return []

    effectiveness = preference.get("critique_effectiveness", [])
    issues = critique.get("issues_found", [])

    # 建立 critique issue → detail 的映射
    issue_map: dict[str, dict[str, Any]] = {}
    for issue in issues:
        desc = issue.get("description", "")
        if desc:
            issue_map[desc[:80]] = issue

    genes: list[dict[str, Any]] = []
    for idx, eff in enumerate(effectiveness):
        if not eff.get("was_valid") or not eff.get("should_persist"):
            continue
        impact = eff.get("impact", "none")
        if _IMPACT_ORDER.get(impact, 0) < _IMPACT_ORDER[GENE_MIN_IMPACT]:
            continue

        critique_issue = eff.get("critique_issue", "")
        # 尝试匹配原始 critique detail
        detail = issue_map.get(critique_issue[:80], {})

        gene = {
            "gene_id": _make_gene_id(phase_id, detail.get("type", "FN"), idx),
            "phase_id": phase_id,
            "agent_role": agent_role,
            "error_type": detail.get("type", "FN"),
            "severity": detail.get("severity", impact),
            "target_pattern": _extract_pattern(critique_issue, detail),
            "description": critique_issue,
            "action": detail.get("suggestion", ""),
            "evidence": detail.get("evidence", ""),
            "confidence": confidence,
            "impact": impact,
            "source": {
                "project_id": project_id,
                "phase_id": phase_id,
                "extracted_at": datetime.now().isoformat(),
            },
            "match_count": 0,
            "last_matched_at": None,
        }
        genes.append(gene)

    return genes


def _extract_pattern(description: str, detail: dict[str, Any]) -> str:
    """从 critique 描述中提取可匹配的模式.

    优先用 evidence 中的关键词，fallback 到描述中的名词短语。
    """
    evidence = detail.get("evidence", "") or description

    # 提取中文关键词（2-8字的名词短语）
    cn_patterns = re.findall(r"[\u4e00-\u9fff]{2,8}", evidence)
    # 提取英文标识符（CamelCase, snake_case）
    en_patterns = re.findall(r"[A-Z][a-zA-Z]+|[a-z]+_[a-z_]+", evidence)

    patterns = list(dict.fromkeys(cn_patterns[:3] + en_patterns[:3]))
    return "|".join(patterns) if patterns else description[:60]


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def save_genes(
    base_dir: Path,
    genes: list[dict[str, Any]],
    project_id: str | None = None,
) -> list[str]:
    """保存 Gene 到文件系统。

    project_id 不为空时写入隔离路径 regression/genes/{phase_id}/{project_id}/。
    """
    if not genes:
        return []

    saved: list[str] = []
    for gene in genes:
        phase_id = gene.get("phase_id", "unknown")
        gene_id = gene["gene_id"]
        if project_id:
            gene_dir = base_dir / GENE_DIR / phase_id / project_id
        else:
            gene_dir = base_dir / GENE_DIR / phase_id
        gene_dir.mkdir(parents=True, exist_ok=True)
        save_json(gene_dir / f"{gene_id}.json", gene)
        saved.append(gene_id)
        log.info("Gene saved: %s", gene_id)

    return saved


def format_genes_for_injection(genes: list[dict[str, Any]], max_genes: int = 10) -> str:
    """将 Gene 格式化为可注入 Worker/Judge prompt 的简洁文本。

    与 render_genes_for_prompt 不同，这里面向 adaptive loop 的 prompt prefix，
    更简洁（每条 Gene 一行），token 增量 ≤ 800。
    """
    if not genes:
        return ""

    top = genes[:max_genes]
    lines = [
        "## 历史 Gene（来自本项目过往成功修正，优先关注）",
        "",
    ]
    for gene in top:
        desc = gene.get("description", "")[:80]
        gene_id = gene.get("gene_id", "")
        matched = gene.get("match_count", 0)
        lines.append(f"- [{gene_id}] {desc}" + (f" [命中 {matched} 次]" if matched else ""))

    lines.append("")
    return "\n".join(lines)


def _build_preference_from_pass(
    iteration_record: Any,
    project_id: str,
    phase_id: str,
) -> dict[str, Any]:
    """从 IterationRecord 构造 preference dict，用于 Gene 提取。

    adaptive loop 没有真正的 Preference LLM 调用，
    用 passed=True 代理 preferred='v2'，置信度设为 medium。
    """
    critique_data = {}
    if iteration_record.critique_result and iteration_record.critique_result.status != "failed":
        import json as _json
        try:
            critique_data = _json.loads(iteration_record.critique_result.content)
        except (ValueError, AttributeError):
            pass

    issues = critique_data.get("issues_found", [])
    effectiveness = [
        {
            "critique_issue": issue.get("description", ""),
            "was_valid": True,
            "should_persist": True,
            "impact": issue.get("severity", "medium"),
        }
        for issue in issues
        if issue.get("description")
    ]

    return {
        "preferred": "v2",
        "confidence": "medium",
        "critique_effectiveness": effectiveness,
    }


def save_capsule(
    base_dir: Path,
    phase_id: str,
    project_id: str,
    critique: dict[str, Any],
    preference: dict[str, Any],
) -> str | None:
    """保存成功的 Critique→修正 快照为 Capsule."""
    if preference.get("preferred") != "v2":
        return None

    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    capsule_id = f"CAP-{phase_id}-{ts}"
    capsule = {
        "capsule_id": capsule_id,
        "phase_id": phase_id,
        "project_id": project_id,
        "created_at": datetime.now().isoformat(),
        "critique_summary": critique.get("summary", ""),
        "issues_found": len(critique.get("issues_found", [])),
        "preference": preference.get("preferred", ""),
        "confidence": preference.get("confidence", ""),
        "effectiveness": preference.get("critique_effectiveness", []),
    }

    capsule_dir = base_dir / CAPSULE_DIR / phase_id
    capsule_dir.mkdir(parents=True, exist_ok=True)
    save_json(capsule_dir / f"{capsule_id}.json", capsule)
    log.info("Capsule saved: %s", capsule_id)
    return capsule_id


# ---------------------------------------------------------------------------
# 匹配
# ---------------------------------------------------------------------------


def load_genes_for_phase(
    base_dir: Path,
    phase_id: str,
    agent_role: str | None = None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """加载指定 Phase 的 Gene。

    project_id 不为空时走隔离路径 regression/genes/{phase_id}/{project_id}/，
    为空时走共享路径 regression/genes/{phase_id}/（向后兼容）。
    """
    gene_dir = base_dir / GENE_DIR / phase_id
    if project_id:
        project_gene_dir = gene_dir / project_id
        if project_gene_dir.exists():
            gene_dir = project_gene_dir
        elif not gene_dir.exists():
            return []
    elif not gene_dir.exists():
        return []

    genes: list[dict[str, Any]] = []
    for p in sorted(gene_dir.glob("GENE-*.json")):
        gene = load_json(p)
        if gene:
            genes.append(gene)

    if agent_role:
        genes = [g for g in genes if g.get("agent_role", "judge") == agent_role]
    return genes


def match_genes(
    genes: list[dict[str, Any]],
    context_text: str,
    max_matches: int = 5,
) -> list[dict[str, Any]]:
    """用 Gene 的 target_pattern 匹配上下文文本.

    Returns:
        匹配到的 Gene 列表（按 impact 降序），最多 max_matches 个。
    """
    if not genes or not context_text:
        return []

    matched: list[dict[str, Any]] = []
    for gene in genes:
        pattern = gene.get("target_pattern", "")
        if not pattern:
            continue

        # pattern 是 "|" 分隔的关键词，任一命中即匹配
        keywords = [kw.strip() for kw in pattern.split("|") if kw.strip()]
        hit = any(kw in context_text for kw in keywords)
        if hit:
            matched.append(gene)

    # 按 impact 降序排序
    matched.sort(key=lambda g: _IMPACT_ORDER.get(g.get("impact", "none"), 0), reverse=True)
    return matched[:max_matches]


def render_genes_for_prompt(
    matched_genes: list[dict[str, Any]],
) -> str:
    """将匹配到的 Gene 渲染为可注入 prompt 的文本."""
    if not matched_genes:
        return ""

    lines = [
        "## 评审基因（历史 Critique 结晶）",
        "",
        "以下是从历史评审中提取的高价值模式，请特别关注：",
        "",
    ]
    for i, gene in enumerate(matched_genes, 1):
        lines.append(f"### Gene {i}: {gene.get('gene_id', '')}")
        lines.append(f"- 错误类型: {gene.get('error_type', '')}")
        lines.append(f"- 严重度: {gene.get('severity', '')}")
        lines.append(f"- 问题: {gene.get('description', '')}")
        if gene.get("action"):
            lines.append(f"- 建议: {gene['action']}")
        if gene.get("evidence"):
            lines.append(f"- 历史证据: {gene['evidence'][:200]}")
        lines.append("")

    return "\n".join(lines)
