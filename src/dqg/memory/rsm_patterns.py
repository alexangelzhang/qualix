"""Memory 驱动 RSM 进化：从历史项目提取高频 GAP 模式，注入新项目 Phase A.

闭环3: 项目完成后 → 提取 recurring patterns → 沉淀为 Memory → 下一个项目 Phase A 自动注入

用法：
    from dqg.memory.rsm_patterns import extract_gap_patterns, inject_patterns_for_phase_a
    patterns = extract_gap_patterns(output_dir, project_ids=["proj-a", "proj-b"])
    inject_patterns_for_phase_a(patterns)  # 写入 .dqg/MEMORY.md
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dqg.schemas.rsm import build_lifecycle, load_rsm


def extract_gap_patterns(
    output_dir: Path,
    project_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """从多个项目的 RSM 中提取高频 GAP 模式.

    Returns:
        按频率排序的 GAP 模式列表，每个包含 pattern/count/examples。
    """
    # 收集所有 GAP 的描述
    gap_descriptions: list[str] = []
    gap_by_project: dict[str, list[str]] = {}

    if project_ids is None:
        # 自动发现所有项目
        if output_dir.exists():
            project_ids = [
                d.name for d in output_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
        else:
            project_ids = []

    for pid in project_ids:
        lifecycle = load_rsm(output_dir, pid)
        gaps = [item for item in lifecycle.values() if item.id_type == "GAP"]
        descs = [g.description for g in gaps if g.description]
        gap_descriptions.extend(descs)
        if descs:
            gap_by_project[pid] = descs

    if not gap_descriptions:
        return []

    # 两层模式提取：
    # Layer 1: 种子关键词匹配（快速，高精度）
    # Layer 2: 语义相似度聚类（基于 n-gram 重叠，覆盖关键词遗漏的模式）

    keywords = Counter()
    _SEED_KEYWORDS = {
        "并发", "幂等", "超时", "异常", "回滚", "重试", "权限", "校验",
        "边界", "精度", "缓存", "一致性", "死锁", "溢出", "注入",
        "降级", "熔断", "限流", "监控", "告警", "日志",
    }

    # Layer 1: 种子关键词
    for desc in gap_descriptions:
        for kw in _SEED_KEYWORDS:
            if kw in desc:
                keywords[kw] += 1

    # Layer 2: 高频 bigram 提取（发现种子关键词未覆盖的模式）
    bigram_counter: Counter = Counter()
    for desc in gap_descriptions:
        chars = [c for c in desc if '\u4e00' <= c <= '\u9fff']  # 只取中文字符
        for i in range(len(chars) - 1):
            bigram = chars[i] + chars[i + 1]
            if bigram not in _SEED_KEYWORDS:  # 避免和种子重复
                bigram_counter[bigram] += 1

    # 高频 bigram 中筛选有意义的（出现 >= 3 次且不是停用词）
    _STOP_BIGRAMS = {"的是", "不是", "没有", "可以", "需要", "应该", "已经", "进行", "使用", "通过"}
    for bigram, count in bigram_counter.most_common(20):
        if count >= 3 and bigram not in _STOP_BIGRAMS:
            keywords[bigram] += count

    # 构建模式列表
    patterns: list[dict[str, Any]] = []
    for kw, count in keywords.most_common(15):
        if count < 2:
            continue  # 只保留出现 2 次以上的模式
        examples = [d for d in gap_descriptions if kw in d][:3]
        patterns.append({
            "pattern": kw,
            "count": count,
            "examples": examples,
            "projects": [pid for pid, descs in gap_by_project.items() if any(kw in d for d in descs)],
        })

    return patterns


def format_patterns_as_checklist(patterns: list[dict[str, Any]]) -> str:
    """将 GAP 模式格式化为 Phase A 的检查清单."""
    if not patterns:
        return ""

    lines = ["## 历史高频遗漏模式（自动从历史项目 RSM 提取）\n"]
    lines.append("以下模式在历史项目中反复出现为 GAP，请在需求结构化时主动检查：\n")

    for p in patterns:
        lines.append(f"- **{p['pattern']}**（{p['count']} 个项目出现）")
        for ex in p["examples"][:2]:
            lines.append(f"  - 例: {ex[:100]}")

    return "\n".join(lines)


def save_patterns_to_memory(patterns: list[dict[str, Any]]) -> bool:
    """将高频 GAP 模式沉淀到 .dqg/MEMORY.md（global 标签）."""
    if not patterns:
        return False

    mem_dir = Path(".dqg")
    mem_dir.mkdir(exist_ok=True)
    mem_file = mem_dir / "MEMORY.md"

    # 检查是否已有模式条目（避免重复追加）
    existing = ""
    if mem_file.exists():
        existing = mem_file.read_text(encoding="utf-8")

    new_entries: list[str] = []
    for p in patterns:
        entry = f"[global] 高频遗漏模式-{p['pattern']}: 在 {p['count']} 个项目中出现，注意检查"
        if entry not in existing:
            new_entries.append(f"- {entry}")

    if not new_entries:
        return False

    with open(mem_file, "a", encoding="utf-8") as f:
        f.write("\n".join(new_entries) + "\n")

    return True


def save_patterns_to_file(
    output_dir: Path,
    patterns: list[dict[str, Any]],
) -> Path:
    """保存模式到独立文件（供分析和审计）."""
    path = output_dir / ".dqg" / "rsm_patterns.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
