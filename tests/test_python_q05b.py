"""Python Q05b: compile_check + import_check + mock template tests."""

from __future__ import annotations

from pathlib import Path

from qualix.languages.python.provider import PythonProvider, _find_test_files, _import_check

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_py_project(tmp_path: Path, with_pytest_mock: bool = False) -> Path:
    repo = tmp_path / "py-app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        + ("pytest-mock\n" if with_pytest_mock else "")
    )
    (repo / "src").mkdir()
    (repo / "src" / "approval.py").write_text(
        "from decimal import Decimal\n\n"
        "class ApprovalService:\n"
        "    def classify(self, amount: Decimal) -> str:\n"
        "        if amount >= Decimal('500'):\n"
        "            return 'MANAGER_AND_FINANCE'\n"
        "        return 'MANAGER_ONLY'\n"
    )
    return repo


# ---------------------------------------------------------------------------
# compile_check: syntax error caught by compileall
# ---------------------------------------------------------------------------

class TestCompileCheck:
    def test_valid_project_passes(self, tmp_path: Path):
        repo = _make_py_project(tmp_path)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_approval.py").write_text(
            "def test_dummy(): assert 1 == 1\n"
        )
        provider = PythonProvider()
        result = provider.compile_check(repo)
        assert result.passed is True

    def test_syntax_error_blocked(self, tmp_path: Path):
        repo = _make_py_project(tmp_path)
        (repo / "tests").mkdir()
        (repo / "tests" / "test_bad.py").write_text("def broken(\n")  # syntax error
        provider = PythonProvider()
        result = provider.compile_check(repo)
        assert result.passed is False
        assert result.error_summary  # has diagnostic text


# ---------------------------------------------------------------------------
# import_check: catches missing imports that compileall misses
# ---------------------------------------------------------------------------

class TestImportCheck:
    def test_valid_test_file_passes(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        tf = repo / "test_ok.py"
        tf.write_text("import os\ndef test_dummy(): assert os.sep\n")
        result = _import_check(repo, [tf])
        assert result.passed is True

    def test_src_layout_import_passes(self, tmp_path: Path):
        repo = tmp_path / "proj"
        (repo / "src" / "app").mkdir(parents=True)
        (repo / "src" / "app" / "service.py").write_text("VALUE = 42\n")
        tf = repo / "tests" / "test_service.py"
        tf.parent.mkdir()
        tf.write_text("from app.service import VALUE\ndef test_value(): assert VALUE == 42\n")
        result = _import_check(repo, [tf])
        assert result.passed is True

    def test_missing_import_blocked(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        tf = repo / "test_bad.py"
        tf.write_text("from nonexistent_pkg_xyz import Foo\n")
        result = _import_check(repo, [tf])
        assert result.passed is False
        assert "ModuleNotFoundError" in result.error_summary or "ModuleNotFoundError" in result.stderr

    def test_name_error_blocked(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        tf = repo / "test_nameerr.py"
        # NameError at module level (not inside a function) is caught on import
        tf.write_text("x = UndefinedName123\n")
        result = _import_check(repo, [tf])
        assert result.passed is False

    def test_no_test_files_skips(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        provider = PythonProvider()
        result = provider.import_check(repo, [])
        assert result.passed is True
        assert result.skipped is True


# ---------------------------------------------------------------------------
# _find_test_files
# ---------------------------------------------------------------------------

class TestFindTestFiles:
    def test_finds_test_prefix(self, tmp_path: Path):
        repo = tmp_path / "proj"
        (repo / "tests").mkdir(parents=True)
        (repo / "tests" / "test_approval.py").write_text("")
        files = _find_test_files(repo, None)
        assert any(f.name == "test_approval.py" for f in files)

    def test_finds_suffix_test(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "approval_test.py").write_text("")
        files = _find_test_files(repo, None)
        assert any(f.name == "approval_test.py" for f in files)

    def test_excludes_non_test_files(self, tmp_path: Path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "approval.py").write_text("")
        files = _find_test_files(repo, None)
        assert not any(f.name == "approval.py" for f in files)


# ---------------------------------------------------------------------------
# get_test_gen_context: mock library detection
# ---------------------------------------------------------------------------

class TestGetTestGenContext:
    def test_no_pytest_mock_uses_unittest_mock(self, tmp_path: Path):
        repo = _make_py_project(tmp_path, with_pytest_mock=False)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert "unittest.mock" in ctx.mock_library
        assert "pytest-mock" not in ctx.mock_library

    def test_with_pytest_mock_detected(self, tmp_path: Path):
        repo = _make_py_project(tmp_path, with_pytest_mock=True)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert "pytest-mock" in ctx.mock_library

    def test_conventions_include_constructor_injection(self, tmp_path: Path):
        repo = _make_py_project(tmp_path)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert any("constructor injection" in c for c in ctx.conventions)

    def test_conventions_include_patch_rule(self, tmp_path: Path):
        repo = _make_py_project(tmp_path)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert any("patch" in c for c in ctx.conventions)

    def test_conventions_include_parametrize(self, tmp_path: Path):
        repo = _make_py_project(tmp_path)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert any("parametrize" in c for c in ctx.conventions)

    def test_example_test_loads_standard_pytest_mock_template(self, tmp_path: Path):
        repo = _make_py_project(tmp_path, with_pytest_mock=True)
        ctx = PythonProvider().get_test_gen_context(repo / "src" / "approval.py")
        assert "test_constructor_injection_boundary_value" in ctx.example_test
        assert "test_patch_imported_dependency" in ctx.example_test
        assert "test_pytest_mock_fixture" in ctx.example_test
        assert "@pytest.mark.parametrize" in ctx.example_test
