"""测试 mock_consistency_check.py 的各种场景."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from qualix.quality.checks.mock_consistency_check import check_mock_consistency


# ---------------------------------------------------------------------------
# 辅助：在临时目录里创建 Java 测试文件
# ---------------------------------------------------------------------------

def _write_java_test(tmp_path: Path, filename: str, content: str) -> Path:
    """在 tmp_path/src/test/java/ 下创建 Java 文件，返回文件路径."""
    test_dir = tmp_path / "src" / "test" / "java"
    test_dir.mkdir(parents=True, exist_ok=True)
    java_file = test_dir / filename
    java_file.write_text(textwrap.dedent(content), encoding="utf-8")
    return java_file


# ---------------------------------------------------------------------------
# 场景 1: DomainService + Repository mock → 无 warning
# ---------------------------------------------------------------------------

class TestDomainServiceWithRepository:
    def test_no_warning_when_domain_service_mocks_repository(self, tmp_path: Path):
        _write_java_test(tmp_path, "OrderDomainServiceTest.java", """
            @ExtendWith(MockitoExtension.class)
            class OrderDomainServiceTest {
                @InjectMocks
                OrderDomainService orderDomainService;

                @Mock
                OrderRepository orderRepository;

                @Test
                void shouldPlaceOrder() {
                    when(orderRepository.save(any())).thenReturn(new Order());
                    orderDomainService.placeOrder(new Order());
                    verify(orderRepository).save(any());
                }
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        assert result == [], f"预期无 warning，实际得到: {result}"


# ---------------------------------------------------------------------------
# 场景 2: ApplicationService 直接 Mock Repository → 产生 WARNING
# ---------------------------------------------------------------------------

class TestApplicationServiceMocksRepositoryDirectly:
    def test_warning_when_app_service_mocks_repository(self, tmp_path: Path):
        _write_java_test(tmp_path, "OrderApplicationServiceTest.java", """
            @ExtendWith(MockitoExtension.class)
            class OrderApplicationServiceTest {
                @InjectMocks
                OrderApplicationService orderApplicationService;

                @Mock
                OrderRepository orderRepository;

                @Test
                void shouldConfirmOrder() {
                    orderApplicationService.confirm("ORD-1");
                    verify(orderRepository).findById("ORD-1");
                }
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        assert len(result) >= 1
        # 检查 warning 提及了字段名
        combined = "\n".join(result)
        assert "OrderApplicationService" in combined
        assert "OrderRepository" in combined or "orderRepository" in combined
        assert all(w.startswith("WARNING:") for w in result), (
            f"Mock 一致性检查只能产生 WARNING，不能有 BLOCKED: {result}"
        )

    def test_warning_names_the_field(self, tmp_path: Path):
        """WARNING 消息必须点名具体字段名."""
        _write_java_test(tmp_path, "PaymentApplicationServiceTest.java", """
            @ExtendWith(MockitoExtension.class)
            class PaymentApplicationServiceTest {
                @InjectMocks
                PaymentApplicationService paymentApplicationService;

                @Mock
                PaymentRepository paymentRepository;
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        combined = "\n".join(result)
        # 字段类型或字段名必须出现在消息中
        assert "PaymentRepository" in combined or "paymentRepository" in combined


# ---------------------------------------------------------------------------
# 场景 3: 内部类上使用 @InjectMocks → WARNING 提及内部类
# ---------------------------------------------------------------------------

class TestInnerClassInjectMocks:
    def test_warning_for_inner_class_inject_mocks(self, tmp_path: Path):
        _write_java_test(tmp_path, "OuterTest.java", """
            @ExtendWith(MockitoExtension.class)
            class OuterTest {
                @InjectMocks
                Outer$InnerService innerService;

                @Mock
                SomeDependency dep;
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        assert len(result) >= 1
        combined = "\n".join(result)
        assert "InnerService" in combined or "$" in combined
        assert all(w.startswith("WARNING:") for w in result)


# ---------------------------------------------------------------------------
# 场景 4: 无 @InjectMocks → 空列表
# ---------------------------------------------------------------------------

class TestNoInjectMocks:
    def test_empty_result_when_no_inject_mocks(self, tmp_path: Path):
        _write_java_test(tmp_path, "PlainTest.java", """
            class PlainTest {
                @Mock
                OrderRepository orderRepository;

                @Test
                void test() {
                    assertNotNull(orderRepository);
                }
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        assert result == []


# ---------------------------------------------------------------------------
# 场景 5: ApplicationService Mock DomainService → 无 WARNING（正确分层）
# ---------------------------------------------------------------------------

class TestApplicationServiceMocksDomainService:
    def test_no_warning_when_app_service_mocks_domain_service(self, tmp_path: Path):
        _write_java_test(tmp_path, "OrderApplicationServiceTest.java", """
            @ExtendWith(MockitoExtension.class)
            class OrderApplicationServiceTest {
                @InjectMocks
                OrderApplicationService orderApplicationService;

                @Mock
                OrderDomainService orderDomainService;

                @Test
                void shouldDelegateToOrderDomainService() {
                    when(orderDomainService.confirm("ORD-1")).thenReturn(new Order());
                    orderApplicationService.confirm("ORD-1");
                    verify(orderDomainService).confirm("ORD-1");
                }
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        assert result == [], f"正确分层（AppService mock DomainService）不应产生 warning，实际: {result}"


# ---------------------------------------------------------------------------
# 场景 6: 空仓库列表 → 空列表
# ---------------------------------------------------------------------------

class TestEmptyRepoList:
    def test_empty_result_for_empty_repo_list(self, tmp_path: Path):
        result = check_mock_consistency(tmp_path, "proj1", [])
        assert result == []


# ---------------------------------------------------------------------------
# 场景 7: 不存在的仓库路径 → 空列表（不崩溃）
# ---------------------------------------------------------------------------

class TestNonExistentRepo:
    def test_no_crash_for_nonexistent_repo(self, tmp_path: Path):
        result = check_mock_consistency(tmp_path, "proj1", ["/nonexistent/path/to/repo"])
        assert result == []


# ---------------------------------------------------------------------------
# 场景 8: 返回值永远不含 BLOCKED
# ---------------------------------------------------------------------------

class TestNeverBlocked:
    def test_results_never_contain_blocked(self, tmp_path: Path):
        """check_mock_consistency 是 advisory，任何情况都不返回 BLOCKED."""
        # 创建一个有问题的文件
        _write_java_test(tmp_path, "BrokenLayerTest.java", """
            @ExtendWith(MockitoExtension.class)
            class BrokenLayerApplicationServiceTest {
                @InjectMocks
                BrokenLayerApplicationService svc;

                @Mock
                BrokenLayerRepository repo;

                @Mock
                BrokenLayerMapper mapper;
            }
        """)

        result = check_mock_consistency(tmp_path, "proj1", [str(tmp_path)])
        for item in result:
            assert not item.startswith("BLOCKED:"), (
                f"mock_consistency_check 不应产生 BLOCKED，但发现: {item}"
            )
