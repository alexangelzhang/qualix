"""测试数据模式推导：从 bug case 提取真实故障的数据组合模式.

分析历史 bug case 中的失败场景，提取"什么样的测试数据能触发这类 bug"，
生成 Data Pattern 库注入 Phase B EUT 生成和 Phase C 审计。

解决 Layer 3 场景 gap：测试数据不覆盖真实故障组合。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dqg.json_utils import save_json
from dqg.log import get_logger
from dqg.tracking.bug_cases import load_cases_by_phase
from dqg.tracking.lesson_inference import get_case_with_inferred_lesson

log = get_logger(__name__)


# 数据模式定义：关键词 → 模式名 → 测试数据建议
_DATA_PATTERNS: list[dict[str, Any]] = [
    {
        "id": "DP-FIELD-MAPPING",
        "name": "字段映射/转换",
        "keywords": ["字段", "映射", "转换", "赋值", "新增字段", "字段取值"],
        "description": "新增/修改字段的映射和转换逻辑",
        "test_data_suggestions": [
            "构造包含所有新增字段的完整对象（不能只传必填字段）",
            "构造字段值为边界值的对象（空串、最大长度、特殊字符）",
            "构造源对象和目标对象字段名不一致的场景（驼峰 vs 下划线）",
            "构造嵌套对象中的字段映射（如 order.address.city）",
        ],
    },
    {
        "id": "DP-ENUM-STATE",
        "name": "枚举/状态组合",
        "keywords": ["枚举", "状态", "类型", "分类", "状态流转", "非法"],
        "description": "枚举值组合和状态流转的边界",
        "test_data_suggestions": [
            "构造每种枚举值的测试数据（不能只测默认值）",
            "构造非法枚举值（null、空串、不存在的值）",
            "构造状态流转的每条边（包括反向/驳回/循环）",
            "构造多个枚举字段的组合（如 orderType=REFUND + status=PENDING）",
        ],
    },
    {
        "id": "DP-NULL-EMPTY",
        "name": "空值/null 边界",
        "keywords": ["空", "null", "blank", "判空", "空指针", "NPE", "NullPointer"],
        "description": "空值和 null 的边界处理",
        "test_data_suggestions": [
            "必填字段传 null",
            '字符串字段传空串 ""',
            "集合字段传空集合 Collections.emptyList()",
            "嵌套对象为 null（如 order.getAddress() 返回 null）",
            "Optional 字段的 empty 场景",
        ],
    },
    {
        "id": "DP-MULTI-RECORD",
        "name": "多记录/批量",
        "keywords": ["批量", "多条", "多个", "列表", "集合", "多记录", "批处理"],
        "description": "多记录场景的数据组合",
        "test_data_suggestions": [
            "构造 0 条记录（空集合）",
            "构造 1 条记录（单条）",
            "构造多条记录（3-5 条，包含不同状态/类型的混合）",
            "构造同一 key 的多条记录（如同一 orderId 多条明细）",
            "构造超过分页大小的记录数",
        ],
    },
    {
        "id": "DP-BOUNDARY",
        "name": "数值/长度边界",
        "keywords": ["边界", "最大", "最小", "溢出", "长度", "越界", "范围", "精度"],
        "description": "数值和长度的边界条件",
        "test_data_suggestions": [
            "数值字段：0、负数、最大值、最小值、小数精度边界",
            "字符串字段：空串、1 字符、最大长度、超最大长度",
            "金额字段：0.00、0.01（最小正值）、999999.99（最大值）",
            "日期字段：跨天边界（23:59:59 → 00:00:00）、跨月、跨年",
            "分页参数：page=0、page=-1、pageSize=0、pageSize=MAX",
        ],
    },
    {
        "id": "DP-CONCURRENT",
        "name": "并发/重复",
        "keywords": ["并发", "重复", "幂等", "冲突", "竞争", "重复提交"],
        "description": "并发和重复请求的数据场景",
        "test_data_suggestions": [
            "同一请求连续发送两次（幂等性验证）",
            "同一资源的并发修改（乐观锁冲突）",
            "构造已存在的唯一键数据（重复插入）",
            "构造版本号不匹配的更新请求",
        ],
    },
    {
        "id": "DP-SORT-PAGE",
        "name": "排序/分页",
        "keywords": ["排序", "分页", "翻页", "order by", "limit"],
        "description": "排序和分页的边界场景",
        "test_data_suggestions": [
            "构造排序字段值相同的多条记录（稳定性验证）",
            "构造跨页边界的数据（第 N 页最后一条 vs 第 N+1 页第一条）",
            "构造排序字段为 null 的记录",
            "构造总数恰好等于 pageSize 的场景",
        ],
    },
    {
        "id": "DP-PERMISSION",
        "name": "权限/角色",
        "keywords": ["权限", "角色", "越权", "租户", "隔离"],
        "description": "权限和数据隔离的测试数据",
        "test_data_suggestions": [
            "构造不同角色的用户数据（admin vs normal）",
            "构造跨租户的数据访问请求",
            "构造无权限用户的操作请求",
            "构造权限刚好在边界的用户（如只有读权限尝试写操作）",
        ],
    },
]


def match_data_patterns(case: dict[str, Any]) -> list[str]:
    """匹配单个 case 涉及的数据模式.

    Returns:
        匹配的 pattern ID 列表
    """
    title = case.get("title", "")
    tags = " ".join(case.get("tags", []))
    actual = str(case.get("actual", ""))
    lesson = case.get("lesson", "")
    text = f"{title} {tags} {actual} {lesson}"

    matched: list[str] = []
    for pattern in _DATA_PATTERNS:
        if any(kw in text for kw in pattern["keywords"]):
            matched.append(pattern["id"])
    return matched


def analyze_data_patterns(phase: str | None = None) -> dict[str, Any]:
    """分析 bug case 库中的数据模式分布.

    Returns:
        {
            "total_cases": N,
            "pattern_distribution": {"DP-FIELD-MAPPING": 18, ...},
            "top_patterns": [{"id": "...", "count": N, "suggestions": [...]}],
            "cases_by_pattern": {"DP-FIELD-MAPPING": ["case_id1", ...], ...},
        }
    """
    raw_cases = load_cases_by_phase(phase) if phase else load_cases_by_phase("Q06")
    cases = [get_case_with_inferred_lesson(c) for c in raw_cases]

    from dqg.constants import DATA_PATTERN_LESSON_MAX_CHARS, DATA_PATTERN_TOP_LESSONS

    pattern_counter: Counter = Counter()
    cases_by_pattern: dict[str, list[str]] = defaultdict(list)
    lessons_by_pattern: dict[str, list[str]] = defaultdict(list)

    for case in cases:
        matched = match_data_patterns(case)
        for pid in matched:
            pattern_counter[pid] += 1
            cases_by_pattern[pid].append(case.get("case_id", ""))
            lesson = (case.get("lesson") or "").strip()
            if lesson:
                lessons_by_pattern[pid].append(lesson[:DATA_PATTERN_LESSON_MAX_CHARS])

    top_patterns = []
    for pid, count in pattern_counter.most_common():
        pattern_def = next((p for p in _DATA_PATTERNS if p["id"] == pid), None)
        if pattern_def:
            top_patterns.append(
                {
                    "id": pid,
                    "name": pattern_def["name"],
                    "count": count,
                    "suggestions": pattern_def["test_data_suggestions"],
                    "example_cases": cases_by_pattern[pid][:3],
                    "top_lessons": list(dict.fromkeys(lessons_by_pattern[pid]))[:DATA_PATTERN_TOP_LESSONS],
                }
            )

    return {
        "total_cases": len(cases),
        "pattern_distribution": dict(pattern_counter),
        "top_patterns": top_patterns,
        "cases_by_pattern": {k: v[:5] for k, v in cases_by_pattern.items()},
    }


def _render_data_pattern_context(
    analysis: dict[str, Any],
    max_patterns: int = 5,
) -> str:
    """渲染数据模式为 Markdown（内部函数，避免重复调用 analyze）."""
    if not analysis.get("top_patterns"):
        return ""

    lines = [
        "## DATA_PATTERNS — 历史故障数据模式（自动推导）",
        "",
        "以下数据模式从历史 bug case 中提取，生成/审计测试时请确保覆盖这些场景。",
        "",
    ]

    for pattern in analysis["top_patterns"][:max_patterns]:
        lines.append(f"### {pattern['id']}: {pattern['name']}（{pattern['count']} 次历史故障）")
        lines.append("")
        lines.append("测试数据建议：")
        for suggestion in pattern["suggestions"]:
            lines.append(f"- {suggestion}")
        lines.append("")

    return "\n".join(lines)


def write_data_patterns(
    output_dir: Path,
    project_id: str,
    phase_id: str,
) -> Path | None:
    """生成数据模式文件到 Phase 目录.

    Returns:
        写入的文件路径
    """
    analysis = analyze_data_patterns(phase_id)
    if not analysis["top_patterns"]:
        return None

    from dqg.constants import PHASE_DIR_MAP

    dir_suffix = PHASE_DIR_MAP.get(phase_id, f"phase{phase_id}")
    phase_dir = output_dir / project_id / dir_suffix

    int_dir = phase_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    # JSON 版本
    json_path = int_dir / "_data_patterns.json"
    save_json(json_path, analysis)

    # Markdown 版本（复用已有的 analysis，不重新调用 analyze_data_patterns）
    md_path = int_dir / "_data_patterns.md"
    md_path.write_text(_render_data_pattern_context(analysis), encoding="utf-8")

    log.info("Data patterns: %d patterns from %d cases", len(analysis["top_patterns"]), analysis["total_cases"])
    return json_path
