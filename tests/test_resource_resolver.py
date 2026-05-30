from __future__ import annotations

import pytest

from qualix.core.resource_resolver import ResourceResolver


@pytest.fixture
def tmp_project(tmp_path):
    """模拟项目目录 + .qualix/"""
    project = tmp_path / "my-project"
    project.mkdir()
    (project / ".qualix" / "skill-overrides").mkdir(parents=True)
    (project / ".qualix" / "skill-overrides" / "Q01.md").write_text("override")
    return project


@pytest.fixture
def tmp_global(tmp_path):
    """模拟 ~/.qualix/"""
    global_qualix = tmp_path / "home" / ".qualix"
    (global_qualix / "skills" / "Q01").mkdir(parents=True)
    (global_qualix / "skills" / "Q01" / "SKILL.md").write_text("global skill")
    (global_qualix / "references").mkdir(parents=True)
    (global_qualix / "references" / "data.md").write_text("ref data")
    (global_qualix / "profiles" / "java-ddd").mkdir(parents=True)
    (global_qualix / "profiles" / "java-ddd" / "profile.json").write_text("{}")
    (global_qualix / "regression").mkdir(parents=True)
    return global_qualix


def test_resolve_project_override(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("skill-overrides", "Q01.md")
    assert result == tmp_project / ".qualix" / "skill-overrides" / "Q01.md"


def test_resolve_global_fallback(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("skills", "Q01/SKILL.md")
    assert result == tmp_global / "skills" / "Q01" / "SKILL.md"


def test_resolve_not_found_raises(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    with pytest.raises(FileNotFoundError):
        resolver.resolve("skills", "NONEXISTENT/SKILL.md")


def test_resolve_profiles(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    result = resolver.resolve("profiles", "java-ddd/profile.json")
    assert result == tmp_global / "profiles" / "java-ddd" / "profile.json"


def test_list_category(tmp_project, tmp_global):
    resolver = ResourceResolver(
        project_root=tmp_project,
        global_root=tmp_global,
    )
    items = resolver.list_category("profiles")
    assert items == [tmp_global / "profiles" / "java-ddd"]


def test_resolve_dir_project_override(tmp_project, tmp_global):
    # project .qualix/profiles/ wins over global
    (tmp_project / ".qualix" / "profiles").mkdir()
    resolver = ResourceResolver(project_root=tmp_project, global_root=tmp_global)
    result = resolver.resolve_dir("profiles")
    assert result == tmp_project / ".qualix" / "profiles"


def test_list_category_project_overrides_global(tmp_project, tmp_global):
    # same name in both layers — project wins
    (tmp_project / ".qualix" / "profiles" / "java-ddd").mkdir(parents=True)
    (tmp_project / ".qualix" / "profiles" / "java-ddd" / "profile.json").write_text("{}")
    resolver = ResourceResolver(project_root=tmp_project, global_root=tmp_global)
    items = resolver.list_category("profiles")
    # java-ddd entry should point to project-level, not global
    assert len(items) == 1
    assert items[0] == tmp_project / ".qualix" / "profiles" / "java-ddd"


def test_resolve_rejects_path_traversal(tmp_project, tmp_global):
    resolver = ResourceResolver(project_root=tmp_project, global_root=tmp_global)
    with pytest.raises(ValueError):
        resolver.resolve("../etc", "passwd")
    with pytest.raises(ValueError):
        resolver.resolve("skills", "../../../etc/passwd")


def test_layer4_fallback_when_nothing_else_matches(tmp_path, capsys):
    """When .qualix/, ~/.qualix/, importlib.resources all miss, fall back to Qualix repo root."""
    ResourceResolver._LAYER4_WARNED.clear()
    empty_project = tmp_path / "empty"
    empty_project.mkdir()
    empty_global = tmp_path / "empty-home" / ".qualix"
    resolver = ResourceResolver(project_root=empty_project, global_root=empty_global)
    # Real category that exists in Qualix repo
    result = resolver.resolve_dir("profiles")
    # Must resolve — exact path will depend on test location, just assert it exists and is a dir
    assert result.is_dir()
    captured = capsys.readouterr()
    assert "Layer-4" in captured.err or "layer-4" in captured.err.lower() or "layer4" in captured.err.lower()


def test_layer4_warning_only_once_per_category(tmp_path, capsys):
    # Reset the warned set to isolate this test
    ResourceResolver._LAYER4_WARNED.clear()
    empty_project = tmp_path / "empty2"
    empty_project.mkdir()
    empty_global = tmp_path / "empty-home2" / ".qualix"
    resolver = ResourceResolver(project_root=empty_project, global_root=empty_global)
    resolver.resolve_dir("profiles")
    resolver.resolve_dir("profiles")
    captured = capsys.readouterr()
    # Warning should appear exactly once
    assert captured.err.lower().count("layer-4") == 1


def test_legacy_cwd_layout_warns(tmp_path, capsys):
    """cwd 同时有 src/qualix/ 和 skills/ 时打印 deprecation warning."""
    legacy = tmp_path / "legacy"
    (legacy / "src" / "qualix").mkdir(parents=True)
    (legacy / "skills").mkdir()

    resolver = ResourceResolver(
        project_root=legacy,
        global_root=tmp_path / "empty-global",
    )
    resolver.check_legacy_layout()

    captured = capsys.readouterr()
    # 打印走 stderr
    assert "deprecat" in captured.err.lower()


def test_non_legacy_layout_no_warn(tmp_path, capsys):
    """正常用户项目不触发 warning."""
    project = tmp_path / "user-project"
    project.mkdir()
    resolver = ResourceResolver(
        project_root=project,
        global_root=tmp_path / "empty-global",
    )
    resolver.check_legacy_layout()
    captured = capsys.readouterr()
    assert "deprecat" not in captured.err.lower()
