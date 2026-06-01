"""tests/test_import_whitelist_check.py

测试 import_whitelist_check 的所有场景：
- 标准前缀（java.*, org.junit.* 等）→ 无 warning
- 已知类 → 无 warning
- 幻觉类 → WARNING
- >50% 无法识别 → BLOCKED
- <50% 无法识别 → 只有 WARNING，没有 BLOCKED
- 空 import 文件 → 无 warning
- 缺失 _q05_target_modules.json → fail-open，返回空列表
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from qualix.quality.checks.import_whitelist_check import (
    _check_single_file,
    _extract_known_classes,
    check_import_whitelist,
)


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _write_java(tmp_path: Path, name: str, content: str) -> Path:
    """在 tmp_path/src/test/java 下创建 Java 文件."""
    test_root = tmp_path / "repo" / "src" / "test" / "java"
    test_root.mkdir(parents=True, exist_ok=True)
    f = test_root / name
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return f


def _write_target_modules(output_dir: Path, project_id: str, data: dict) -> Path:
    """写入 _q05_target_modules.json 到对应 _internal 路径.

    Args:
        output_dir: Qualix 输出根目录（传入 tmp_path / "output"）。
    """
    int_dir = output_dir / project_id / "Q05b" / "_internal"
    int_dir.mkdir(parents=True, exist_ok=True)
    path = int_dir / "_q05_target_modules.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _extract_known_classes 单元测试
# ---------------------------------------------------------------------------

class TestExtractKnownClasses:
    def test_extracts_from_se_mappings(self):
        data = {
            "se_mappings": [
                {"item_id": "SE-001", "impl_class": "com.example.OrderService", "found": True},
            ]
        }
        known = _extract_known_classes(data)
        assert "com.example.OrderService" in known
        assert "OrderService" in known

    def test_extracts_from_br_mappings(self):
        data = {
            "br_mappings": [
                {"item_id": "BR-001", "impl_class": "com.example.PaymentGateway", "found": True},
            ]
        }
        known = _extract_known_classes(data)
        assert "PaymentGateway" in known

    def test_extracts_from_code_symbols(self):
        data = {
            "code_symbols": [
                {"name": "InventoryManager", "kind": "class", "file": "InventoryManager.java"},
            ]
        }
        known = _extract_known_classes(data)
        assert "InventoryManager" in known

    def test_empty_data(self):
        assert _extract_known_classes({}) == set()


# ---------------------------------------------------------------------------
# _check_single_file 单元测试
# ---------------------------------------------------------------------------

class TestCheckSingleFile:
    def test_standard_prefix_java_no_warning(self, tmp_path):
        f = tmp_path / "FooTest.java"
        f.write_text(
            "import java.util.List;\nimport java.util.Map;\nclass FooTest {}\n",
            encoding="utf-8",
        )
        assert _check_single_file(f, set()) == []

    def test_junit_no_warning(self, tmp_path):
        f = tmp_path / "BarTest.java"
        f.write_text(
            "import org.junit.jupiter.api.Test;\nimport org.assertj.core.api.Assertions;\nclass BarTest {}\n",
            encoding="utf-8",
        )
        assert _check_single_file(f, set()) == []

    def test_known_class_no_warning(self, tmp_path):
        f = tmp_path / "OrderServiceTest.java"
        f.write_text(
            "import com.example.OrderService;\nclass OrderServiceTest {}\n",
            encoding="utf-8",
        )
        known = {"com.example.OrderService", "OrderService"}
        assert _check_single_file(f, known) == []

    def test_phantom_import_warning(self, tmp_path):
        f = tmp_path / "GhostTest.java"
        f.write_text(
            "import com.example.NonExistentHelper;\nclass GhostTest {}\n",
            encoding="utf-8",
        )
        results = _check_single_file(f, set())
        # 1 条无法识别的 import → WARNING（+ 可能触发 BLOCKED，因为 1/1=100% > 50%）
        warnings = [r for r in results if r.startswith("WARNING:")]
        assert len(warnings) >= 1
        assert "com.example.NonExistentHelper" in warnings[0]
        assert "GhostTest.java" in warnings[0]

    def test_blocked_when_majority_unrecognized(self, tmp_path):
        """3 out of 4 non-standard imports unrecognized → BLOCKED."""
        f = tmp_path / "BigTest.java"
        f.write_text(
            "\n".join([
                "import com.example.RealService;",        # known
                "import com.example.Ghost1;",             # unknown
                "import com.example.Ghost2;",             # unknown
                "import com.example.Ghost3;",             # unknown
                "class BigTest {}",
            ]),
            encoding="utf-8",
        )
        known = {"com.example.RealService", "RealService"}
        results = _check_single_file(f, known)
        # 3 警告 + 1 BLOCKED
        warnings = [r for r in results if r.startswith("WARNING:")]
        blocked = [r for r in results if r.startswith("BLOCKED:")]
        assert len(warnings) == 3
        assert len(blocked) == 1
        assert ">50%" in blocked[0]
        assert "3/4" in blocked[0]

    def test_warning_only_when_minority_unrecognized(self, tmp_path):
        """1 out of 4 non-standard imports unrecognized → WARNING only, no BLOCKED."""
        f = tmp_path / "SmallTest.java"
        f.write_text(
            "\n".join([
                "import com.example.RealA;",
                "import com.example.RealB;",
                "import com.example.RealC;",
                "import com.example.Ghost1;",
                "class SmallTest {}",
            ]),
            encoding="utf-8",
        )
        known = {
            "com.example.RealA", "RealA",
            "com.example.RealB", "RealB",
            "com.example.RealC", "RealC",
        }
        results = _check_single_file(f, known)
        warnings = [r for r in results if r.startswith("WARNING:")]
        blocked = [r for r in results if r.startswith("BLOCKED:")]
        assert len(warnings) == 1
        assert len(blocked) == 0

    def test_empty_file_no_warnings(self, tmp_path):
        f = tmp_path / "EmptyTest.java"
        f.write_text("class EmptyTest {}\n", encoding="utf-8")
        assert _check_single_file(f, set()) == []

    def test_wildcard_import_ignored(self, tmp_path):
        """通配符 import（com.example.*）不触发 WARNING."""
        f = tmp_path / "WildTest.java"
        f.write_text("import com.example.*;\nclass WildTest {}\n", encoding="utf-8")
        assert _check_single_file(f, set()) == []

    def test_static_import_standard_no_warning(self, tmp_path):
        f = tmp_path / "StaticTest.java"
        f.write_text(
            "import static org.assertj.core.api.Assertions.assertThat;\nclass StaticTest {}\n",
            encoding="utf-8",
        )
        assert _check_single_file(f, set()) == []

    def test_lombok_no_warning(self, tmp_path):
        f = tmp_path / "LombokTest.java"
        f.write_text(
            "import lombok.Data;\nimport lombok.Builder;\nclass LombokTest {}\n",
            encoding="utf-8",
        )
        assert _check_single_file(f, set()) == []


# ---------------------------------------------------------------------------
# check_import_whitelist 集成测试（使用 tmp_path 模拟文件结构）
# 真实 state_machine 的 internal_dir(output_dir, project_id, phase_def_q05b)
# 返回 output_dir / project_id / "Q05b" / "_internal"
# 与 _write_target_modules 写入路径一致，无需 monkeypatch。
# ---------------------------------------------------------------------------

class TestCheckImportWhitelist:
    def test_missing_target_modules_fail_open(self, tmp_path):
        """缺失 _q05_target_modules.json → fail-open，返回空列表."""
        project_id = "proj_test"
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        # 不创建 _q05_target_modules.json
        result = check_import_whitelist(output_dir, project_id, [])
        assert result == []

    def test_phantom_import_triggers_warning(self, tmp_path):
        """幻觉 import → 返回 WARNING 行."""
        project_id = "proj_phantom"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [
                {"item_id": "SE-001", "impl_class": "com.example.OrderService", "found": True, "repo": ""},
            ],
            "br_mappings": [],
            "code_symbols": [],
            "git_diff_files": [],
        })

        _write_java(tmp_path, "GhostTest.java",
            "import com.example.NonExistentHelper;\nclass GhostTest {}\n")

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        assert any("WARNING: import whitelist:" in r for r in result)
        assert any("NonExistentHelper" in r for r in result)

    def test_known_class_no_warning(self, tmp_path):
        """从 target_modules 里的已知类 → 无 warning."""
        project_id = "proj_known"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [
                {"item_id": "SE-001", "impl_class": "com.example.OrderService", "found": True, "repo": ""},
            ],
            "br_mappings": [],
            "code_symbols": [],
            "git_diff_files": [],
        })

        _write_java(tmp_path, "OrderServiceTest.java",
            "import com.example.OrderService;\nclass OrderServiceTest {}\n")

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        assert result == []

    def test_standard_prefix_no_warning(self, tmp_path):
        """标准前缀 import → 无 warning."""
        project_id = "proj_std"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [], "br_mappings": [], "code_symbols": [], "git_diff_files": [],
        })

        _write_java(tmp_path, "StdTest.java",
            "import java.util.List;\nimport org.junit.jupiter.api.Test;\nclass StdTest {}\n")

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        assert result == []

    def test_majority_unrecognized_blocked(self, tmp_path):
        """3/4 非标准 import 无法识别 → 包含 BLOCKED 行."""
        project_id = "proj_blocked"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [
                {"item_id": "SE-001", "impl_class": "com.example.RealService", "found": True, "repo": ""},
            ],
            "br_mappings": [], "code_symbols": [], "git_diff_files": [],
        })

        _write_java(tmp_path, "BigTest.java", "\n".join([
            "import com.example.RealService;",
            "import com.example.Ghost1;",
            "import com.example.Ghost2;",
            "import com.example.Ghost3;",
            "class BigTest {}",
        ]))

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        blocked = [r for r in result if r.startswith("BLOCKED:")]
        assert len(blocked) == 1

    def test_minority_unrecognized_no_blocked(self, tmp_path):
        """1/4 非标准 import 无法识别 → 只有 WARNING，无 BLOCKED."""
        project_id = "proj_warn_only"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [
                {"item_id": "SE-001", "impl_class": "com.example.RealA", "found": True, "repo": ""},
                {"item_id": "SE-002", "impl_class": "com.example.RealB", "found": True, "repo": ""},
                {"item_id": "SE-003", "impl_class": "com.example.RealC", "found": True, "repo": ""},
            ],
            "br_mappings": [], "code_symbols": [], "git_diff_files": [],
        })

        _write_java(tmp_path, "SmallTest.java", "\n".join([
            "import com.example.RealA;",
            "import com.example.RealB;",
            "import com.example.RealC;",
            "import com.example.Ghost1;",
            "class SmallTest {}",
        ]))

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        blocked = [r for r in result if r.startswith("BLOCKED:")]
        warnings = [r for r in result if r.startswith("WARNING:")]
        assert len(blocked) == 0
        assert len(warnings) >= 1

    def test_empty_test_file_no_warnings(self, tmp_path):
        """空 import 文件 → 无 warning."""
        project_id = "proj_empty"
        output_dir = tmp_path / "output"

        _write_target_modules(output_dir, project_id, {
            "se_mappings": [], "br_mappings": [], "code_symbols": [], "git_diff_files": [],
        })

        _write_java(tmp_path, "EmptyTest.java", "class EmptyTest {}\n")

        code_repos = [str(tmp_path / "repo")]
        result = check_import_whitelist(output_dir, project_id, code_repos)
        assert result == []
