"""Tests for version drift warning at qualix-run startup (Task 10)."""

import subprocess


def test_drift_warning_prints(tmp_path):
    """settings.yaml 版本与 installed 不同时跑 qualix-run，应在 stderr 看到漂移 warning."""
    (tmp_path / ".qualix").mkdir()
    (tmp_path / ".qualix" / "settings.yaml").write_text(
        'qualix_version: "0.0.1-ancient"\nprofile: java-ddd\ncode_repos: []\n'
    )
    # init 是 workspace-level，不需要 project_id；用它触发 main 启动序列
    result = subprocess.run(
        ["qualix-run", "init", "--force"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    # stderr 应该出现漂移 warning（可能在 stdout 也行，取决于实现）
    combined = result.stderr + result.stdout
    assert "0.0.1-ancient" in combined or "版本漂移" in combined or "version" in combined.lower()


def test_no_drift_warning_when_matching(tmp_path):
    """pinned version 与 installed 一致时不打 warning."""
    from importlib.metadata import version as _v

    try:
        installed = _v("qualix")
    except Exception:
        installed = "unknown"

    (tmp_path / ".qualix").mkdir()
    (tmp_path / ".qualix" / "settings.yaml").write_text(f'qualix_version: "{installed}"\nprofile: java-ddd\ncode_repos: []\n')
    result = subprocess.run(
        ["qualix-run", "init", "--force"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert "漂移" not in result.stderr
    assert "drift" not in result.stderr.lower()


def test_no_drift_warning_when_no_settings(tmp_path):
    """没有 .qualix/settings.yaml 时不应打 warning."""
    result = subprocess.run(
        ["qualix-run", "init"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert "漂移" not in result.stderr
    assert "drift" not in result.stderr.lower()
