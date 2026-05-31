from __future__ import annotations

import json
from pathlib import Path

from qualix.languages.go.provider import GoProvider
from qualix.languages.python.provider import PythonProvider
from qualix.languages.registry import LanguageRegistry, get_registry
from qualix.languages.typescript.provider import TypeScriptProvider


def test_registry_registers_public_language_providers() -> None:
    registry = get_registry()
    languages = set(registry.registered_languages)
    assert {"java", "typescript", "go", "python"}.issubset(languages)


def test_registry_detects_typescript_go_python(tmp_path: Path) -> None:
    registry = LanguageRegistry()
    registry.register(TypeScriptProvider())
    registry.register(GoProvider())
    registry.register(PythonProvider())

    ts_repo = tmp_path / "ts"
    ts_repo.mkdir()
    (ts_repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    assert registry.detect(ts_repo).language_id == "typescript"  # type: ignore[union-attr]

    go_repo = tmp_path / "go"
    go_repo.mkdir()
    (go_repo / "go.mod").write_text("module example.com/app\n", encoding="utf-8")
    assert registry.detect(go_repo).language_id == "go"  # type: ignore[union-attr]

    py_repo = tmp_path / "py"
    py_repo.mkdir()
    (py_repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    assert registry.detect(py_repo).language_id == "python"  # type: ignore[union-attr]


def test_go_provider_detects_framework_dependencies_and_tests(tmp_path: Path) -> None:
    repo = tmp_path / "go-app"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/app\nrequire github.com/stretchr/testify v1.8.0\n",
        encoding="utf-8",
    )
    (repo / "policy_test.go").write_text(
        """
package policy

import "testing"

func TestApproval(t *testing.T) {
    assert.NotNil(t, buildRequest())
}
""",
        encoding="utf-8",
    )

    provider = GoProvider()
    assert provider.detect(repo) == 0.95
    assert provider.detect_test_framework(repo).name == "go-test"  # type: ignore[union-attr]
    assert provider.resolve_test_dependencies(repo) == ["testify"]
    methods = provider.parse_test_methods((repo / "policy_test.go").read_text(encoding="utf-8"))
    assert methods[0].name == "TestApproval"
    weak = provider.analyze_weak_asserts((repo / "policy_test.go").read_text(encoding="utf-8"))
    assert weak and weak[0].signals[0].code == "WEAK_ASSERT_ONLY"


def test_python_provider_detects_pytest_and_weak_asserts(tmp_path: Path) -> None:
    repo = tmp_path / "py-app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        json.dumps({"project": {"name": "demo"}, "tool": {"pytest": {"ini_options": {}}}}),
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    test_content = """
def test_returns_result():
    result = build_result()
    assert result

def test_amount_boundary():
    assert classify_amount(500) == "finance_required"
"""

    provider = PythonProvider()
    assert provider.detect(repo) == 0.95
    assert provider.detect_test_framework(repo).name == "pytest"  # type: ignore[union-attr]
    methods = provider.parse_test_methods(test_content)
    assert [m.name for m in methods] == ["test_returns_result", "test_amount_boundary"]
    weak = provider.analyze_weak_asserts(test_content)
    assert len(weak) == 1
    assert weak[0].method_name == "test_returns_result"
    assert provider.locate_test_file(repo / "policy.py") == repo / "test_policy.py"


def test_public_profiles_include_python() -> None:
    from qualix.core.profiles import get_profile, list_profiles

    profile_ids = {item.profile_id for item in list_profiles()}
    assert "python-service" in profile_ids
    assert get_profile("python-service").language == "python"

