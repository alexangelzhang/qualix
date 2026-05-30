import pytest

from qualix.core.settings import check_version_drift, load_settings


def test_load_settings_minimal(tmp_path):
    settings_file = tmp_path / ".qualix" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text('qualix_version: "0.2.0"\nprofile: java-ddd\ncode_repos:\n  - /path/to/repo1\n')
    s = load_settings(tmp_path)
    assert s.qualix_version == "0.2.0"
    assert s.profile == "java-ddd"
    assert s.code_repos == ["/path/to/repo1"]


def test_load_settings_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path)


def test_load_settings_empty_file_uses_defaults(tmp_path):
    """空 YAML 文件应当 fall back 到默认值，不抛异常."""
    settings_file = tmp_path / ".qualix" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text("")
    s = load_settings(tmp_path)
    assert s.qualix_version == ""
    assert s.profile == "java-ddd"
    assert s.code_repos == []


def test_version_drift_matching(tmp_path):
    settings_file = tmp_path / ".qualix" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text('qualix_version: "0.2.0"\nprofile: java-ddd\ncode_repos: []\n')
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift is None


def test_version_drift_mismatch(tmp_path):
    settings_file = tmp_path / ".qualix" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text('qualix_version: "0.1.9"\nprofile: java-ddd\ncode_repos: []\n')
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift == ("0.1.9", "0.2.0")


def test_version_drift_no_settings_returns_none(tmp_path):
    """没有 .qualix/settings.yaml 时不应报错，返回 None."""
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift is None


def test_version_drift_empty_pinned_version_returns_none(tmp_path):
    """pinned version 为空字符串时不触发漂移（比如手工写坏了）."""
    settings_file = tmp_path / ".qualix" / "settings.yaml"
    settings_file.parent.mkdir()
    settings_file.write_text('qualix_version: ""\nprofile: java-ddd\ncode_repos: []\n')
    drift = check_version_drift(tmp_path, installed_version="0.2.0")
    assert drift is None
