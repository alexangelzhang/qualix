"""规则定义：预编译正则 + Phase 规则注册表.

从 rule_compliance.py 拆分，包含所有规则元数据和正则常量。
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# 预编译正则：避免在检查函数内重复编译
# ---------------------------------------------------------------------------

RE_CONFIDENCE = re.compile(
    r"\[置信度[:：]\s*(High|Medium|Low|高|中|低)\]"  # [置信度: High] 格式
    r"|置信度[:：]\s*(High|Medium|Low|高|中|低)"  # 置信度：High 格式
    r"|`(High|Medium|Low)`"  # `High` 格式
    r"|\|\s*(High|Medium|Low)\s*[\|（]"  # 表格单元格 | High |
    r"|\|\s*([高中低])\s*[\|（]"  # 表格单元格 | 高 |（中文）
)
RE_CONFIDENCE_D = re.compile(
    r"\[置信度[:：]\s*(High|Medium|Low|高|中|低)\]|置信度[:：]\s*(High|Medium|Low|高|中|低)"
    r'|`(High|Medium|Low)`|"confidence":\s*"(High|Medium|Low)"|BLOCKER|MAJOR|MINOR'
)
RE_UT_EUT = re.compile(r"\bUT-\d+|EUT-\d+|\bUT\b.*测试用例")
RE_GAP_TABLE_LINE = re.compile(r"\s*\|\s*GAP-\d+")
RE_GAP_DEF_LINE = re.compile(r"\s*GAP-\d+")
# 风险等级：P0/P1/P2 或表格单元格中的中文 高/中/低（限定 | 上下文，避免匹配"中间件"等词内字符）
RE_GAP_LEVEL = re.compile(r"P[012]|风险等级|\|\s*[高中低]\s*\|")
# 仅匹配 OPEN-ID 在首列的表格行，避免误匹配 SE/BR 等行中对 OPEN 的引用
RE_OPEN_TABLE_LINE = re.compile(r"\s*\|\s*OPEN-\d+")
RE_OPEN_DEF_LINE = re.compile(r"\s*OPEN-\d+")
RE_OPEN_OWNER = re.compile(r"决策方|产品|研发|业务|PM")
RE_SE_LINE = re.compile(r".*SE-\d+")
RE_COVERAGE_STATUS = re.compile(r"COVERED|PARTIAL|MISSING|IMPLICIT")
RE_COVERAGE_EVIDENCE = re.compile(r"来源|证据|DOC-\d+|第\d+行|技术方案|\d+:\d+|\.java")
RE_URL_DESIGN = re.compile(r"(?:URL|url)[：:]\s*`?(?:GET|POST|PUT|DELETE)\s+/")
RE_URL_FALLBACK = re.compile(r"/mtop/|/api/")
RE_STATE_ENUM = re.compile(r"状态[名枚]|码值|状态码|status.*\d+")
RE_REQ_ID = re.compile(r"REQ-\d+")
RE_BR_ID = re.compile(r"BR-\d+")
RE_SE_ID = re.compile(r"SE-\d+")


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------


def get_rules(phase_id: str) -> list[dict[str, Any]]:
    """获取 Phase 对应的规则检查项."""
    common = [
        {
            "id": "R-LOG",
            "name": "推理日志存在且有实质内容",
            "category": "流程",
            "check": "_check_reasoning_log",
        },
        {
            "id": "R-JUDGE",
            "name": "Judge/Critique 自我评审已执行",
            "category": "流程",
            "check": "_check_judge_critique",
        },
        {
            "id": "R-SOURCE",
            "name": "结论标注来源（文件名:行号）",
            "category": "反幻觉",
            "check": "_check_source_annotation",
        },
        {
            "id": "R-CONFIDENCE",
            "name": "结论标注置信度（High/Medium/Low）",
            "category": "反幻觉",
            "check": "_check_confidence_annotation",
        },
        {
            "id": "R-NO-UTEUT",
            "name": "未输出 UT/EUT（Phase A/A.5/A.6）",
            "category": "禁止",
            "check": "_check_no_ut_eut",
        },
    ]

    phase_specific: dict[str, list[dict[str, Any]]] = {
        "Q01": [
            {"id": "R-MERMAID", "name": "状态机/流程图已转为 Mermaid", "category": "图片", "check": "_check_mermaid"},
            {"id": "R-IMG-TABLE", "name": "图片资产表存在", "category": "图片", "check": "_check_image_table"},
            {
                "id": "R-BR-DETAIL",
                "name": "BR 包含完整字段（非概括性描述）",
                "category": "质量",
                "check": "_check_br_detail",
            },
            {
                "id": "R-GAP-LEVEL",
                "name": "GAP 标注风险等级（P0/P1/P2）",
                "category": "质量",
                "check": "_check_gap_level",
            },
            {"id": "R-OPEN-OWNER", "name": "OPEN 标注决策方", "category": "质量", "check": "_check_open_owner"},
            {"id": "R-SE-BASIS", "name": "SE 有判定依据", "category": "质量", "check": "_check_se_basis"},
        ],
        "Q04": [
            {
                "id": "R-COVERAGE-EVIDENCE",
                "name": "覆盖判定引用技术方案原文",
                "category": "质量",
                "check": "_check_coverage_evidence",
            },
            {
                "id": "R-GAP-CLOSURE",
                "name": "GAP/OPEN 闭环状态已检查",
                "category": "质量",
                "check": "_check_gap_closure",
            },
            {"id": "R-REVERSE-AUDIT", "name": "反向审计已完成", "category": "质量", "check": "_check_reverse_audit"},
        ],
        "Q03": [
            {
                "id": "R-FIVE-DIM",
                "name": "架构/接口/数据/异常/性能五维度已检查",
                "category": "质量",
                "check": "_check_five_dimensions",
            },
            {
                "id": "R-FAILURE-MODE",
                "name": "Failure Mode 分析已完成",
                "category": "质量",
                "check": "_check_failure_mode",
            },
        ],
        "Q02": [
            {"id": "R-DDL", "name": "DDL 完整（CREATE TABLE）", "category": "质量", "check": "_check_ddl"},
            {
                "id": "R-INTERFACE",
                "name": "接口设计完整（URL+入参+响应）",
                "category": "质量",
                "check": "_check_interface_design",
            },
            {
                "id": "R-STATE-MACHINE",
                "name": "状态机设计（如涉及）",
                "category": "质量",
                "check": "_check_state_machine",
            },
            {"id": "R-REUSE", "name": "现有代码复用分析", "category": "质量", "check": "_check_reuse_analysis"},
            {"id": "R-SLICE", "name": "实施切片建议", "category": "质量", "check": "_check_impl_slice"},
            {
                "id": "R-TRACEABILITY",
                "name": "Q01 的 REQ/BR 在技术方案中已追溯",
                "category": "可追溯性",
                "check": "_check_traceability",
            },
        ],
        "Q05": [
            {"id": "R-DESIGN-MATRIX", "name": "单测设计矩阵存在", "category": "流程", "check": "_check_design_matrix"},
            {"id": "R-REQ-COVERAGE", "name": "REQ 覆盖率 100%", "category": "质量", "check": "_check_req_coverage"},
            {"id": "R-BR-COVERAGE", "name": "BR 覆盖率 ≥80%", "category": "质量", "check": "_check_br_coverage"},
            {"id": "R-EUT-COUNT", "name": "EUT 数量充足（≥10）", "category": "质量", "check": "_check_eut_count"},
            {
                "id": "R-HAPPY-EXCEPTION",
                "name": "Happy/Exception 路径均衡",
                "category": "质量",
                "check": "_check_path_balance",
            },
            {"id": "R-SE-BOUND", "name": "SE 绑定覆盖", "category": "质量", "check": "_check_se_bound"},
            {
                "id": "R-STRONG-ASSERT",
                "name": "使用强断言（assertEquals 非 assertNotNull）",
                "category": "质量",
                "check": "_check_strong_assert",
            },
            {"id": "R-CODE-BRANCH", "name": "代码分支覆盖", "category": "质量", "check": "_check_code_branch_coverage"},
        ],
        "Q06": [
            {"id": "R-C-SE-COVERAGE", "name": "①SE覆盖率（≥80%）", "category": "质量", "check": "_check_c_se_coverage"},
            {
                "id": "R-C-PATH-BALANCE",
                "name": "②路径覆盖（Happy/Exception/Boundary均衡）",
                "category": "质量",
                "check": "_check_c_path_balance",
            },
            {
                "id": "R-C-ASSERT-STRENGTH",
                "name": "③断言强度（assertEquals验证业务字段）",
                "category": "质量",
                "check": "_check_c_assert_strength",
            },
            {
                "id": "R-C-MOCK-REALITY",
                "name": "④Mock真实性（贴近业务数据）",
                "category": "质量",
                "check": "_check_c_mock_reality",
            },
            {
                "id": "R-C-STATE-MACHINE",
                "name": "⑤状态机覆盖（迁移边测试）",
                "category": "质量",
                "check": "_check_c_state_machine",
            },
            {
                "id": "R-C-MAINTAINABILITY",
                "name": "⑥可维护性（Nested/DisplayName）",
                "category": "质量",
                "check": "_check_c_maintainability",
            },
            {
                "id": "R-C-BOUNDARY",
                "name": "⑦边界场景（空值/不存在/越界）",
                "category": "质量",
                "check": "_check_c_boundary",
            },
            {
                "id": "R-C-DEFENSIVE",
                "name": "⑧防御性测试（系统不崩溃）",
                "category": "质量",
                "check": "_check_c_defensive",
            },
        ],
    }

    rules = common.copy()
    rules.extend(phase_specific.get(phase_id, []))
    return rules
