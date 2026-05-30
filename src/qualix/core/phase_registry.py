"""Phase 注册表：Qualix Domain 层的 Phase 定义.

所有 Phase 的元数据（名称、skill、依赖、输入、交付物、审批清单）
集中在此文件定义。state_machine.py 通过 import 引用，只负责状态流转机制。

分层定位：
- phase_registry.py = Domain 层（Qualix 业务知识）
- state_machine.py = Harness 层（通用状态机机制）

模型等级说明（recommended_model）：
- "strong": 需要深度理解和推理的 Phase（需求结构化、技术方案、代码评审）
- "standard": 模式化执行的 Phase（单测生成、覆盖度审计）
- 未指定时默认 "strong"
- Judge/Critique 始终使用 Judge 专用模型，不受此配置影响
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

# Phase 定义：Qualix 特有的业务元数据
PHASE_DEFS: Final = MappingProxyType(
    {
        "Q01": {
            "name": "需求结构化",
            "dir_suffix": "Q01",
            "skill": "skills/requirement-structuring/SKILL.md",
            "recommended_model": "strong",
            "reasoning_profile": {"planning": "high", "execution": "standard", "verification": "high"},
            "depends_on": [],
            "parallel_with": [],
            "required_inputs": [
                {"key": "prd", "label": "需求文档", "prompt": "PRD 路径或飞书链接", "required": True},
            ],
            "optional_inputs": [
                {"key": "images", "label": "补充图片目录", "prompt": "图片/原型图目录路径（没有直接回车跳过）"},
            ],
            "deliverables": [
                "phase_a_report.md — REQ/BR/SE + GAP + OPEN 结构化报告",
                "phase_a_structured.json — 机器可读的结构化产物",
            ],
            "approve_checklist": [
                "所有需求点已结构化为 REQ/BR",
                "关键语义已显式化为 SE",
                "缺口已记录为 GAP，待确认项已记录为 OPEN",
            ],
            "required_report_sections": [
                {"canonical": "需求清单", "aliases": ["REQ/BR 需求清单", "需求列表", "需求点"]},
                {"canonical": "SE 列表", "aliases": ["SE 关键语义清单", "关键语义", "SE List"]},
                {"canonical": "业务规则", "aliases": ["BR 业务规则", "Business Rules"]},
                {"canonical": "Gap 分析", "aliases": ["GAP 缺口清单", "缺口分析", "Gap Analysis"]},
                {"canonical": "评审结论", "aliases": ["结论", "Conclusion", "审查结论"]},
            ],
        },
        "Q02": {
            "name": "技术方案生成",
            "dir_suffix": "Q02",
            "skill": "skills/tech-design-generation/SKILL.md",
            "recommended_model": "strong",
            "reasoning_profile": {"planning": "high", "execution": "high", "verification": "high"},
            "depends_on": ["Q01"],
            "parallel_with": [],
            "skippable": True,
            "skip_condition": "已有技术方案文档时可跳过，直接进入 Q03 质量评审",
            "required_inputs": [],
            "optional_inputs": [
                {
                    "key": "existing_tech_design",
                    "label": "已有技术方案",
                    "prompt": "如已有技术方案文档，提供路径或飞书链接（提供则跳过生成，直接进入评审）",
                },
                {
                    "key": "code_repo",
                    "label": "代码仓库",
                    "prompt": "现有代码仓库路径，多个用逗号分隔（没有直接回车跳过）",
                },
                {
                    "key": "knowledge_base",
                    "label": "架构规范/知识库",
                    "prompt": "架构规范或知识库路径（没有直接回车跳过）",
                },
            ],
            "deliverables": [
                "tech_design.md — 技术方案文档（架构设计 + 接口设计 + 数据模型 + 异常处理）",
                "phase_a3_structured.json — 结构化技术方案",
            ],
            "approve_checklist": [
                "业务需求到技术方案的映射完整（每条 REQ/BR 有对应设计）",
                "架构设计符合 DDD + TMF 规范",
                "接口设计完整（含入参/出参/异常码/幂等性）",
                "数据模型设计合理（含索引/约束/扩展性）",
                "异常处理和边界条件已覆盖",
                "性能和扩展性已考虑",
            ],
            "required_report_sections": [
                {"canonical": "技术方案概述", "aliases": ["方案概述", "Technical Overview"]},
                {"canonical": "接口设计", "aliases": ["API Design", "接口协议"]},
                {"canonical": "数据模型", "aliases": ["Data Model", "DDL", "表结构"]},
                {"canonical": "阻断项", "aliases": ["Blockers", "阻断", "技术阻断"]},
            ],
        },
        "Q03": {
            "name": "技术方案质量评审",
            "dir_suffix": "Q03",
            "skill": "skills/tech-quality-review/SKILL.md",
            "recommended_model": "strong",
            "reasoning_profile": {"planning": "high", "execution": "standard", "verification": "high"},
            "depends_on": ["Q02"],
            "parallel_with": ["Q04"],
            "required_inputs": [
                {
                    "key": "tech_design",
                    "label": "技术方案文档",
                    "prompt": "技术方案路径或飞书链接（Q02 跳过时必填）",
                    "required": True,
                },
            ],
            "optional_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库(master/main分支)",
                    "prompt": "代码仓库路径，多个用逗号分隔（没有直接回车跳过）",
                },
                {
                    "key": "knowledge_base",
                    "label": "知识库",
                    "prompt": "架构规范或知识库路径（没有直接回车跳过）",
                },
            ],
            "deliverables": [
                "tech_design_quality_review.md — 质量评审报告（含调用链路图）",
                "phase_a6_structured.json — 结构化问题清单",
            ],
            "approve_checklist": [
                "架构/接口/数据/异常/性能五个维度已逐项检查",
                "改动功能点的完整 TMF 链路已梳理",
                "Failure Mode 分析已完成",
                "无 CRITICAL_GAP",
            ],
            "required_report_sections": [
                {"canonical": "质量问题", "aliases": ["Quality Issues", "问题列表"]},
                {"canonical": "异常场景", "aliases": ["Exception Scenarios", "异常分析"]},
            ],
        },
        "Q04": {
            "name": "技术方案覆盖度审计",
            "dir_suffix": "Q04",
            "skill": "skills/tech-coverage-audit/SKILL.md",
            "recommended_model": "standard",
            "reasoning_profile": {"planning": "standard", "execution": "standard", "verification": "high"},
            "depends_on": ["Q02"],
            "parallel_with": ["Q03"],
            "required_inputs": [
                {
                    "key": "tech_design",
                    "label": "技术方案文档",
                    "prompt": "技术方案路径或飞书链接（多个用逗号分隔）",
                    "required": True,
                },
            ],
            "optional_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库(master分支)",
                    "prompt": "代码仓库路径，多个用逗号分隔（没有直接回车跳过）",
                },
                {"key": "knowledge_base", "label": "知识库", "prompt": "知识库路径或飞书链接（没有直接回车跳过）"},
            ],
            "deliverables": [
                "tech_design_coverage_review.md — 覆盖度审计报告",
                "phase_a5_structured.json — 结构化覆盖矩阵",
            ],
            "approve_checklist": [
                "每条 REQ/SE 都已标注覆盖状态",
                "GAP/OPEN 闭环状态已检查",
                "反向审计已完成（NEW_DESIGN + NOT_IN_SCOPE）",
            ],
            "required_report_sections": [
                {"canonical": "覆盖度分析", "aliases": ["Coverage Analysis", "覆盖率"]},
                {"canonical": "BR 覆盖度", "aliases": ["BR Coverage", "BR覆盖", "分支需求覆盖"]},
                {"canonical": "缺失项", "aliases": ["Missing Items", "遗漏"]},
            ],
        },
        "Q05": {
            "name": "单测生成",
            "dir_suffix": "Q05",
            "skill": "skills/unit-test-generation/SKILL.md",
            "recommended_model": "standard",
            "reasoning_profile": {"planning": "high", "execution": "standard", "verification": "standard"},
            "depends_on": ["Q01"],
            "parallel_with": [],
            "required_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库",
                    "prompt": "代码仓库路径，多个用逗号分隔（本地路径或 Git URL）",
                    "required": True,
                },
                {
                    "key": "target_modules",
                    "label": "目标模块",
                    "prompt": "要生成单测的模块/类路径（多个用逗号分隔）",
                    "required": True,
                },
            ],
            "optional_inputs": [],
            "deliverables": [
                "eut_matrix.md — EUT 测试大纲",
                "phase_b_structured.json — 结构化 EUT 矩阵",
                "生成的单测代码文件",
            ],
            "approve_checklist": [
                "EUT 矩阵覆盖了所有 REQ/BR/SE",
                "单测代码使用强断言（非仅执行流程）",
                "异常路径有对应测试",
            ],
            "required_report_sections": [
                {"canonical": "测试用例清单", "aliases": ["单测用例", "Test Cases", "EUT Matrix"]},
                {"canonical": "覆盖率矩阵", "aliases": ["Coverage Matrix", "覆盖率"]},
            ],
            "judge_pass_threshold": 4.7,  # 单测生成质量要求高，高于其他 Phase 默认 3.5
        },
        "Q05a": {
            "name": "EUT 矩阵设计",
            "dir_suffix": "Q05a",
            "skill": "skills/unit-test-design/SKILL.md",
            "recommended_model": "strong",
            "reasoning_profile": {"planning": "high", "execution": "standard", "verification": "high"},
            "depends_on": ["Q01"],
            "parallel_with": [],
            "required_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库",
                    "prompt": "代码仓库路径，多个用逗号分隔（本地路径或 Git URL）",
                    "required": True,
                },
                {
                    "key": "target_modules",
                    "label": "目标模块",
                    "prompt": "要生成单测的模块/类路径（多个用逗号分隔）",
                    "required": True,
                },
            ],
            "optional_inputs": [],
            "deliverables": [
                "eut_matrix.md — EUT 测试大纲（人工 approve 后锁定为 Q05b 规格）",
                "phase_b_structured.json — 结构化 EUT 矩阵",
            ],
            "approve_checklist": [
                "三层驱动目标模块完整（se_mappings + br_mappings + git_diff_files 全部非空）",
                "每条 REQ/BR/SE 都有对应 EUT（bound_item 非空，100% 覆盖）",
                "git diff 每个实现类都出现在某条 EUT 的 when 字段（C10 无 BLOCKED）",
                "then 字段包含具体断言（非模糊描述）",
            ],
            "required_report_sections": [
                {"canonical": "测试用例清单", "aliases": ["单测用例", "Test Cases", "EUT Matrix"]},
                {"canonical": "目标模块", "aliases": ["Target Modules", "三层驱动"]},
            ],
            "judge_required": False,  # 退出条件是 C9/C10 确定性 gate，无 LLM judge rubric
        },
        "Q05b": {
            "name": "单测代码生成",
            "dir_suffix": "Q05b",
            "skill": "skills/unit-test-codegen/SKILL.md",
            "recommended_model": "standard",
            "reasoning_profile": {"planning": "standard", "execution": "standard", "verification": "high"},
            "depends_on": ["Q05a"],
            "judge_required": False,  # 退出条件是 C9+编译（确定性），不需要 LLM judge 评分
            "parallel_with": [],
            "required_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库",
                    "prompt": "代码仓库路径，多个用逗号分隔（含单测代码目录）",
                    "required": True,
                },
            ],
            "optional_inputs": [],
            "deliverables": [
                "生成的单测代码文件（每条 EUT 对应独立 @Test 方法，含 // EUT-xxx 追溯注释）",
                "codegen_progress.md — 生成进度报告",
                "phase_b_code_status.json — EUT 实现状态追踪（Ralph prd.json 等价）",
            ],
            "approve_checklist": [
                "C9: 所有 EUT 都有对应 @Test 方法（精确模式：EUT-xxx 追溯注释）",
                "C10: git diff 实现类全部有 EUT 覆盖（无 BLOCKED: Q05 git_diff_not_covered）",
                "编译通过（mvn test-compile），无幻觉方法名",
                "断言强度达标（无 try/catch 仅防 NPE 的弱断言）",
            ],
            "required_report_sections": [
                {"canonical": "生成进度", "aliases": ["EUT 实现状态", "Codegen Progress"]},
                {"canonical": "未覆盖 EUT", "aliases": ["MISSING", "待补充"]},
            ],
        },
        "Q06": {
            "name": "单测覆盖审计",
            "dir_suffix": "Q06",
            "skill": "skills/unit-test-audit/SKILL.md",
            "recommended_model": "standard",
            "reasoning_profile": {"planning": "standard", "execution": "standard", "verification": "high"},
            "depends_on": ["Q05b"],
            "parallel_with": [],
            "required_inputs": [
                {
                    "key": "code_repo",
                    "label": "代码仓库",
                    "prompt": "代码仓库路径，多个用逗号分隔（含单测代码）",
                    "required": True,
                },
                {
                    "key": "coverage_report",
                    "label": "覆盖率报告",
                    "prompt": "JaCoCo/覆盖率报告路径（没有直接回车跳过）",
                    "required": False,
                },
            ],
            "optional_inputs": [],
            "deliverables": [
                "ut_audit_report.md — 单测审计报告",
                "phase_c_structured.json — 结构化审计结果",
            ],
            "approve_checklist": [
                "覆盖率门禁达标（line >= 80%, branch >= 80%）",
                "T1 核心异常分支 100% 覆盖",
                "无 WRONG_TARGET 问题",
            ],
            "required_report_sections": [
                {"canonical": "审计结果", "aliases": ["Audit Results", "审计发现"]},
                {"canonical": "覆盖率分析", "aliases": ["Coverage Analysis", "覆盖率"]},
            ],
        },
        "Q07": {
            "name": "代码评审",
            "dir_suffix": "Q07",
            "skill": "skills/code-review/SKILL.md",
            "recommended_model": "strong",
            "reasoning_profile": {"planning": "high", "execution": "standard", "verification": "high"},
            "depends_on": ["Q04", "Q03"],
            "parallel_with": [],
            "required_inputs": [
                {"key": "code_repo", "label": "代码仓库", "prompt": "代码仓库路径，多个用逗号分隔", "required": True},
                {"key": "branch", "label": "评审分支", "prompt": "要评审的分支名（如 feature/xxx）", "required": True},
                {"key": "base_branch", "label": "基线分支", "prompt": "基线分支名（默认 master）", "required": False},
            ],
            "optional_inputs": [],
            "deliverables": [
                "review_report.md — 代码评审报告",
                "phase_d_structured.json — 结构化评审发现",
            ],
            "approve_checklist": [
                "所有 BLOCKER 级问题已修复",
                "REQ/BR/SEM → CODE/TEST 覆盖缺口已确认",
                "无未确认的自动修改",
            ],
            "required_report_sections": [
                {"canonical": "评审发现", "aliases": ["Review Findings", "发现列表"]},
                {"canonical": "需求代码对齐", "aliases": ["Req-Code Alignment", "对齐分析"]},
            ],
        },
    }
)

# Phase 执行顺序
PHASE_ORDER: Final = ("Q01", "Q02", "Q03", "Q04", "Q05", "Q05a", "Q05b", "Q06", "Q07")
