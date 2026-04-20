"""DQG 全局常量集中管理.

所有硬编码的 Phase ID、目录名、文件名映射、路径常量、数字阈值
统一在此定义，其他模块通过 import 引用，禁止就地硬编码。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

# ---------------------------------------------------------------------------
# Phase 元数据
# ---------------------------------------------------------------------------

# Phase ID → 目录后缀（目录名保持不变，只改 key）
PHASE_DIR_MAP: Final = MappingProxyType({
    "Q01": "phaseA",
    "Q02": "phaseA3",
    "Q03": "phaseA6",
    "Q04": "phaseA5",
    "Q05": "phaseB",
    "Q06": "phaseC",
    "Q07": "phaseD",
})

# Phase ID → 结构化 JSON 文件名（文件名保持不变，只改 key）
STRUCTURED_JSON_MAP: Final = MappingProxyType({
    "Q01": "phase_a_structured.json",
    "Q02": "phase_a3_structured.json",
    "Q03": "phase_a6_structured.json",
    "Q04": "phase_a5_structured.json",
    "Q05": "phase_b_structured.json",
    "Q06": "phase_c_structured.json",
    "Q07": "phase_d_structured.json",
})

# Phase ID → 报告文件名
REPORT_MAP: Final = MappingProxyType({
    "Q01": "phase_a_report.md",
    "Q02": "tech_design.md",
    "Q03": "tech_design_quality_review.md",
    "Q04": "tech_design_coverage_review.md",
    "Q05": "eut_matrix.md",
    "Q06": "ut_audit_report.md",
    "Q07": "review_report.md",
})

# Phase ID → Skill 文件路径
SKILL_FILE_MAP: Final = MappingProxyType({
    "Q01": "skills/requirement-structuring/SKILL.md",
    "Q02": "skills/tech-design-generation/SKILL.md",
    "Q04": "skills/tech-coverage-audit/SKILL.md",
    "Q03": "skills/tech-quality-review/SKILL.md",
    "Q06": "skills/unit-test-audit/SKILL.md",
})

# Phase ID → 知识库参考文件路径
KNOWLEDGE_FILE_MAP: Final = MappingProxyType({
    "Q01": "references/risk-catalog-risks.md",
    "Q02": "references/risk-catalog-risks.md",
    "Q04": "profiles/java-ddd-tmf/baseline.md",
    "Q03": "references/risk-catalog-risks.md",
    "Q06": "references/risk-catalog-exceptions.md",
})

# 旧 Phase ID → 新 Phase ID（向后兼容映射）
LEGACY_PHASE_ID_MAP: Final = MappingProxyType({
    "A": "Q01",
    "A.3": "Q02",
    "A.6": "Q03",
    "A.5": "Q04",
    "B": "Q05",
    "C": "Q06",
    "D": "Q07",
})

# ---------------------------------------------------------------------------
# 目录 / 文件路径常量
# ---------------------------------------------------------------------------

DB_FILENAME = ".dqg/store.db"
DASHBOARD_PID_FILE = ".dqg/dashboard.pid"
MEMORY_FILE = ".dqg/MEMORY.md"
WIKI_DIR = ".dqg-wiki"
CASES_DIR = "regression/failure-library/cases"
GOLDEN_DIR = "regression/golden"
PREFERENCE_LOG = "regression/preference_history.jsonl"
MEMORY_INDEX_STATE_FILE = "_memory_index_state.json"

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
DEFAULT_FALLBACK_MODEL = "deepseek-chat"
DEFAULT_JUDGE_MODEL = "deepseek-chat"
DEFAULT_ADAPTIVE_JUDGE_MODELS: tuple[str, ...] = (
    "deepseek-chat",
    "deepseek-chat",
)

# 模型等级映射：Phase 的 recommended_model 字段 → 实际模型名
MODEL_TIER: Final = MappingProxyType({
    "strong": DEFAULT_PRIMARY_MODEL,     # 需要深度理解的 Phase（A/A.3/A.6/D）
    "standard": "claude-sonnet-4-6",     # 模式化执行的 Phase（B/C/A.5）
})
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TIMEOUT = 120

# ---------------------------------------------------------------------------
# LLM 定价（USD per 1M tokens）
# ---------------------------------------------------------------------------

PRICING_INPUT_PER_M = 15.0          # Claude Opus 4 base input
PRICING_OUTPUT_PER_M = 75.0         # Claude Opus 4 base output
PRICING_CACHE_WRITE_PER_M = 18.75   # Cache write (1.25x input)
PRICING_CACHE_READ_PER_M = 1.5      # Cache read (0.1x input)

# ---------------------------------------------------------------------------
# 质量阈值
# ---------------------------------------------------------------------------

JUDGE_PASS_THRESHOLD = 3.5          # adaptive_loop: 通过分数线
JUDGE_PASS_WITH_CONCERNS_DELTA = 0.5  # PASS_WITH_CONCERNS 容差
ADAPTIVE_MAX_ITERATIONS = 3         # adaptive_loop: 最大迭代次数
COMPACT_THRESHOLD = 0.8             # context_loader: 自动压缩触发比例
CASE_MIN_RELEVANCE = 0.05           # skill_tracker: 案例最低相关性
JUDGE_MIN_SCORE_TO_EXTRACT = 4.0    # skill_tracker: judge issue 提取阈值

# ---------------------------------------------------------------------------
# 性能阈值
# ---------------------------------------------------------------------------

PERF_TOKEN_WARNING = 100_000        # perf_tracker: token 用量告警
PERF_DURATION_WARNING = 600         # perf_tracker: 耗时告警（秒）
PERF_OUTPUT_TOKEN_WARNING = 500     # perf_tracker: 输出 token 告警

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
    "req_id", "br_id", "se_id", "gap_id", "open_id",
    "fact_id", "id", "case_id",
)

# ---------------------------------------------------------------------------
# DAG 调度器
# ---------------------------------------------------------------------------

DAG_DEFAULT_MAX_PARALLEL = 3
DAG_DEFAULT_MODE = "adaptive"  # adaptive / agent-run
