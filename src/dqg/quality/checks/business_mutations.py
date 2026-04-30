"""业务域变异测试推导：从 Phase A SE 自动推导针对性变异规则.

根据 SE 的业务类型（金额/状态机/并发等）生成对应的变异算子，
输出追加到 Phase C 的 mutation context 中，供 LLM 做针对性审计。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from dqg.constants import PHASE_DIR_MAP, STRUCTURED_JSON_MAP
from dqg.json_utils import load_json, save_json
from dqg.log import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)


# SE 描述中的关键词 → 业务域变异规则
_BUSINESS_MUTATION_RULES: Final[dict[str, dict[str, Any]]] = {
    "金额精度": {
        "keywords": ["金额", "BigDecimal", "精度", "分", "元", "费用", "价格", "总额", "单价"],
        "operator": "DECIMAL_PRECISION",
        "description": "金额精度丢失变异",
        "mutations": [
            "BigDecimal.setScale(2, RoundingMode.HALF_UP) → setScale(0, RoundingMode.DOWN)",
            "BigDecimal.valueOf(amount) → new BigDecimal(amount)  // double 精度丢失",
            "删除 setScale() 调用",
            "HALF_UP → HALF_DOWN / FLOOR / CEILING",
        ],
        "kill_condition": "断言必须精确到分（0.01），不能用 assertEquals(expected, actual) 不带 delta",
    },
    "状态机跳转": {
        "keywords": ["状态机", "状态流转", "状态迁移", "驳回", "审批", "流程"],
        "operator": "STATE_TRANSITION_SKIP",
        "description": "状态机非法跳转变异",
        "mutations": [
            "删除中间状态校验（如 PENDING → APPROVED 跳过 REVIEWING）",
            "允许反向流转（APPROVED → PENDING）",
            "删除 StatusTransition.validate() 调用",
            "将状态枚举值替换为相邻值",
        ],
        "kill_condition": "断言必须验证状态流转的合法性，assertThrows 必须检查具体错误码",
    },
    "并发安全": {
        "keywords": ["并发", "幂等", "锁", "竞争", "重复提交", "乐观锁", "悲观锁", "分布式锁"],
        "operator": "LOCK_REMOVAL",
        "description": "并发保护移除变异",
        "mutations": [
            "删除 @Lock / synchronized / ReentrantLock.lock()",
            "删除 @Transactional 注解",
            "删除乐观锁版本号检查（WHERE version = ?）",
            "删除幂等键校验（idempotent key check）",
        ],
        "kill_condition": "并发测试必须验证重复调用的幂等性，或验证锁竞争时的异常",
    },
    "空值边界": {
        "keywords": ["校验", "必填", "非空", "NotNull", "NotBlank", "参数校验"],
        "operator": "NULL_INJECTION",
        "description": "空值注入变异",
        "mutations": [
            "将必填参数设为 null",
            '将字符串参数设为空串 ""',
            "将集合参数设为空集合 Collections.emptyList()",
            "删除 @NotNull / @NotBlank 注解",
        ],
        "kill_condition": "断言必须验证参数校验异常（ConstraintViolationException / IllegalArgumentException）",
    },
    "回调通知": {
        "keywords": ["回调", "通知", "消息", "推送", "事件", "MQ", "Kafka"],
        "operator": "VOID_CALLBACK_REMOVAL",
        "description": "回调/通知静默移除变异",
        "mutations": [
            "删除 notify() / sendMessage() / publish() 调用",
            "将异步回调改为空实现",
            "删除事件发布（EventPublisher.publish()）",
        ],
        "kill_condition": "必须用 Mockito.verify(times(1)) 验证通知确实被调用",
    },
    "超时补偿": {
        "keywords": ["超时", "重试", "降级", "熔断", "补偿", "Retry"],
        "operator": "TIMEOUT_BYPASS",
        "description": "超时/重试机制绕过变异",
        "mutations": [
            "将超时时间设为极大值（Integer.MAX_VALUE）",
            "删除重试逻辑（@Retryable / retry loop）",
            "删除降级 fallback 方法",
        ],
        "kill_condition": "必须验证超时场景下的降级行为和重试次数",
    },
}


def derive_mutations_from_se(
    se_list: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从 SE 列表推导业务域变异规则.

    Args:
        se_list: Phase A 的 semantic_expectations 列表

    Returns:
        变异规则列表，每条包含 se_id + 匹配的变异算子
    """
    results: list[dict[str, Any]] = []
    seen_operators: set[str] = set()

    for se in se_list:
        se_id = se.get("se_id", se.get("id", ""))
        desc = se.get("description", "")
        if not desc:
            continue

        desc_lower = desc.lower()
        matched_rules: list[dict[str, Any]] = []

        for rule_name, rule in _BUSINESS_MUTATION_RULES.items():
            if any(kw in desc or kw in desc_lower for kw in rule["keywords"]):
                matched_rules.append(
                    {
                        "rule_name": rule_name,
                        "operator": rule["operator"],
                        "description": rule["description"],
                        "mutations": rule["mutations"],
                        "kill_condition": rule["kill_condition"],
                    }
                )
                seen_operators.add(rule["operator"])

        if matched_rules:
            results.append(
                {
                    "se_id": se_id,
                    "se_description": desc[:100],
                    "matched_mutations": matched_rules,
                }
            )

    return results


def write_business_mutations(
    output_dir: Path,
    project_id: str,
) -> Path | None:
    """生成业务域变异规则并写入 Phase C 目录.

    Returns:
        写入的文件路径，或 None
    """
    phase_a_path = output_dir / project_id / PHASE_DIR_MAP["Q01"] / STRUCTURED_JSON_MAP["Q01"]
    if not phase_a_path.exists():
        return None

    phase_a_data = load_json(phase_a_path)
    if not phase_a_data:
        return None

    se_list = phase_a_data.get("semantic_expectations", [])
    if not se_list:
        return None

    mutations = derive_mutations_from_se(se_list)
    if not mutations:
        return None

    phase_c_dir = output_dir / project_id / PHASE_DIR_MAP["Q06"]
    phase_c_dir.mkdir(parents=True, exist_ok=True)
    int_dir = phase_c_dir / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)

    # JSON 版本
    json_path = int_dir / "_business_mutations.json"
    save_json(json_path, {"mutations": mutations, "total_se_matched": len(mutations)})

    # Markdown 版本供 LLM 引用
    md_path = int_dir / "_business_mutations.md"
    md_path.write_text(_render_mutations_markdown(mutations), encoding="utf-8")

    log.info("业务域变异规则已生成: %d 条 SE 匹配, 写入 %s", len(mutations), md_path)
    return json_path


def _render_mutations_markdown(mutations: list[dict[str, Any]]) -> str:
    """渲染变异规则为 Markdown."""
    lines = [
        "## BUSINESS_MUTATIONS — 业务域变异测试规则（自动推导）",
        "",
        "以下变异规则从 Phase A 的 SE 自动推导，审计时请针对性检查。",
        "",
    ]

    for item in mutations:
        lines.append(f"### {item['se_id']}: {item['se_description']}")
        lines.append("")
        for rule in item["matched_mutations"]:
            lines.append(f"**{rule['operator']}** — {rule['description']}")
            lines.append("")
            for mut in rule["mutations"]:
                lines.append(f"- 变异: {mut}")
            lines.append(f"- 杀死条件: {rule['kill_condition']}")
            lines.append("")

    return "\n".join(lines)
