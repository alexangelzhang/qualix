"""Qualix 全局常量集中管理.

所有硬编码的 Phase ID、目录名、文件名映射、路径常量、数字阈值
统一在此定义，其他模块通过 import 引用，禁止就地硬编码。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

# ---------------------------------------------------------------------------
# Phase 元数据
# ---------------------------------------------------------------------------

# Phase ID → 目录名（Q 系列统一命名）
PHASE_DIR_MAP: Final = MappingProxyType(
    {
        "Q01": "Q01",
        "Q02": "Q02",
        "Q03": "Q03",
        "Q04": "Q04",
        "Q05a": "Q05a",
        "Q05b": "Q05b",
        "Q06": "Q06",
        "Q07": "Q07",
    }
)

# Phase ID → 结构化 JSON 文件名（文件名保持不变，只改 key）
STRUCTURED_JSON_MAP: Final = MappingProxyType(
    {
        "Q01": "phase_a_structured.json",
        "Q02": "phase_a3_structured.json",
        "Q03": "phase_a6_structured.json",
        "Q04": "phase_a5_structured.json",
        "Q05a": "phase_b_structured.json",  # EUT 矩阵设计产物
        "Q05b": "phase_b_code_status.json",  # @Test 实现进度（Ralph prd.json 等价物）
        "Q06": "phase_c_structured.json",
        "Q07": "phase_d_structured.json",
    }
)

# Phase ID → 报告文件名
REPORT_MAP: Final = MappingProxyType(
    {
        "Q01": "phase_a_report.md",
        "Q02": "tech_design.md",
        "Q03": "tech_design_quality_review.md",
        "Q04": "tech_design_coverage_review.md",
        "Q05a": "eut_matrix.md",
        "Q05b": "codegen_progress.md",
        "Q06": "ut_audit_report.md",
        "Q07": "review_report.md",
    }
)

# Phase ID → Skill 文件路径
SKILL_FILE_MAP: Final = MappingProxyType(
    {
        "Q01": "skills/requirement-structuring/SKILL.md",
        "Q02": "skills/tech-design-generation/SKILL.md",
        "Q03": "skills/tech-quality-review/SKILL.md",
        "Q04": "skills/tech-coverage-audit/SKILL.md",
        "Q05a": "skills/unit-test-design/SKILL.md",
        "Q05b": "skills/unit-test-codegen/SKILL.md",
        "Q06": "skills/unit-test-audit/SKILL.md",
        "Q07": "skills/code-review/SKILL.md",
    }
)

# Phase ID → 知识库参考文件路径
KNOWLEDGE_FILE_MAP: Final = MappingProxyType(
    {
        "Q01": "references/risk-catalog-risks.md",
        "Q02": "references/risk-catalog-risks.md",
        "Q04": "profiles/java-ddd-tmf/baseline.md",
        "Q03": "references/risk-catalog-risks.md",
        "Q06": "references/risk-catalog-exceptions.md",
    }
)

# 旧 Phase ID → 新 Phase ID（向后兼容映射）
LEGACY_PHASE_ID_MAP: Final = MappingProxyType(
    {
        "A": "Q01",
        "A.3": "Q02",
        "A.6": "Q03",
        "A.5": "Q04",
        "C": "Q06",
        "D": "Q07",
    }
)

# ---------------------------------------------------------------------------
# 目录 / 文件路径常量
# ---------------------------------------------------------------------------

DB_FILENAME = ".qualix/store.db"
DASHBOARD_PID_FILE = ".qualix/dashboard.pid"
MEMORY_FILE = ".qualix/MEMORY.md"
MEMORY_SIDECAR_QUEUE = ".qualix/memory_sidecar_queue.jsonl"
MEMORY_GARDEN_REPORT = ".qualix/_memory_garden_report.json"
QUALIX_LARK_AUTH_CONFIG = ".qualix/auth/lark.ini"
QUALIX_LARK_TOKEN_ENV = "QUALIX_LARK_USER_TOKEN"
QUALIX_LARK_EMAIL_ENV = "QUALIX_LARK_USER_EMAIL"
QUALIX_LARK_EXPIRES_ENV = "QUALIX_LARK_TOKEN_EXPIRES_AT"
ENTERPRISE_DOCUMENT_DINGTALK_HOSTS: tuple[str, ...] = ("alidocs.dingtalk.com", "docs.dingtalk.com", "dingtalk.com")
ENTERPRISE_DOCUMENT_LARK_HOSTS: tuple[str, ...] = ("feishu.cn", "larksuite.com")
ENTERPRISE_DOCUMENT_DINGTALK_PROVIDER_ID = "enterprise-url:dingtalk"
ENTERPRISE_DOCUMENT_LARK_PROVIDER_ID = "enterprise-url:lark"
# memory/garden: 同 Phase GAP 两两极性冲突检测的配对上限（O(n²) 保护）。
# 超限后截断并发 log.info 告警，不抽样、不抛异常。GAP 数 >40 的场景目前罕见，
# 真实出现后再考虑抽样策略或按 business_path 分桶。
MEMORY_GAP_CONTRADICTION_MAX_PAIRS = 40
WIKI_DIR = ".qualix-wiki"
CASES_DIR = "regression/failure-library/cases"
GOLDEN_DIR = "regression/golden"
PREFERENCE_LOG = "regression/preference_history.jsonl"
MEMORY_INDEX_STATE_FILE = "_memory_index_state.json"
RULE_HASHES_FILENAME = "_rule_hashes.json"

# Agent 上下文去重：_upstream_context / evidence pack 已内联这些高成本 side files
UPSTREAM_EMBEDDED_CONTEXT_FILES: tuple[str, ...] = (
    "_profile_context.md",
    "_bug_cases.md",
    "_diff_context.md",
)
EVIDENCE_PACK_HEADER = "# Evidence Pack"
EVIDENCE_PACK_EMBEDDED_CONTEXT_FILES: tuple[str, ...] = (
    "image_semantics.md",
    "plain_text_summary.md",
    "plain_text.txt",
)
EVIDENCE_PACK_MAX_QUOTES = 8
EVIDENCE_PACK_QUOTE_CHAR_LIMIT = 600
EVIDENCE_PACK_TOTAL_QUOTE_CHAR_LIMIT = 4_800
EVIDENCE_PACK_SUMMARY_MAX_LINES = 120

# Bug case manifest 相关性匹配输入
BUG_CASE_RELEVANCE_INTERNAL_FILES: tuple[str, ...] = (
    "_upstream_context.md",
    "_diff_context.md",
    "_inputs.json",
)
BUG_CASE_RELEVANCE_EXCERPT_LIMIT = 4_000
BUG_CASE_RELEVANCE_SEED_LIMIT = 12_000
BUG_CASE_RELEVANCE_MAX_CASES = 8

# Agent evidence pack（retrieval-first context bundle）
AGENT_EVIDENCE_EXCERPT_LIMIT = 4_000
AGENT_EVIDENCE_TOTAL_LIMIT = 12_000

# ---------------------------------------------------------------------------
# LLM 配置默认值
# ---------------------------------------------------------------------------

DEFAULT_PRIMARY_MODEL = "claude-opus-4-6"
DEFAULT_FALLBACK_MODEL = None
DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"
DEFAULT_ADAPTIVE_JUDGE_MODELS: tuple[str, ...] = ("claude-sonnet-4-6",)

# 模型等级映射：Phase 的 recommended_model 字段 → 实际模型名
MODEL_TIER: Final = MappingProxyType(
    {
        "strong": DEFAULT_PRIMARY_MODEL,  # 需要深度理解的 Phase（A/A.3/A.6/D）
        "standard": "claude-sonnet-4-6",  # 模式化执行的 Phase（B/C/A.5）
    }
)
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT = 120

# ---------------------------------------------------------------------------
# LLM 定价（USD per 1M tokens）
# ---------------------------------------------------------------------------

PRICING_INPUT_PER_M = 15.0  # Claude Opus 4 base input
PRICING_OUTPUT_PER_M = 75.0  # Claude Opus 4 base output
PRICING_CACHE_WRITE_PER_M = 18.75  # Cache write (1.25x input)
PRICING_CACHE_READ_PER_M = 1.5  # Cache read (0.1x input)

# ---------------------------------------------------------------------------
# 质量阈值
# ---------------------------------------------------------------------------

WEAK_ASSERT_HIGH_RISK_WARN = 3  # 弱断言 gate: high-risk 方法数 ≥ 此值触发 WARNING
WEAK_ASSERT_RATIO_WARN = 0.5  # 弱断言 gate: weak/total 比例 ≥ 此值触发 WARNING（Q06）
WEAK_ASSERT_HIGH_RISK_BLOCK = 1  # Q05b 弱断言 gate: high-risk ≥ 此值触发 BLOCKED
WEAK_ASSERT_RATIO_BLOCK = 0.1  # Q05b 弱断言 gate: weak/total 比例 ≥ 此值触发 BLOCKED（10%）
SKILL_AUTO_MERGE_ENABLED = True  # Skill Evolution: 高置信度规则自动合入 SKILL.md
SKILL_AUTO_MERGE_OVERFITTING_THRESHOLD = 0.5  # holdout coverage_gap 超此值自动 revert

# Skill Evolution absorb 闭环：holdout 分布对比硬门槛（2026-05-10）
SKILL_EVO_HOLDOUT_MIN_CASES = 3  # holdout 至少 N 条 case 才足够做判定（不足则拒绝 auto-merge）
SKILL_EVO_HOLDOUT_MIN_WITH_LESSON = 2  # 带 lesson 的 holdout 至少 N 条才算 holdout_ready
SKILL_EVO_DIST_DIVERGENCE_THRESHOLD = 0.3  # training vs holdout root_cause 分布 L1 差上限
SKILL_EVO_HIT_RATE_MIN = 0.3  # holdout cases 被 suggestion 覆盖命中率下限
MOCK_COINCIDENCE_KEYWORDS: list[str] = [  # Mock 巧合正确检测关键词
    "固定返回",
    "硬编码",
    "写死",
    "return.*new.*\\(\\)",
    "mock.*return.*null",
    "when.*thenReturn.*0",
    "mock.*any",
    "Mockito\\.any",
    "答案固定",
    "不随输入变化",
    "忽略参数",
    "无条件返回",
]
MOCK_REALITY_KEYWORDS: list[str] = [  # Mock 真实性评估关键词
    "Mock 真实",
    "mock.*真实",
    "BigDecimal",
    "email",
    "RpcContext",
    "Mock 数据",
    "贴近业务",
]
AI_ORIGIN_CO_AUTHOR_PATTERNS: list[str] = [  # AI 产出标记：Co-Authored-By 匹配
    r"Co-Authored-By:.*Claude",
    r"Co-Authored-By:.*Copilot",
    r"Co-Authored-By:.*GPT",
    r"Co-Authored-By:.*Cursor",
    r"Co-Authored-By:.*Devin",
    r"Co-Authored-By:.*noreply@anthropic\.com",
    r"Co-Authored-By:.*noreply@github\.com",
]

JUDGE_PASS_THRESHOLD = 3.5  # adaptive_loop: 通过分数线
JUDGE_PASS_WITH_CONCERNS_DELTA = 0.5  # PASS_WITH_CONCERNS 容差
ADAPTIVE_MAX_ITERATIONS = 3  # adaptive_loop: 最大迭代次数

# ---------------------------------------------------------------------------
# P1: ACT Review Depth — risk_tier → adaptive loop depth config
# ---------------------------------------------------------------------------

REVIEW_DEPTH_CONFIG: Final = MappingProxyType(
    {
        "LOW": MappingProxyType({"max_iterations": 1, "force_secondary": False, "skip_critique": True}),
        "MEDIUM": MappingProxyType({"max_iterations": 2, "force_secondary": False, "skip_critique": False}),
        "HIGH": MappingProxyType({"max_iterations": 3, "force_secondary": True, "skip_critique": False}),
        "CRITICAL": MappingProxyType({"max_iterations": 3, "force_secondary": True, "skip_critique": False}),
    }
)
REVIEW_DEPTH_DEFAULT = "MEDIUM"

# ---------------------------------------------------------------------------
# P3: Shared Rubric — universal quality dimensions (40% base weight)
# ---------------------------------------------------------------------------

SHARED_RUBRIC_DIMENSIONS: Final = (
    {
        "id": "source_citation",
        "name": "来源标注完整性",
        "description": "每条结论是否标注了来源（[来源: 文件名:行号]）",
        "weight": 0.10,
        "rubric": {
            5: "所有结论都有精确的来源标注（文件名:行号）",
            4: "90%+ 结论有来源标注，个别缺失",
            3: "70-90% 有来源标注",
            2: "来源标注不足 70%",
            1: "几乎无来源标注",
        },
    },
    {
        "id": "confidence_tagging",
        "name": "置信度标注",
        "description": "每条结论是否标注了置信度（High/Medium/Low）",
        "weight": 0.10,
        "rubric": {
            5: "所有结论都有置信度标注，且标注合理",
            4: "90%+ 有置信度标注",
            3: "70-90% 有标注，部分标注不合理",
            2: "标注不足 70%",
            1: "几乎无置信度标注",
        },
    },
    {
        "id": "structural_completeness",
        "name": "结构完整性",
        "description": "报告是否包含所有必要章节，格式是否规范",
        "weight": 0.10,
        "rubric": {
            5: "所有必要章节齐全，格式规范，无截断",
            4: "主要章节齐全，个别格式瑕疵",
            3: "缺少 1-2 个非核心章节",
            2: "缺少核心章节或格式混乱",
            1: "结构严重不完整",
        },
    },
    {
        "id": "reasoning_quality",
        "name": "推理日志质量",
        "description": "推理日志是否记录了关键决策过程，可追溯",
        "weight": 0.10,
        "rubric": {
            5: "每个关键决策都有推理过程记录，可完整追溯",
            4: "主要决策有记录，个别步骤缺失",
            3: "部分决策有记录，但关键判断缺少推理过程",
            2: "推理日志流于形式，缺少实质内容",
            1: "几乎无推理记录",
        },
    },
)

COMPACT_THRESHOLD = 0.8  # context_loader: 自动压缩触发比例
CASE_MIN_RELEVANCE = 0.05  # skill_tracker: 案例最低相关性
JUDGE_MIN_SCORE_TO_EXTRACT = 4.0  # skill_tracker: judge issue 提取阈值

# ---------------------------------------------------------------------------
# 性能阈值
# ---------------------------------------------------------------------------

PERF_TOKEN_WARNING = 100_000  # perf_tracker: token 用量告警
PERF_DURATION_WARNING = 600  # perf_tracker: 耗时告警（秒）
PERF_OUTPUT_TOKEN_WARNING = 500  # perf_tracker: 输出 token 告警

# ---------------------------------------------------------------------------
# Anti-Rationalization Runtime Enforcement
# ---------------------------------------------------------------------------

RATIONALIZATION_PATTERNS: list[str] = [
    r"虽然.{0,20}但.{0,20}(可以接受|尚可|足够)",
    r"(基本|整体|总体).{0,10}(清晰|达标|合格|可接受)",
    r"考虑到.{0,15}(时间|复杂度|限制)",
    r"影响不大",
    r"已经(有了?|存在).{0,10}(改进|提升)",
    r"覆盖率.{0,5}达标",
    r"(不需要|没必要).{0,10}(边界|并发|异常)",
    r"上一轮已经",
]

DEFAULT_RATIONALIZATION_CONFIRM_MODEL = "claude-haiku-4-5-20251001"
RATIONALIZATION_MAX_REJUDGE = 1

# Guard telemetry（结构化事件 + before/after pair 存档，供 guard_precision_report 聚合）
GUARD_EVENT_FILENAME = "_rationalization_guard.jsonl"
GUARD_PAIR_DIRNAME = "_rationalization_pairs"

# Overcorrection patterns: Judge 过严误报信号（与 RATIONALIZATION_PATTERNS 方向相反）
OVERCORRECTION_PATTERNS: list[str] = [
    r"虽然.{0,20}(逻辑正确|实现正确|功能正常).{0,20}但.{0,20}(不符合|未遵循|建议)",
    r"(代码能工作|功能正常).{0,10}但.{0,10}(最佳实践|规范|标准)",
    r"(严格来说|从标准角度).{0,10}(不合规|不达标|不满足)",
    r"(缺少|没有).{0,10}(注释|文档|日志).{0,10}(FAIL|不通过|不合格)",
    r"(风格|命名|格式).{0,10}(不一致|不规范).{0,10}(FAIL|BLOCKER|MAJOR)",
    r"(理论上|原则上).{0,10}(应该|需要|必须).{0,10}(但|不过)",
    r"(潜在|可能|理论上).{0,10}(风险|问题).{0,10}(FAIL|BLOCKER)",
]

# Holdout replay
HOLDOUT_DIR = "regression/holdout"
HOLDOUT_SUITE_BASELINE_FILE = "suite_baseline.json"
HOLDOUT_SUITE_REGRESSION_THRESHOLD = 0.95
HOLDOUT_CASE_REGRESSION_THRESHOLD = 0.90

# ---------------------------------------------------------------------------
# Wiki
# ---------------------------------------------------------------------------

WIKI_COMPILE_CONTEXT_LIMIT = 12_000
WIKI_RAW_TEXT_FALLBACK_LIMIT = 10_000
WIKI_LINT_TOTAL_EXCERPT_LIMIT = 20_000
WIKI_LINT_FILE_EXCERPT_LIMIT = 4_000

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_PORT = 8501

# ---------------------------------------------------------------------------
# 结构化 ID 模式
# ---------------------------------------------------------------------------

# 完整 ID 前缀集合（behavioral_fingerprint / chunk_summarizer / evidence_renderer / rsm_mutations 共用）
RSM_ID_PREFIXES: tuple[str, ...] = ("REQ-", "BR-", "SE-", "GAP-", "OPEN-")

# 基础 ID 正则（chunk_summarizer 等用于从文本提取 ID）
ID_PATTERN_BASE = r"(REQ|BR|SE|GAP|OPEN|EUT|CASE)-\d+"

# 扩展 ID 正则（behavioral_fingerprint 用于行为指纹，含架构/API/数据等维度）
ID_PATTERN_EXTENDED = r"(REQ|BR|SE|GAP|OPEN|EUT|CASE|ARCH|API|DATA|EXC|PERF)-\d+"

# evidence_renderer / chunk_summarizer 共用的 ID 字段名
ID_FIELD_KEYS: tuple[str, ...] = (
    "req_id",
    "br_id",
    "se_id",
    "gap_id",
    "open_id",
    "fact_id",
    "id",
    "case_id",
)

# ---------------------------------------------------------------------------
# DAG 调度器
# ---------------------------------------------------------------------------

DAG_DEFAULT_MAX_PARALLEL = 3
DAG_DEFAULT_MODE = "adaptive"  # adaptive / agent-run

# ---------------------------------------------------------------------------
# 图片 Token 优化
# ---------------------------------------------------------------------------

# 小于此字节数的图片直接跳过 VLM 解析（图标/分隔线/装饰图）
IMAGE_SIZE_SKIP_THRESHOLD = 10_000  # 10KB
# 小于此字节数的图片用轻量描述，不做精读
IMAGE_SIZE_LIGHT_THRESHOLD = 50_000  # 50KB
# 需要精读的图片类型关键词（流程图/状态机/架构图）
IMAGE_DEEP_READ_KEYWORDS = ("流程", "状态", "架构", "时序", "ER", "拓扑", "flowchart", "state", "sequence")

# ---------------------------------------------------------------------------
# data_patterns sidecar
# ---------------------------------------------------------------------------

# 每个 pattern 保留的 lesson 原文数量及最大字符数
DATA_PATTERN_TOP_LESSONS: int = 3
DATA_PATTERN_LESSON_MAX_CHARS: int = 200

# 枚举单一真源（T7）: `EnumSource` / `render_enum_contract_prefix` → `qualix.context.enum_contract`
