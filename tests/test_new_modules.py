"""新增模块测试：compile_check, blast_radius, coverage_matrix, dynamic_rubric, coverage_gate."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# coverage_matrix 测试
# ---------------------------------------------------------------------------


class TestCoverageMatrix:
    def test_extract_requirement_ids(self):
        from dqg.quality.coverage_matrix import extract_requirement_ids

        data = {
            "requirements": [
                {"req_id": "REQ-001", "description": "用户登录"},
                {"req_id": "BR-001", "description": "密码长度>=8"},
            ],
            "semantic_expectations": [
                {"se_id": "SE-001", "description": "登录失败锁定"},
            ],
            "gaps": [
                {"gap_id": "GAP-001", "description": "并发登录未定义"},
            ],
            "open_items": [
                {"open_id": "OPEN-001", "description": "第三方登录待确认"},
            ],
        }
        result = extract_requirement_ids(data)
        assert len(result["requirements"]) == 1
        assert len(result["business_rules"]) == 1
        assert len(result["semantic_expectations"]) == 1
        assert len(result["gaps"]) == 1
        assert len(result["open_items"]) == 1

    def test_extract_tech_design_sections(self, tmp_path):
        from dqg.quality.coverage_matrix import extract_tech_design_sections

        md = tmp_path / "tech_design.md"
        md.write_text("## 3.1 退款接口\nRefundService.refund(RefundRequest req)\n## 3.2 查询\n")
        sections = extract_tech_design_sections(md)
        assert any(s["type"] == "heading" for s in sections)

    def test_generate_coverage_matrix_no_phase_a(self, tmp_path):
        from dqg.quality.coverage_matrix import generate_coverage_matrix

        result = generate_coverage_matrix(tmp_path, "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# dynamic_rubric 测试
# ---------------------------------------------------------------------------


class TestDynamicRubric:
    def test_classify_se_domains(self):
        from dqg.quality.dynamic_rubric import classify_se_domains

        se_list = [
            {"description": "金额计算精度必须到分"},
            {"description": "金额BigDecimal不能用double"},
            {"description": "并发提交幂等校验"},
            {"description": "用户登录功能"},
        ]
        domains = classify_se_domains(se_list)
        assert domains.get("金额精度", 0) == 2
        assert domains.get("并发安全", 0) == 1

    def test_generate_dynamic_dimensions_empty(self, tmp_path):
        from dqg.quality.dynamic_rubric import generate_dynamic_dimensions

        dims = generate_dynamic_dimensions(tmp_path, "nonexistent", "Q01")
        assert dims == []

    def test_enrich_rubric_normalizes_weights(self):
        from dqg.quality.dynamic_rubric import enrich_rubric_with_dynamic_dimensions

        rubric = {
            "name": "test",
            "dimensions": [
                {"id": "d1", "weight": 0.5, "name": "dim1", "description": ""},
                {"id": "d2", "weight": 0.5, "name": "dim2", "description": ""},
            ],
        }
        dynamic = [
            {"id": "dyn1", "weight": 0.15, "name": "dyn", "description": "", "rubric": {}},
        ]
        enriched = enrich_rubric_with_dynamic_dimensions(rubric, dynamic)
        total = sum(d["weight"] for d in enriched["dimensions"])
        assert abs(total - 1.0) < 0.01
        assert len(enriched["dimensions"]) == 3

    def test_enrich_rubric_no_duplicates(self):
        from dqg.quality.dynamic_rubric import enrich_rubric_with_dynamic_dimensions

        rubric = {
            "name": "test",
            "dimensions": [{"id": "dyn1", "weight": 1.0, "name": "x", "description": ""}],
        }
        dynamic = [{"id": "dyn1", "weight": 0.15, "name": "y", "description": "", "rubric": {}}]
        enriched = enrich_rubric_with_dynamic_dimensions(rubric, dynamic)
        assert len(enriched["dimensions"]) == 1  # no duplicate


# ---------------------------------------------------------------------------
# compile_check 测试
# ---------------------------------------------------------------------------


class TestCompileCheck:
    def test_detect_build_tool_maven(self, tmp_path):
        from dqg.quality.compile_check import detect_build_tool

        (tmp_path / "pom.xml").write_text("<project/>")
        assert detect_build_tool(tmp_path) == "maven"

    def test_detect_build_tool_gradle(self, tmp_path):
        from dqg.quality.compile_check import detect_build_tool

        (tmp_path / "build.gradle").write_text("apply plugin: 'java'")
        assert detect_build_tool(tmp_path) == "gradle"

    def test_detect_build_tool_go(self, tmp_path):
        from dqg.quality.compile_check import detect_build_tool

        (tmp_path / "go.mod").write_text("module example.com/foo")
        assert detect_build_tool(tmp_path) == "go"

    def test_detect_build_tool_none(self, tmp_path):
        from dqg.quality.compile_check import detect_build_tool

        assert detect_build_tool(tmp_path) is None

    def test_check_phase_b_no_repo(self):
        from dqg.quality.compile_check import check_phase_b_compilation

        errors = check_phase_b_compilation(Path("/tmp"), "test", code_repo=None)
        assert errors == []

    def test_check_phase_b_missing_repo(self):
        from dqg.quality.compile_check import check_phase_b_compilation

        errors = check_phase_b_compilation(Path("/tmp"), "test", code_repo="/nonexistent/path")
        assert any("BLOCKED" in e for e in errors)


# ---------------------------------------------------------------------------
# blast_radius 测试
# ---------------------------------------------------------------------------


class TestBlastRadius:
    def test_build_call_graph_regex(self, tmp_path):
        from dqg.quality.blast_radius import build_call_graph_regex

        java_file = tmp_path / "OrderService.java"
        java_file.write_text(
            textwrap.dedent("""\
            public class OrderService {
                public void createOrder(OrderRequest req) {
                    paymentService.charge(req.getAmount());
                    notifyService.send(req.getUserId());
                }
                public void cancelOrder(String orderId) {
                    paymentService.refund(orderId);
                }
            }
        """)
        )
        graph = build_call_graph_regex(tmp_path, ["OrderService.java"])
        assert "OrderService.createOrder" in graph
        assert "OrderService.cancelOrder" in graph
        calls = graph["OrderService.createOrder"]["calls"]
        assert any("charge" in c for c in calls)

    def test_build_call_graph_empty(self, tmp_path):
        from dqg.quality.blast_radius import build_call_graph_regex

        graph = build_call_graph_regex(tmp_path, [])
        assert graph == {}


# ---------------------------------------------------------------------------
# coverage_gate 测试
# ---------------------------------------------------------------------------


class TestCoverageGate:
    def test_parse_jacoco_xml(self, tmp_path):
        from dqg.quality.coverage_gate import parse_jacoco_xml

        xml_content = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <counter type="LINE" covered="800" missed="200"/>
                <counter type="BRANCH" covered="600" missed="400"/>
                <counter type="METHOD" covered="50" missed="10"/>
            </report>
        """)
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(xml_content)

        result = parse_jacoco_xml(xml_path)
        assert result is not None
        assert result["line"]["rate"] == 0.8
        assert result["branch"]["rate"] == 0.6

    def test_check_coverage_gate_pass(self):
        from dqg.quality.coverage_gate import check_coverage_gate

        coverage = {
            "line": {"covered": 850, "missed": 150, "rate": 0.85},
            "branch": {"covered": 820, "missed": 180, "rate": 0.82},
        }
        errors = check_coverage_gate(coverage)
        assert errors == []

    def test_check_coverage_gate_fail(self):
        from dqg.quality.coverage_gate import check_coverage_gate

        coverage = {
            "line": {"covered": 700, "missed": 300, "rate": 0.70},
            "branch": {"covered": 500, "missed": 500, "rate": 0.50},
        }
        errors = check_coverage_gate(coverage)
        assert len(errors) == 2
        assert all("BLOCKED" in e for e in errors)

    def test_parse_jacoco_xml_missing(self, tmp_path):
        from dqg.quality.coverage_gate import parse_jacoco_xml

        result = parse_jacoco_xml(tmp_path / "nonexistent.xml")
        assert result is None

    def test_find_jacoco_report_maven(self, tmp_path):
        from dqg.quality.coverage_gate import find_jacoco_report

        jacoco_dir = tmp_path / "target" / "site" / "jacoco"
        jacoco_dir.mkdir(parents=True)
        (jacoco_dir / "jacoco.xml").write_text("<report/>")
        found = find_jacoco_report(tmp_path)
        assert found is not None
        assert "jacoco.xml" in str(found)

    def test_find_jacoco_report_none(self, tmp_path):
        from dqg.quality.coverage_gate import find_jacoco_report

        assert find_jacoco_report(tmp_path) is None

    def test_parse_jacoco_per_file(self, tmp_path):
        from dqg.quality.coverage_gate import parse_jacoco_per_file

        xml_content = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <report name="test">
                <package name="com/example">
                    <sourcefile name="Foo.java">
                        <counter type="LINE" covered="80" missed="20"/>
                        <counter type="BRANCH" covered="30" missed="10"/>
                    </sourcefile>
                    <sourcefile name="Bar.java">
                        <counter type="LINE" covered="50" missed="50"/>
                        <counter type="BRANCH" covered="20" missed="30"/>
                    </sourcefile>
                </package>
            </report>
        """)
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(xml_content)

        result = parse_jacoco_per_file(xml_path)
        assert result is not None
        assert "com/example/Foo.java" in result
        assert result["com/example/Foo.java"]["line"]["rate"] == 0.8
        assert "com/example/Bar.java" in result
        assert result["com/example/Bar.java"]["line"]["rate"] == 0.5

    def test_parse_jacoco_per_file_missing(self, tmp_path):
        from dqg.quality.coverage_gate import parse_jacoco_per_file

        assert parse_jacoco_per_file(tmp_path / "nope.xml") is None

    def test_compute_incremental_coverage_basic(self):
        from dqg.quality.coverage_gate import compute_incremental_coverage

        per_file = {
            "com/example/Foo.java": {
                "line": {"covered": 80, "missed": 20, "total": 100, "rate": 0.8},
                "branch": {"covered": 30, "missed": 10, "total": 40, "rate": 0.75},
            },
            "com/example/Bar.java": {
                "line": {"covered": 50, "missed": 50, "total": 100, "rate": 0.5},
                "branch": {"covered": 20, "missed": 30, "total": 50, "rate": 0.4},
            },
            "com/example/Unrelated.java": {
                "line": {"covered": 10, "missed": 90, "total": 100, "rate": 0.1},
                "branch": {"covered": 5, "missed": 45, "total": 50, "rate": 0.1},
            },
        }
        blast_radius = {
            "changed_files": ["src/main/java/com/example/Foo.java"],
            "changed_methods": ["Foo.doSomething"],
            "affected_callers": ["Bar.callFoo"],
            "affected_tests": [],
        }

        result = compute_incremental_coverage(per_file, blast_radius)
        assert len(result["matched_files"]) == 2  # Foo + Bar
        assert result["unmatched_files_count"] == 1  # Unrelated
        # Foo(80/20) + Bar(50/50) = 130/70 → 0.65
        assert result["incremental"]["line"]["rate"] == 0.65
        # Foo(30/10) + Bar(20/30) = 50/40 → ~0.5556
        assert abs(result["incremental"]["branch"]["rate"] - 0.5556) < 0.001

    def test_compute_incremental_coverage_no_match(self):
        from dqg.quality.coverage_gate import compute_incremental_coverage

        per_file = {
            "com/example/Unrelated.java": {
                "line": {"covered": 10, "missed": 90, "total": 100, "rate": 0.1},
            },
        }
        blast_radius = {
            "changed_files": ["src/main/java/com/other/Missing.java"],
            "changed_methods": [],
            "affected_callers": [],
            "affected_tests": [],
        }

        result = compute_incremental_coverage(per_file, blast_radius)
        assert result["matched_files"] == []
        assert result["incremental"] == {}

    def test_compute_incremental_coverage_filename_fallback(self):
        """changed_files 路径不含 java/ 目录时 fallback 到文件名匹配."""
        from dqg.quality.coverage_gate import compute_incremental_coverage

        per_file = {
            "com/example/Service.java": {
                "line": {"covered": 90, "missed": 10, "total": 100, "rate": 0.9},
            },
        }
        blast_radius = {
            "changed_files": ["some/odd/path/Service.java"],
            "changed_methods": [],
            "affected_callers": [],
            "affected_tests": [],
        }

        result = compute_incremental_coverage(per_file, blast_radius)
        assert len(result["matched_files"]) == 1


# ---------------------------------------------------------------------------
# overcorrection_guard 测试
# ---------------------------------------------------------------------------


class TestOvercorrectionGuard:
    def test_no_overcorrection(self):
        from dqg.quality.rationalization_guard import OvercorrectionGuard

        guard = OvercorrectionGuard()
        output = (
            "FAIL: 接口缺少幂等校验，并发场景下会重复扣款。\n"
            "证据: PaymentService.java:142 — deduct() 没有检查 requestId 唯一性。"
        )
        result = guard.check(output)
        assert not result.has_overcorrection
        assert result.confirmed_overcorrections == []
        assert result.fail_without_evidence == []

    def test_detect_style_overcorrection(self):
        from dqg.quality.rationalization_guard import OvercorrectionGuard

        guard = OvercorrectionGuard()
        output = "虽然代码逻辑正确，但不符合最佳实践，判定 FAIL。"
        result = guard.check(output)
        assert result.has_overcorrection
        assert len(result.confirmed_overcorrections) >= 1

    def test_detect_fail_without_evidence(self):
        from dqg.quality.rationalization_guard import OvercorrectionGuard

        guard = OvercorrectionGuard()
        output = "该模块整体质量一般。\n\nFAIL: 缺少异常处理逻辑，不符合规范要求。\n\nPASS: 接口定义清晰。"
        result = guard.check(output)
        assert result.has_overcorrection
        assert len(result.fail_without_evidence) == 1
        assert "缺少异常处理" in result.fail_without_evidence[0]

    def test_fail_with_evidence_passes(self):
        from dqg.quality.rationalization_guard import OvercorrectionGuard

        guard = OvercorrectionGuard()
        output = (
            "FAIL: 空指针风险。\nOrderService.java:88 — getOrder() 返回值未做 null 检查，下游 calculateTotal() 会 NPE。"
        )
        result = guard.check(output)
        # Has evidence, so fail_without_evidence should be empty
        assert result.fail_without_evidence == []

    def test_detect_theoretical_risk_as_blocker(self):
        from dqg.quality.rationalization_guard import OvercorrectionGuard

        guard = OvercorrectionGuard()
        output = "潜在风险较大，判定 BLOCKER。"
        result = guard.check(output)
        assert result.has_overcorrection
        assert len(result.confirmed_overcorrections) >= 1

    def test_format_overcorrection_warning(self):
        from dqg.quality.rationalization_guard import (
            OvercorrectionResult,
            format_overcorrection_warning,
        )

        result = OvercorrectionResult(
            has_overcorrection=True,
            confirmed_overcorrections=["虽然代码逻辑正确但不符合规范"],
            fail_without_evidence=["FAIL: 缺少注释"],
        )
        warning = format_overcorrection_warning(result)
        assert "过度纠正" in warning
        assert "FAIL 缺少证据行号" in warning
        assert "SUGGESTION" in warning


# ---------------------------------------------------------------------------
# code_skeleton (TREEFRAG) 测试
# ---------------------------------------------------------------------------


class TestCodeSkeleton:
    SAMPLE_JAVA = textwrap.dedent("""\
        package com.example;

        import java.util.List;

        public class OrderService {
            private final OrderRepository repo;

            public OrderService(OrderRepository repo) {
                this.repo = repo;
            }

            public Order getOrder(Long id) {
                Order order = repo.findById(id);
                if (order == null) {
                    throw new NotFoundException("Order not found: " + id);
                }
                return order;
            }

            public List<Order> listOrders(String userId) {
                return repo.findByUserId(userId);
            }

            private void validateOrder(Order order) {
                if (order.getAmount() <= 0) {
                    throw new IllegalArgumentException("Invalid amount");
                }
                if (order.getStatus() == null) {
                    throw new IllegalArgumentException("Status required");
                }
            }
        }
    """)

    def test_regex_skeleton_no_expand(self):
        from dqg.context.code_skeleton import extract_skeleton_regex

        result = extract_skeleton_regex(self.SAMPLE_JAVA)
        assert result.total_lines > result.skeleton_lines
        assert result.compression_ratio > 1.0
        assert "{ ... }" in result.skeleton_text
        # 方法签名应保留
        assert "getOrder" in result.skeleton_text
        assert "listOrders" in result.skeleton_text
        assert "validateOrder" in result.skeleton_text
        # 方法体应被省略
        assert "NotFoundException" not in result.skeleton_text
        assert result.expanded_methods == []

    def test_regex_skeleton_with_expand(self):
        from dqg.context.code_skeleton import extract_skeleton_regex

        result = extract_skeleton_regex(self.SAMPLE_JAVA, expand_methods={"getOrder"})
        # getOrder 应展开
        assert "NotFoundException" in result.skeleton_text
        assert "getOrder" in result.expanded_methods
        # listOrders 应折叠
        assert "findByUserId" not in result.skeleton_text

    def test_extract_skeleton_unified(self):
        """统一入口：tree-sitter 或 regex 都应返回有效结果."""
        from dqg.context.code_skeleton import extract_skeleton

        result = extract_skeleton(self.SAMPLE_JAVA)
        assert result.skeleton_lines > 0
        assert result.compression_ratio >= 1.0
        assert "getOrder" in result.skeleton_text

    def test_extract_skeleton_with_oracle(self):
        """Oracle 标注：只展开相关方法."""
        from dqg.context.code_skeleton import extract_skeleton

        result = extract_skeleton(self.SAMPLE_JAVA, expand_methods={"validateOrder"})
        assert "validateOrder" in result.expanded_methods
        # validateOrder 方法体应展开
        assert "Invalid amount" in result.skeleton_text
        # getOrder 方法体应折叠
        assert "NotFoundException" not in result.skeleton_text

    def test_extract_skeleton_for_files(self, tmp_path):
        from dqg.context.code_skeleton import extract_skeleton_for_files

        java_file = tmp_path / "OrderService.java"
        java_file.write_text(self.SAMPLE_JAVA)

        results = extract_skeleton_for_files(
            [java_file],
            se_code_mapping={str(java_file): ["getOrder"]},
        )
        assert str(java_file) in results
        r = results[str(java_file)]
        assert "getOrder" in r.expanded_methods
        assert r.compression_ratio >= 1.0

    def test_empty_source(self):
        from dqg.context.code_skeleton import extract_skeleton

        result = extract_skeleton("")
        assert result.skeleton_lines == 0 or result.skeleton_text.strip() == ""

    def test_case_insensitive_expand(self):
        """方法名匹配应大小写不敏感."""
        from dqg.context.code_skeleton import extract_skeleton_regex

        result = extract_skeleton_regex(self.SAMPLE_JAVA, expand_methods={"GETORDER"})
        assert "getOrder" in result.expanded_methods


# ---------------------------------------------------------------------------
# demand_trace 测试
# ---------------------------------------------------------------------------


class TestDemandTrace:
    def test_trace_downstream_basic(self):
        from dqg.quality.demand_trace import trace_downstream

        graph = {
            "Controller.handleOrder": {
                "file": "Controller.java",
                "line": 10,
                "calls": ["Service.createOrder"],
                "called_by": [],
            },
            "Service.createOrder": {
                "file": "Service.java",
                "line": 20,
                "calls": ["Repo.save", "Validator.check"],
                "called_by": ["Controller.handleOrder"],
            },
            "Repo.save": {
                "file": "Repo.java",
                "line": 30,
                "calls": [],
                "called_by": ["Service.createOrder"],
            },
            "Validator.check": {
                "file": "Validator.java",
                "line": 40,
                "calls": ["Validator.checkAmount"],
                "called_by": ["Service.createOrder"],
            },
            "Validator.checkAmount": {
                "file": "Validator.java",
                "line": 50,
                "calls": [],
                "called_by": ["Validator.check"],
            },
        }

        result = trace_downstream(graph, ["Controller.handleOrder"], max_depth=3)
        methods = {t["method"] for t in result["traced_methods"]}
        assert "Controller.handleOrder" in methods
        assert "Service.createOrder" in methods
        assert "Repo.save" in methods
        assert "Validator.check" in methods
        assert "Validator.checkAmount" in methods
        assert len(result["traced_files"]) == 4

    def test_trace_downstream_depth_limit(self):
        from dqg.quality.demand_trace import trace_downstream

        graph = {
            "A.a": {"file": "A.java", "line": 1, "calls": ["B.b"], "called_by": []},
            "B.b": {"file": "B.java", "line": 1, "calls": ["C.c"], "called_by": ["A.a"]},
            "C.c": {"file": "C.java", "line": 1, "calls": ["D.d"], "called_by": ["B.b"]},
            "D.d": {"file": "D.java", "line": 1, "calls": [], "called_by": ["C.c"]},
        }

        result = trace_downstream(graph, ["A.a"], max_depth=1)
        methods = {t["method"] for t in result["traced_methods"]}
        assert "A.a" in methods
        assert "B.b" in methods
        assert "C.c" not in methods  # depth 2, beyond limit

    def test_trace_downstream_empty_graph(self):
        from dqg.quality.demand_trace import trace_downstream

        result = trace_downstream({}, ["Missing.method"])
        assert result["traced_methods"] == []
        assert result["traced_files"] == []

    def test_extract_entry_methods(self):
        from dqg.quality.demand_trace import _extract_entry_methods

        se_data = {
            "mappings": [
                {
                    "se_id": "SE-001",
                    "coverage": "FOUND",
                    "code_matches": [
                        {"class": "OrderService", "method": "createOrder"},
                        {"class": "OrderService", "method": "validateOrder"},
                    ],
                },
                {
                    "se_id": "SE-002",
                    "coverage": "NOT_FOUND",
                    "code_matches": [],
                },
                {
                    "se_id": "SE-003",
                    "coverage": "FOUND",
                    "code_matches": [
                        {"class": "PaymentService", "method": "charge"},
                    ],
                },
            ],
        }

        entries = _extract_entry_methods(se_data)
        assert "OrderService.createOrder" in entries
        assert "OrderService.validateOrder" in entries
        assert "PaymentService.charge" in entries
        assert len(entries) == 3

    def test_compute_overlap(self):
        from dqg.quality.demand_trace import _compute_overlap

        trace = {
            "traced_methods": [
                {"method": "A.a"},
                {"method": "B.b"},
                {"method": "C.c"},
            ],
        }
        blast = {
            "changed_methods": ["B.b", "D.d"],
            "affected_callers": ["E.e"],
        }

        overlap = _compute_overlap(trace, blast)
        assert overlap["overlap_count"] == 1  # B.b
        assert overlap["trace_only_count"] == 2  # A.a, C.c
        assert overlap["blast_only_count"] == 2  # D.d, E.e
        assert overlap["recommendation"] == "HIGH_CONFIDENCE"

    def test_compute_overlap_no_intersection(self):
        from dqg.quality.demand_trace import _compute_overlap

        trace = {"traced_methods": [{"method": "A.a"}]}
        blast = {"changed_methods": ["B.b"], "affected_callers": []}

        overlap = _compute_overlap(trace, blast)
        assert overlap["overlap_count"] == 0
        assert overlap["recommendation"] == "COMPLEMENTARY"


# ---------------------------------------------------------------------------
# requirement_smell 测试
# ---------------------------------------------------------------------------


class TestRequirementSmell:
    def test_detect_vague(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "系统应适当控制并发请求数量，尽量保证响应速度。"
        report = detect_smells(text)
        types = {s.smell_type for s in report.smells}
        assert "VAGUE" in types

    def test_detect_subjective(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "界面设计要美观，交互流畅。"
        report = detect_smells(text)
        types = {s.smell_type for s in report.smells}
        assert "SUBJECTIVE" in types

    def test_detect_unbounded(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "支持所有用户同时在线，数据量不限。"
        report = detect_smells(text)
        types = {s.smell_type for s in report.smells}
        assert "UNBOUNDED" in types

    def test_detect_incomplete(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "优化查询性能，提升用户体验。"
        report = detect_smells(text)
        types = {s.smell_type for s in report.smells}
        assert "INCOMPLETE" in types

    def test_detect_contradictory(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "该接口必须同步返回结果，同时支持异步回调通知。"
        report = detect_smells(text)
        types = {s.smell_type for s in report.smells}
        assert "CONTRADICTORY" in types

    def test_clean_requirement(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "用户提交订单后，系统在3秒内返回订单号，状态为PENDING。"
        report = detect_smells(text)
        assert report.quality_score == 1.0
        assert len(report.smells) == 0

    def test_quality_score_degrades(self):
        from dqg.quality.requirement_smell import detect_smells

        text = "系统应适当处理并发请求。\n所有用户数据不限容量。\n界面要美观大方。\n"
        report = detect_smells(text)
        assert report.quality_score < 1.0
        assert len(report.smells) >= 3

    def test_get_smell_lines(self):
        from dqg.quality.requirement_smell import detect_smells, get_smell_lines

        text = "正常需求描述。\n系统应适当处理请求。\n另一条正常需求。"
        report = detect_smells(text)
        lines = get_smell_lines(report)
        assert 2 in lines  # 第二行有 smell
        assert 1 not in lines
        assert 3 not in lines

    def test_dedup_same_line_same_type(self):
        from dqg.quality.requirement_smell import detect_smells

        # 同一行多个模糊词只保留一条 VAGUE
        text = "系统应适当且尽量保证合理的响应速度。"
        report = detect_smells(text)
        vague_on_line1 = [s for s in report.smells if s.smell_type == "VAGUE" and s.line_number == 1]
        assert len(vague_on_line1) == 1


# ---------------------------------------------------------------------------
# requirement_graph 测试
# ---------------------------------------------------------------------------


class TestRequirementGraph:
    SAMPLE_DATA = {
        "requirements": [
            {"req_id": "REQ-001", "parent_id": "", "description": "订单管理功能"},
            {"req_id": "BR-001", "parent_id": "REQ-001", "description": "创建订单"},
            {"req_id": "BR-002", "parent_id": "REQ-001", "description": "取消订单"},
            {"req_id": "BR-003", "parent_id": "REQ-001", "description": "修改订单"},
            {"req_id": "REQ-002", "parent_id": "", "description": "孤立需求无分解"},
        ],
        "semantic_expectations": [
            {"se_id": "SE-001", "description": "创建订单校验", "mapping_target": "BR-001"},
            {"se_id": "SE-002", "description": "取消订单状态机", "mapping_target": "BR-002"},
            {"se_id": "SE-003", "description": "无关联的SE", "mapping_target": ""},
        ],
        "gaps": [
            {"gap_id": "GAP-001", "related_ids": ["BR-003"], "description": "修改订单缺少并发控制"},
            {"gap_id": "GAP-002", "related_ids": [], "description": "悬空GAP"},
        ],
        "open_items": [
            {"open_id": "OPEN-001", "related_ids": ["REQ-001"], "question": "订单上限？"},
            {"open_id": "OPEN-002", "related_ids": [], "question": "悬空OPEN"},
        ],
    }

    def test_build_graph(self):
        from dqg.quality.requirement_graph import build_requirement_graph

        G = build_requirement_graph(self.SAMPLE_DATA)
        assert G is not None
        # 5 reqs + 3 SE + 2 GAP + 2 OPEN = 12
        assert G.number_of_nodes() == 12

    def test_detect_uncovered_br(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph(self.SAMPLE_DATA)
        result = analyze_requirement_graph(G)
        uncovered = [a for a in result.anomalies if a.anomaly_type == "UNCOVERED_BR"]
        # BR-003 has no SE mapping
        assert any(a.node_id == "BR-003" for a in uncovered)

    def test_detect_orphan_se(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph(self.SAMPLE_DATA)
        result = analyze_requirement_graph(G)
        orphans = [a for a in result.anomalies if a.anomaly_type == "ORPHAN_SE"]
        # SE-003 has no mapping_target
        assert any(a.node_id == "SE-003" for a in orphans)

    def test_detect_isolated_req(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph(self.SAMPLE_DATA)
        result = analyze_requirement_graph(G)
        isolated = [a for a in result.anomalies if a.anomaly_type == "ISOLATED_REQ"]
        # REQ-002 has no children and no SE
        assert any(a.node_id == "REQ-002" for a in isolated)
        # REQ-001 has children, should NOT be isolated
        assert not any(a.node_id == "REQ-001" for a in isolated)

    def test_detect_dangling_gap_and_open(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph(self.SAMPLE_DATA)
        result = analyze_requirement_graph(G)
        dangling_gaps = [a for a in result.anomalies if a.anomaly_type == "DANGLING_GAP"]
        dangling_opens = [a for a in result.anomalies if a.anomaly_type == "DANGLING_OPEN"]
        assert any(a.node_id == "GAP-002" for a in dangling_gaps)
        assert any(a.node_id == "OPEN-002" for a in dangling_opens)

    def test_coverage_summary(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph(self.SAMPLE_DATA)
        result = analyze_requirement_graph(G)
        # BR-001 and BR-002 covered by SE, BR-003 not → 2/3 ≈ 0.67
        assert result.coverage_summary["br_se_coverage"] == pytest.approx(0.67, abs=0.01)

    def test_empty_data(self):
        from dqg.quality.requirement_graph import (
            analyze_requirement_graph,
            build_requirement_graph,
        )

        G = build_requirement_graph({"requirements": [{"req_id": "REQ-001", "description": "solo"}]})
        result = analyze_requirement_graph(G)
        assert result.node_count == 1
        assert result.req_count == 1
        # Solo REQ with no children and no SE → ISOLATED_REQ
        assert any(a.anomaly_type == "ISOLATED_REQ" for a in result.anomalies)
