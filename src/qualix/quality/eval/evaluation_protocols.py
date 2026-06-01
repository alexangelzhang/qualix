"""Phase-level evaluation protocols: specialized checklists for Judge and Critique agents.

Research (PRISM/EMNLP/Wharton) shows specific checklists >> identity labels for LLM accuracy.
Each Phase's Judge and Critique gets specialized instructions instead of a generic persona.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class AgentProtocol:
    role_label: str  # routing label (NOT injected into prompt)
    checklist: tuple[str, ...]  # must-check items
    red_lines: tuple[str, ...]  # must-NOT-do items
    domain_vocab: dict[str, str] = field(default_factory=dict)
    focus_areas: tuple[str, ...] = field(default_factory=tuple)
    not_applicable: str = ""


@dataclass(frozen=True)
class PhaseProtocol:
    phase_id: str
    judge: AgentProtocol
    critique: AgentProtocol


# ---------------------------------------------------------------------------
# Q01 — 需求结构化
# ---------------------------------------------------------------------------
_Q01 = PhaseProtocol(
    phase_id="Q01",
    judge=AgentProtocol(
        role_label="需求完整性审查员",
        checklist=(
            "PRD 每个功能点是否提取为 REQ",
            "隐式业务规则是否显式化为 BR",
            "关键语义是否提取为可验证 SE",
            "模糊点是否标记为 GAP/OPEN",
            "边界约定（必须做/需确认/禁止做）是否完整",
        ),
        red_lines=(
            "不评估技术可行性",
            "不补充 PRD 未提及的需求",
            "不把正常业务流程当 GAP",
        ),
        domain_vocab={
            "REQ": "需求条目，从 PRD 功能点提取",
            "BR": "业务规则，显式或隐式的约束条件",
            "SE": "语义元素，可验证的业务规则",
            "GAP": "需求缺口，PRD 中模糊或缺失的定义",
            "OPEN": "待确认项，需要业务方决策",
        },
        focus_areas=(
            "并发幂等隐式语义",
            "金额精度隐式约束",
            "状态机边界条件",
        ),
    ),
    critique=AgentProtocol(
        role_label="需求盲区挖掘员",
        checklist=(
            "是否遗漏了并发/幂等场景的隐式需求",
            "是否遗漏了安全/权限相关的隐式约束",
            "是否遗漏了性能/容量相关的非功能需求",
            "GAP 是否把正常业务流程误判为缺口",
        ),
        red_lines=(
            "不重复 Judge 已发现的问题",
            "不编造 PRD 未暗示的需求",
        ),
        focus_areas=(
            "隐式需求挖掘（并发/幂等/安全/性能）",
            "跨模块依赖遗漏",
            "边界条件未覆盖",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q02 — 技术方案生成
# ---------------------------------------------------------------------------
_Q02 = PhaseProtocol(
    phase_id="Q02",
    judge=AgentProtocol(
        role_label="方案完整性审查员",
        checklist=(
            "方案是否包含 HLD + LLD + DTO + 流程图 + 伪代码",
            "是否满足 AI 亲和性标准（完整到 AI 可直接编码）",
            "接口协议清单是否完整",
            "部署灰度方案是否明确",
        ),
        red_lines=(
            "不评估需求合理性",
            "不替代架构师做技术选型",
        ),
        domain_vocab={
            "HLD": "High-Level Design，高层设计",
            "LLD": "Low-Level Design，详细设计",
            "DTO": "Data Transfer Object，数据传输对象",
        },
        focus_areas=(
            "AI 亲和性",
            "接口完整性",
        ),
    ),
    critique=AgentProtocol(
        role_label="方案落地性审查员",
        checklist=(
            "方案是否有未识别的外部依赖风险",
            "是否有引入技术债的设计决策",
            "运维成本是否被低估",
        ),
        red_lines=("不重复 Judge 已发现的问题",),
        focus_areas=(
            "依赖风险",
            "技术债",
            "运维成本",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q03 — 技术方案质量评审
# ---------------------------------------------------------------------------
_Q03 = PhaseProtocol(
    phase_id="Q03",
    judge=AgentProtocol(
        role_label="技术方案质量审查员",
        checklist=(
            "每个写操作是否有 Failure Mode 分析",
            "9 类异常分支是否逐类检查",
            "RPC 调用是否有超时重试降级",
            "数据一致性方案是否明确（事务/补偿/最终一致）",
            "SE 是否可直接转化为测试用例",
        ),
        red_lines=(
            "不评估需求合理性（Q01 的事）",
            "不建议具体技术选型（只审方案完整性）",
        ),
        domain_vocab={
            "Failure Mode": "故障模式，某个操作失败时的行为和恢复策略",
            "RPC": "Remote Procedure Call，远程过程调用",
            "补偿事务": "分布式场景下通过反向操作恢复一致性",
        },
        focus_areas=(
            "跨服务调用失败路径",
            "并发冲突处理",
            "资金安全设计",
        ),
    ),
    critique=AgentProtocol(
        role_label="级联失败猎手",
        checklist=(
            "是否存在跨服务级联失败路径未被识别",
            "是否存在数据不一致时间窗口",
            "是否有单点故障未被冗余设计覆盖",
        ),
        red_lines=(
            "不重复 Judge 已发现的问题",
            "不质疑已确认的架构决策",
        ),
        focus_areas=(
            "跨服务级联失败",
            "数据不一致窗口",
            "单点故障",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q04 — 技术方案覆盖度审计
# ---------------------------------------------------------------------------
_Q04 = PhaseProtocol(
    phase_id="Q04",
    judge=AgentProtocol(
        role_label="覆盖度审计员",
        checklist=(
            "每条 REQ/BR/SE 是否在技术方案中有对应设计",
            "COVERED 判定是否有具体设计证据（不是仅提到接口名）",
            "MISSING 是否真的缺失",
            "技术方案中超出 PRD 范围的设计是否标记为 NEW_DESIGN",
        ),
        red_lines=(
            "不评估技术方案质量（Q03 的事）",
            "不把 PARTIAL 乐观判为 COVERED",
        ),
        domain_vocab={
            "COVERED": "需求在技术方案中有完整设计",
            "PARTIAL": "需求在技术方案中有部分设计，缺少异常/边界",
            "MISSING": "需求在技术方案中完全缺失",
            "NEW_DESIGN": "技术方案中有但 PRD 未要求的设计",
        },
        focus_areas=(
            "异常分支覆盖",
            "反向审计（方案有但需求没有）",
        ),
    ),
    critique=AgentProtocol(
        role_label="隐式覆盖猎手",
        checklist=(
            "是否存在代码里有但方案没写的隐式覆盖",
            "是否存在过度设计（方案远超需求范围）",
            "COVERED 判定是否有乐观偏差",
        ),
        red_lines=("不重复 Judge 已发现的问题",),
        focus_areas=(
            "隐式覆盖识别",
            "过度设计检测",
            "乐观偏差纠正",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q06 — 单测覆盖审计
# ---------------------------------------------------------------------------
_Q06 = PhaseProtocol(
    phase_id="Q06",
    judge=AgentProtocol(
        role_label="覆盖审计员",
        checklist=(
            "每条 EUT 的覆盖状态判定是否正确",
            "弱断言是否标记为 WRONG_TARGET",
            "T1 核心异常分支是否有测试",
            "测试数据是否覆盖真实故障组合（多记录/边界值/枚举组合）",
        ),
        red_lines=(
            "不评估测试代码风格",
            "不把 assertNotNull 判为 COVERED",
            "团队有意的模式冲突标记 CONFLICT 而非误判",
        ),
        domain_vocab={
            "WRONG_TARGET": "测试存在但断言目标错误（弱断言）",
            "CONFLICT": "团队有意的模式与审计标准冲突，交人工裁决",
            "T1": "Tier 1，核心业务路径",
        },
        focus_areas=(
            "弱断言检测",
            "场景覆盖质量",
            "增量覆盖率",
        ),
    ),
    critique=AgentProtocol(
        role_label="巧合正确猎手",
        checklist=(
            "是否存在 Mock 返回固定值恰好通过的巧合正确",
            "是否存在断言目标偏移（验证了返回值但没验证业务语义）",
            "是否存在测试间隐式依赖（执行顺序影响结果）",
        ),
        red_lines=("不重复 Judge 已发现的问题",),
        focus_areas=(
            "巧合正确检测",
            "断言目标偏移",
            "测试隔离性",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q07 — 代码评审
# ---------------------------------------------------------------------------
_Q07 = PhaseProtocol(
    phase_id="Q07",
    judge=AgentProtocol(
        role_label="代码审查员",
        checklist=(
            "每个 finding 是否有具体文件:行号证据",
            "REQ/BR/SE 在代码中的实现是否完整",
            "改动点的完整调用链是否追踪（Controller→Service→Domain→Gateway）",
            "blast radius 内的 callers/tests 是否评估",
            "严重级别分级是否合理",
        ),
        red_lines=(
            "不评估代码风格偏好",
            "不做影响评估（留给 approve 阶段）",
            "每轮独立评审不考虑历史改进",
        ),
        domain_vocab={
            "blast radius": "代码改动的影响范围（受影响的调用方和测试）",
            "BLOCKER": "阻断级问题，必须修复才能合并",
            "MAJOR": "重要问题，应在本次修复",
            "MINOR": "次要问题，可后续修复",
        },
        focus_areas=(
            "需求-代码对齐",
            "调用链路完整性",
            "blast radius 感知",
        ),
    ),
    critique=AgentProtocol(
        role_label="安全与性能盲区猎手",
        checklist=(
            "是否存在未被发现的安全风险（注入/越权/信息泄露）",
            "是否存在性能瓶颈（N+1 查询/大对象序列化/锁竞争）",
            "是否存在向后兼容破坏（接口变更/数据迁移）",
        ),
        red_lines=(
            "不重复 Judge 已发现的问题",
            "不评估代码风格",
        ),
        focus_areas=(
            "安全风险",
            "性能瓶颈",
            "向后兼容破坏",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q05a — EUT 矩阵设计
# ---------------------------------------------------------------------------
_Q05a = PhaseProtocol(
    phase_id="Q05a",
    judge=AgentProtocol(
        role_label="EUT矩阵设计审查员",
        checklist=(
            "每条 REQ/BR/SE 是否有对应 EUT（bound_item 非空）",
            "Happy Path + Exception + Boundary 三种路径是否均覆盖",
            "then 字段是否包含具体断言描述（非「验证成功」类模糊描述）",
            "git diff 变更的实现类是否全部出现在 EUT 的 when 字段中",
            "并发/幂等语义的 SE 是否有对应多线程 EUT",
        ),
        red_lines=(
            "不接受「验证成功/结果正确」类模糊 then，必须含方法名或具体期望值",
            "不允许按 SE 汇总（SE-based 模式），必须 EUT 逐条对应",
        ),
        domain_vocab={
            "EUT": "Expected Unit Test，预期单测条目，含 when/then/route_type/bound_item",
            "bound_item": "EUT 绑定的 SE/REQ ID，标识被测需求来源",
            "C10": "git diff 覆盖 gate：每个变更实现类必须有 EUT",
        },
        focus_areas=(
            "EUT覆盖完备性",
            "then具体性",
            "git_diff覆盖",
        ),
    ),
    critique=AgentProtocol(
        role_label="测试设计盲区猎手",
        checklist=(
            "是否遗漏了并发/幂等/分布式锁相关的异常 EUT",
            "边界条件（null/空集/最大值）是否有专项 EUT",
            "Mock 层级策略是否合理（不过度 Mock 导致脆弱设计）",
        ),
        red_lines=("不重复 Judge 已发现的问题",),
        focus_areas=(
            "并发幂等盲区",
            "边界条件盲区",
            "Mock策略风险",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Q05b — 单测代码生成（judge_required=False，本 protocol 供手动 judge 使用）
# ---------------------------------------------------------------------------
_Q05b = PhaseProtocol(
    phase_id="Q05b",
    judge=AgentProtocol(
        role_label="单测代码质量审查员",
        checklist=(
            "每条 EUT 是否有对应 @Test 方法（// EUT-xxx 追溯注释）",
            "断言是否验证业务语义（不是 assertNotNull/assertTrue(true)）",
            "代码是否能通过编译（无幻觉方法名/缺失 import）",
            "@Test 方法是否忠实实现 EUT 的 when/then 规格，未越权修改 EUT 矩阵",
        ),
        red_lines=(
            "不接受 assertNotNull 冒充覆盖",
            "不允许 Q05b 修改 Q05a 的 EUT 矩阵",
        ),
        domain_vocab={
            "C9": "EUT 实现完整性 gate：每条 EUT 必须有 @Test 方法",
            "弱断言": "assertNotNull/assertTrue(true) 等不验证业务语义的断言",
        },
        focus_areas=(
            "编译可行性",
            "断言强度",
            "EUT忠实度",
        ),
    ),
    critique=AgentProtocol(
        role_label="测试可维护性审查员",
        checklist=(
            "Mock 数据是否贴近真实业务（不是全用默认值/null）",
            "测试数据是否覆盖已知故障路径（边界值/多记录场景）",
            "是否存在过度 Mock 导致测试脆弱",
        ),
        red_lines=("不重复 Judge 已发现的问题",),
        focus_areas=(
            "Mock真实性",
            "测试数据质量",
            "可维护性",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Registry + helpers
# ---------------------------------------------------------------------------
PHASE_PROTOCOLS: Final[dict[str, PhaseProtocol]] = {
    "Q01": _Q01,
    "Q02": _Q02,
    "Q03": _Q03,
    "Q04": _Q04,
    "Q05a": _Q05a,
    "Q05b": _Q05b,
    "Q06": _Q06,
    "Q07": _Q07,
}


def get_protocol(phase_id: str) -> PhaseProtocol | None:
    return PHASE_PROTOCOLS.get(phase_id)


def render_protocol_for_prompt(protocol: AgentProtocol) -> str:
    """Render as markdown for prompt injection. NO role_label in output."""
    parts: list[str] = []

    parts.append("## 检查清单（必须逐条检查）")
    parts.append("")
    for item in protocol.checklist:
        parts.append(f"- {item}")
    parts.append("")

    parts.append("## 行为红线（绝对不能做）")
    parts.append("")
    for item in protocol.red_lines:
        parts.append(f"- {item}")
    parts.append("")

    if protocol.domain_vocab:
        parts.append("## 领域词汇")
        parts.append("")
        for term, definition in protocol.domain_vocab.items():
            parts.append(f"- **{term}**: {definition}")
        parts.append("")

    if protocol.focus_areas:
        parts.append("## 重点检查方向")
        parts.append("")
        for area in protocol.focus_areas:
            parts.append(f"- {area}")
        parts.append("")

    if protocol.not_applicable:
        parts.append(f"> 不适用条件: {protocol.not_applicable}")
        parts.append("")

    return "\n".join(parts)
