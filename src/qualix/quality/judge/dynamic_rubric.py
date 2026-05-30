"""动态 Judge grading criteria：根据 Phase A SE 类型分布生成针对性评分维度.

静态 rubric 作为基线，动态维度根据项目实际的 SE 分布追加。
例如：项目有大量金额类 SE → 追加"金额精度验证"维度；
有并发类 SE → 追加"并发安全覆盖"维度。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

from qualix.json_utils import load_json
from qualix.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

# SE 描述关键词 → 业务域分类
_SE_DOMAIN_PATTERNS: Final = MappingProxyType(
    {
        "金额精度": ["金额", "BigDecimal", "精度", "分", "元", "费用", "价格", "总额"],
        "并发安全": ["并发", "幂等", "锁", "竞争", "冲突", "重复提交"],
        "状态机": ["状态机", "状态流转", "状态迁移", "驳回", "审批"],
        "权限隔离": ["权限", "隔离", "越权", "鉴权", "角色"],
        "超时补偿": ["超时", "重试", "降级", "熔断", "补偿"],
        "回调通知": ["回调", "通知", "消息", "推送", "事件"],
        "数据一致性": ["一致性", "多入口", "同步", "对齐", "冗余", "口径"],
        "外部依赖": ["外部", "中台", "第三方", "BPM"],
        "异常恢复": ["失败", "回滚", "撤销", "异常", "兜底", "回退"],
    }
)

# 每个业务域对应的动态评分维度模板
# fail_threshold: 维度得分低于此值时整体 verdict 被降为 FAIL（不受加权平均稀释）
_DYNAMIC_DIMENSION_TEMPLATES: Final[dict[str, dict[str, Any]]] = {
    "金额精度": {
        "id": "dyn_amount_precision",
        "name": "金额精度验证",
        "description": "涉及金额计算的 SE 是否都有精度校验（BigDecimal、setScale、舍入模式）",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有金额类 SE 都有精确到分的验证，舍入模式明确",
            4: "90%+ 金额 SE 有精度验证",
            3: "主要金额 SE 有验证，但部分缺少舍入模式检查",
            2: "金额精度验证不足，存在 double 直接计算的风险",
            1: "几乎未验证金额精度",
        },
    },
    "并发安全": {
        "id": "dyn_concurrency",
        "name": "并发安全覆盖",
        "description": "涉及并发/幂等的 SE 是否都有对应的保护机制验证",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有并发类 SE 都有锁/幂等/事务隔离的验证",
            4: "90%+ 并发 SE 有保护机制验证",
            3: "主要并发场景已覆盖，但缺少竞争窗口分析",
            2: "并发安全验证不足",
            1: "几乎未验证并发安全",
        },
    },
    "状态机": {
        "id": "dyn_state_machine",
        "name": "状态机完整性",
        "description": "状态流转的合法性、非法跳转拦截是否都被验证",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有状态迁移路径（含非法路径）都有验证",
            4: "正向流转全覆盖，仅遗漏 1-2 个非法跳转",
            3: "主要流转已覆盖，但反向/跨状态跳转未验证",
            2: "状态机验证不完整",
            1: "几乎未验证状态流转",
        },
    },
    "权限隔离": {
        "id": "dyn_permission",
        "name": "权限隔离验证",
        "description": "越权访问、角色隔离是否都有对应的测试/审计",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有权限类 SE 都有越权测试和角色隔离验证",
            4: "90%+ 权限 SE 有验证",
            3: "主要权限场景已覆盖，但跨租户隔离未验证",
            2: "权限验证不足",
            1: "几乎未验证权限隔离",
        },
    },
    "超时补偿": {
        "id": "dyn_timeout",
        "name": "超时补偿机制",
        "description": "超时/重试/降级场景是否都有对应的验证",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有超时类 SE 都有降级行为和重试次数验证",
            4: "90%+ 超时 SE 有验证",
            3: "主要超时场景已覆盖，但补偿机制未验证",
            2: "超时验证不足",
            1: "几乎未验证超时场景",
        },
    },
    "回调通知": {
        "id": "dyn_callback",
        "name": "回调通知验证",
        "description": "回调/通知/事件发布是否都有调用验证（verify times）",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有回调类 SE 都有 verify(times(1)) 或等价验证",
            4: "90%+ 回调 SE 有验证",
            3: "主要回调已验证，但异步通知未验证",
            2: "回调验证不足",
            1: "几乎未验证回调通知",
        },
    },
    "数据一致性": {
        "id": "dyn_data_consistency",
        "name": "数据一致性口径",
        "description": "多入口/多表/异步数据的一致性口径是否明确且可验证",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有跨入口/跨表/跨系统 SE 都有字段级一致性口径（如 A 入口 vs B 入口的字段对齐规则）和可执行验证",
            4: "90%+ 一致性 SE 有明确口径和验证方法",
            3: "主要一致性场景有口径，但部分跨系统/异步一致性未明确",
            2: "一致性口径模糊，缺少字段级对齐规则",
            1: "几乎未明确一致性口径",
        },
    },
    "外部依赖": {
        "id": "dyn_external_dependency",
        "name": "外部依赖降级策略",
        "description": "PRD 涉及外部系统/中台/第三方时是否有业务级降级策略（用户看到什么、本地数据怎么处理）",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有外部依赖 SE 都明确了业务级降级：错误码/用户提示/本地兜底流",
            4: "90%+ 外部依赖 SE 有降级策略",
            3: "主要外部依赖有降级，但部分场景未定义超时行为",
            2: "降级策略不完整，用户可能看到技术错误栈",
            1: "几乎未定义外部依赖降级",
        },
    },
    "异常恢复": {
        "id": "dyn_error_recovery",
        "name": "异常恢复业务规则",
        "description": "失败/回滚/撤销场景下的业务规则是否明确（数据留/删、状态回退到哪、用户可否重试）",
        "weight": 0.15,
        "fail_threshold": 2,
        "rubric": {
            5: "所有失败/回滚/撤销 SE 都有明确业务规则（数据去向、状态回退目标、用户可否重试）",
            4: "90%+ 异常恢复 SE 有明确业务规则",
            3: "主要异常场景有规则，但部分失败后数据状态未定义",
            2: "异常恢复规则不完整，可能产生数据孤岛",
            1: "几乎未定义异常恢复规则",
        },
    },
}


# Q01 必查业务语义域：即使 SE 0 命中也生成对应维度，让 Judge 能打低分触发 fail_threshold
# 解决"生成侧失败导致评分侧盲区"问题——如 PRD 明显有 BPM 依赖但旧 SE 没触及关键词，
# 按默认生成逻辑 dyn_external_dependency 压根不生成，门限管不到。
_REQUIRED_DOMAINS: Final[tuple[str, ...]] = (
    "状态机",
    "并发安全",
    "外部依赖",
    "异常恢复",
    "数据一致性",
)


def classify_se_domains(se_list: list[dict[str, Any]]) -> dict[str, int]:
    """对 SE 列表按业务域分类，返回每个域的 SE 数量.

    Returns:
        {"金额精度": 5, "并发安全": 3, ...}
    """
    domain_counts: dict[str, int] = {}
    for se in se_list:
        desc = se.get("description", "")
        for domain, keywords in _SE_DOMAIN_PATTERNS.items():
            if any(kw in desc for kw in keywords):
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return domain_counts


def generate_dynamic_dimensions(
    output_dir: Path,
    project_id: str,
    phase_id: str,
    min_se_count: int = 2,
    required_domains: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """根据 Phase A SE 分布生成动态评分维度.

    Args:
        output_dir: 输出目录
        project_id: 项目 ID
        phase_id: 当前 Phase ID
        min_se_count: 某个域至少有多少个 SE 才生成对应维度
        required_domains: 必查维度白名单——即使 SE 0 命中也生成，让门限能管到
            默认使用 _REQUIRED_DOMAINS（Q01 核心 5 个业务语义域）

    Returns:
        动态维度列表（可追加到静态 rubric 的 dimensions 中）
    """
    from qualix.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP

    if required_domains is None:
        required_domains = _REQUIRED_DOMAINS

    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]

    se_list: list[dict[str, Any]] = []
    if phase_a_path.exists():
        data = load_json(phase_a_path)
        if data:
            se_list = data.get("semantic_expectations", [])

    domain_counts = classify_se_domains(se_list) if se_list else {}

    # 合并：所有命中过 min_se_count 的域 + 必查白名单（即使命中=0 也包含）
    selected_domains: set[str] = {d for d, c in domain_counts.items() if c >= min_se_count}
    selected_domains.update(required_domains)

    dynamic_dims: list[dict[str, Any]] = []
    # 先按命中数排序生成（命中多的优先），必查但 0 命中的排后面
    ordered = sorted(
        selected_domains,
        key=lambda d: (-domain_counts.get(d, 0), d),
    )
    for domain in ordered:
        template = _DYNAMIC_DIMENSION_TEMPLATES.get(domain)
        if not template:
            continue
        count = domain_counts.get(domain, 0)
        is_required = domain in required_domains
        dim = dict(template)
        marker = (
            "[必查" + (f", {count} SE 命中]" if count else ", 0 SE 命中 — 按门限兜底]")
            if is_required
            else f"[{count} SE]"
        )
        dim["description"] = f"{marker} {dim['description']}"
        dynamic_dims.append(dim)

    if dynamic_dims:
        log.info(
            "Phase %s: 生成 %d 个动态评分维度 (%s)",
            phase_id,
            len(dynamic_dims),
            ", ".join(d["id"] for d in dynamic_dims),
        )

    return dynamic_dims


def enrich_rubric_with_dynamic_dimensions(
    rubric: dict[str, Any],
    dynamic_dims: list[dict[str, Any]],
    max_dynamic: int = 3,
) -> dict[str, Any]:
    """将动态维度追加到静态 rubric 中.

    动态维度最多追加 max_dynamic 个（按 SE 数量排序取 top），
    追加后重新归一化权重。

    Returns:
        增强后的 rubric（新对象，不修改原始）
    """
    if not dynamic_dims:
        return rubric

    enriched = {
        "name": rubric["name"],
        "dimensions": [dict(d) for d in rubric["dimensions"]],  # 深拷贝，避免修改原始
    }

    # 取 top N 动态维度
    to_add = dynamic_dims[:max_dynamic]
    existing_ids = {d["id"] for d in enriched["dimensions"]}
    for dim in to_add:
        if dim["id"] not in existing_ids:
            enriched["dimensions"].append(dim)

    # 重新归一化权重
    total_weight = sum(d["weight"] for d in enriched["dimensions"])
    if total_weight > 0:
        for d in enriched["dimensions"]:
            d["weight"] = d["weight"] / total_weight

    return enriched
