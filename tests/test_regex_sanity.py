"""正则表达式 sanity 测试.

策略：对每个业务正则常量提供：
  - ≥1 条 should_match（有代表性的合法输入）
  - ≥1 条 should_not_match（边界/历史误报/修复点）

覆盖模块：
  - quality/rules/source_spec.py      (R-SOURCE 来源标注)
  - quality/rules/rule_definitions.py (各 Phase 规则辅助正则)
  - quality/checks/report_quality_checks.py (finalize 检测正则)

新增正则常量时在对应 class 里追加用例。
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# source_spec.py
# ---------------------------------------------------------------------------


class TestRESourceBase:
    """RE_SOURCE_BASE — 通用 [来源: xxx] / [Source: xxx] 格式."""

    from qualix.quality.rules.source_spec import RE_SOURCE_BASE as PAT

    @pytest.mark.parametrize(
        "text",
        [
            "该接口缺失幂等校验 [来源: OrderService.java:42]",
            "存在风险 [来源：plain_text.txt:10]",  # 全角冒号
            "COVERED [Source: tech_design.md:L5]",
            "[来源: SE-003]",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import RE_SOURCE_BASE

        assert RE_SOURCE_BASE.search(text), f"应匹配但未匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "该接口缺失幂等校验",           # 无来源标注
            "来源不对的写法: tech_design",  # 裸"来源"不在括号内
            "参考 source code 里的注释",    # source 非来源标注格式
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import RE_SOURCE_BASE

        assert not RE_SOURCE_BASE.search(text), f"不应匹配但匹配了: {text!r}"


class TestPhaseSourceExtraQ01:
    """PHASE_SOURCE_EXTRA['Q01'] — PRD 原文裸引用."""

    @pytest.mark.parametrize(
        "text",
        [
            "plain_text.txt:42 中描述了此场景",
            "blocks.raw.json:10",
            "comments.md:5",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert PHASE_SOURCE_EXTRA["Q01"].search(text), f"Q01 应匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "REQ-001 缺失幂等校验",      # REQ ID 不是 Q01 的合法来源
            "plain_text.txt 未标行号",   # 无行号
            "tech_design.md:L10",        # Q02 来源，Q01 不接受
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert not PHASE_SOURCE_EXTRA["Q01"].search(text), f"Q01 不应匹配: {text!r}"


class TestPhaseSourceExtraQ04:
    """PHASE_SOURCE_EXTRA['Q04'] — 覆盖审计来源（证据类，不含主语 ID）."""

    @pytest.mark.parametrize(
        "text",
        [
            "tech_design.md 第 3 节已描述此场景",
            "HLD 接口定义已涵盖",
            "OrderService.java:42 有完整实现",
            "OrderService.java 整体覆盖",
            "ARCH-001 架构决策",
            "API-003 接口定义",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert PHASE_SOURCE_EXTRA["Q04"].search(text), f"Q04 应匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "REQ-001 COVERED",       # REQ 是主语，不是来源 — 修复点
            "BR-002 已覆盖",          # BR 是主语
            "SE-003 对应测试已写",    # SE 是主语
            "GAP-001 已闭环",         # GAP 是主语
            "整体已覆盖，无具体来源", # 无任何来源标注
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert not PHASE_SOURCE_EXTRA["Q04"].search(text), f"Q04 不应匹配: {text!r}"


class TestPhaseSourceExtraQ05:
    """PHASE_SOURCE_EXTRA['Q05'] — 单测设计来源（SE/EUT）."""

    @pytest.mark.parametrize(
        "text",
        [
            "SE-003 对应的异常路径",
            "EUT-007 已覆盖边界",
            "target_class 已包含",
            "target_method 方法签名",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert PHASE_SOURCE_EXTRA["Q05"].search(text), f"Q05 应匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "REQ-001 缺少测试",     # REQ 不是 Q05 来源
            "无任何 ID 引用",
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import PHASE_SOURCE_EXTRA

        assert not PHASE_SOURCE_EXTRA["Q05"].search(text), f"Q05 不应匹配: {text!r}"


class TestConclusionPattern:
    """_CONCLUSION_PATTERN — 判定性结论行识别（修复后精确化'建议'）."""

    @pytest.mark.parametrize(
        "text",
        [
            "该字段缺失，需要补充",
            "REQ-001 NOT_COVERED",
            "存在风险，需评估",
            "高风险接口未鉴权",
            "BLOCKER: 空指针异常",
            "COVERED",
            "PARTIAL 覆盖",
            "建议补充边界测试",    # 精确复合词应匹配
            "建议修复此问题",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import _CONCLUSION_PATTERN

        assert _CONCLUSION_PATTERN.search(text), f"应匹配但未匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "建议使用 UUID 而非自增 ID",       # 裸"建议"叙述性句子 — 修复点
            "建议读者参考技术文档",             # 同上
            "这是一个很好的建议",               # 同上
            "系统整体运行正常",
            "接口设计如下",
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import _CONCLUSION_PATTERN

        assert not _CONCLUSION_PATTERN.search(text), f"不应匹配但匹配了: {text!r}"


class TestValidIdPattern:
    """_VALID_ID_PATTERN — 表格行实质内容判断（扩展后含 EUT/ARCH/D 等）."""

    @pytest.mark.parametrize(
        "text",
        [
            "| REQ-001 | COVERED |",
            "| SE-003 | PARTIAL |",
            "| EUT-007 | 已实现 |",       # Q05 特有 — 修复点
            "| D-001 | BLOCKER |",         # Q07 特有 — 修复点
            "| ARCH-002 | 架构决策 |",    # Q02/Q03 特有 — 修复点
            "| API-003 | 接口定义 |",
            "| GAP-001 | P1 |",
            "| OPEN-002 | 待确认 |",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.source_spec import _VALID_ID_PATTERN

        assert _VALID_ID_PATTERN.search(text), f"应匹配但未匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "| 总计 | 10 |",           # 统计行，无具体 ID
            "| 覆盖率 | 80% |",
            "| 已覆盖 | 未覆盖 |",
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.source_spec import _VALID_ID_PATTERN

        assert not _VALID_ID_PATTERN.search(text), f"不应匹配但匹配了: {text!r}"


class TestIsSourceAnnotated:
    """is_source_annotated — 集成测试，验证各 Phase 合法来源被识别."""

    @pytest.mark.parametrize(
        "line, phase, should_pass",
        [
            # 通用基线
            ("缺失校验 [来源: OrderService.java:42]", "Q01", True),
            # Q01 PRD 裸引用
            ("plain_text.txt:10 中提及此场景", "Q01", True),
            # Q01 不接受 REQ ID 作为来源
            ("REQ-001 缺失幂等校验", "Q01", False),
            # Q04 接受技术方案证据
            ("tech_design.md 已覆盖此场景", "Q04", True),
            ("OrderService.java:42 完整实现", "Q04", True),
            # Q04 不接受主语 ID（修复点）
            ("REQ-001 COVERED", "Q04", False),
            ("SE-003 已覆盖", "Q04", False),
            # Q05 接受 SE/EUT
            ("SE-003 对应的边界测试", "Q05", True),
            ("EUT-007 已覆盖", "Q05", True),
            # Q07 接受文件行号
            ("OrderService.java:42 存在空指针风险", "Q07", True),
            ("D-001 缺陷已确认", "Q07", True),
            # 无任何来源标注
            ("整体已覆盖", "Q04", False),
        ],
    )
    def test_annotation(self, line, phase, should_pass):
        from qualix.quality.rules.source_spec import is_source_annotated

        result = is_source_annotated(line, phase)
        if should_pass:
            assert result, f"Phase={phase} 应通过但未通过: {line!r}"
        else:
            assert not result, f"Phase={phase} 不应通过但通过了: {line!r}"


# ---------------------------------------------------------------------------
# rule_definitions.py
# ---------------------------------------------------------------------------


class TestREConfidence:
    """RE_CONFIDENCE — 置信度标注识别."""

    @pytest.mark.parametrize(
        "text",
        [
            "[置信度: High]",
            "[置信度：Medium]",
            "`Low`",
            "| High |",
            "| 高 |（中文）",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.rules.rule_definitions import RE_CONFIDENCE

        assert RE_CONFIDENCE.search(text), f"应匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "高质量代码",        # "高"不在 | 上下文里
            "Medium 风险描述",  # 无括号/表格上下文（不在 |..| 或 [...]）
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.rule_definitions import RE_CONFIDENCE

        assert not RE_CONFIDENCE.search(text), f"不应匹配: {text!r}"


class TestRECoverageStatus:
    """RE_COVERAGE_STATUS — 覆盖状态关键字."""

    @pytest.mark.parametrize("text", ["COVERED", "NOT_COVERED", "PARTIAL", "MISSING", "IMPLICIT"])
    def test_should_match(self, text):
        from qualix.quality.rules.rule_definitions import RE_COVERAGE_STATUS

        assert RE_COVERAGE_STATUS.search(text)

    def test_should_not_match(self):
        from qualix.quality.rules.rule_definitions import RE_COVERAGE_STATUS

        assert not RE_COVERAGE_STATUS.search("覆盖已完成")


class TestREGapLevel:
    """RE_GAP_LEVEL — GAP 风险等级标注."""

    @pytest.mark.parametrize("text", ["P0", "P1", "P2", "| 高 |", "| 中 |", "| 低 |", "风险等级"])
    def test_should_match(self, text):
        from qualix.quality.rules.rule_definitions import RE_GAP_LEVEL

        assert RE_GAP_LEVEL.search(text), f"应匹配: {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "P3 不存在",          # P3 不合法
            "高风险描述",         # "高"不在 | 上下文里
        ],
    )
    def test_should_not_match(self, text):
        from qualix.quality.rules.rule_definitions import RE_GAP_LEVEL

        assert not RE_GAP_LEVEL.search(text), f"不应匹配: {text!r}"


# ---------------------------------------------------------------------------
# report_quality_checks.py
# ---------------------------------------------------------------------------


class TestValidIdPatternInReportChecks:
    """report_quality_checks._VALID_ID_PATTERN — ID 格式合法性."""

    @pytest.mark.parametrize(
        "text", ["REQ-001", "BR-002", "SE-003", "GAP-004", "OPEN-005"]
    )
    def test_valid_ids(self, text):
        from qualix.quality.checks.report_quality_checks import _VALID_ID_PATTERN

        assert _VALID_ID_PATTERN.search(text)

    @pytest.mark.parametrize("text", ["req-001", "REQ_001", "REQ 001"])
    def test_invalid_ids(self, text):
        from qualix.quality.checks.report_quality_checks import _VALID_ID_PATTERN

        assert not _VALID_ID_PATTERN.search(text)


class TestInvalidIdPattern:
    """report_quality_checks._INVALID_ID_PATTERN — 非法 ID 格式检测."""

    @pytest.mark.parametrize("text", ["REQ_001", "req-001", "BR 002"])
    def test_detects_invalid(self, text):
        from qualix.quality.checks.report_quality_checks import _INVALID_ID_PATTERN

        assert _INVALID_ID_PATTERN.search(text), f"应检测为非法: {text!r}"

    @pytest.mark.parametrize("text", ["REQ-001", "BR-002", "SE-003"])
    def test_valid_not_flagged(self, text):
        from qualix.quality.checks.report_quality_checks import _INVALID_ID_PATTERN

        assert not _INVALID_ID_PATTERN.search(text), f"合法 ID 被误报: {text!r}"


class TestStepPattern:
    """report_quality_checks._STEP_PATTERN — 推理日志步骤标记."""

    @pytest.mark.parametrize(
        "text",
        [
            "## Step 1 分析需求",
            "### Step 2",
            "\n## Step 0\n",
        ],
    )
    def test_should_match(self, text):
        from qualix.quality.checks.report_quality_checks import _STEP_PATTERN

        assert _STEP_PATTERN.search(text), f"应匹配: {text!r}"

    def test_should_not_match(self):
        from qualix.quality.checks.report_quality_checks import _STEP_PATTERN

        assert not _STEP_PATTERN.search("Step without heading marker")


# ---------------------------------------------------------------------------
# check_regex.py 脚本自身逻辑
# ---------------------------------------------------------------------------


class TestCheckRegexScript:
    """check_regex.py 核心检测逻辑单元测试."""

    def test_detects_pipe_in_charclass_chinese(self):
        from scripts.check_regex import check_pipe_in_charclass

        # 本次修复前的原始 bug 模式
        findings = check_pipe_in_charclass(r"[来源:|source:|文件名:\d+]")
        assert len(findings) >= 1

    def test_detects_pipe_in_charclass_ascii(self):
        from scripts.check_regex import check_pipe_in_charclass

        findings = check_pipe_in_charclass(r"[foo|bar]")
        assert len(findings) >= 1

    def test_no_false_positive_single_char_in_class(self):
        from scripts.check_regex import check_pipe_in_charclass

        # [\s\-:|] — | 是字面量，两侧无连续 word char，不应报警（历史 false positive 修复点）
        assert check_pipe_in_charclass(r"[\s\-:|]") == []
        # 无 | 的字符类
        assert check_pipe_in_charclass(r"[一-鿿]+") == []
        assert check_pipe_in_charclass(r"[A-Za-z0-9]") == []

    def test_no_false_positive_alternation_outside_charclass(self):
        from scripts.check_regex import check_pipe_in_charclass

        # 正确的交替式，不在字符类里
        assert check_pipe_in_charclass(r"来源[:：]|source:|文件名:\d+") == []
        assert check_pipe_in_charclass(r"REQ-\d+|BR-\d+") == []

    def test_check_file_catches_bug(self, tmp_path):
        from scripts.check_regex import check_file

        bad = tmp_path / "bad.py"
        bad.write_text('import re\nre.search(r"[来源:|source:]", text)\n')
        issues = check_file(bad)
        assert any(i.rule == "R1" for i in issues)

    def test_check_file_no_issue_on_correct_pattern(self, tmp_path):
        from scripts.check_regex import check_file

        good = tmp_path / "good.py"
        good.write_text('import re\nre.search(r"来源[:：]|source:", text)\n')
        issues = check_file(good)
        assert not any(i.rule == "R1" for i in issues)


# ---------------------------------------------------------------------------
# 全量 CI 扫描（通过调用脚本）
# ---------------------------------------------------------------------------


class TestCheckRegexCI:
    """通过脚本入口扫描 src/qualix/，确认现存代码无 R1/R3 问题."""

    def test_no_regex_bugs_in_src(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "scripts/check_regex.py"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"check_regex 发现问题:\n{result.stdout}\n{result.stderr}"
        )
