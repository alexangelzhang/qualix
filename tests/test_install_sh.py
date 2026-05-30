from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "install.sh"


def test_install_sh_exists_and_executable():
    assert INSTALL_SH.exists()
    assert os.access(INSTALL_SH, os.X_OK)


def test_install_sh_dry_run(tmp_path):
    """dry-run 只打印计划，不实际落盘."""
    output_root = tmp_path / "fake-home" / ".dqg"
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--dry-run",
            "--skip-pip",
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "安装计划" in result.stdout
    assert "DQG version" in result.stdout
    assert not output_root.exists(), "dry-run 不应该创建目录"


def test_install_sh_real_copy(tmp_path):
    """--skip-pip 模式下只拷资源，验证拷贝完整."""
    output_root = tmp_path / "fake-home" / ".dqg"
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--skip-pip",
            "--output-root",
            str(output_root),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    for name in ("skills", "references", "profiles", "regression"):
        assert (output_root / name).is_dir(), f"{name} 未拷贝"
    assert (output_root / "VERSION").is_file()
    assert (output_root / "VERSION").read_text().strip() == (REPO_ROOT / "VERSION").read_text().strip()


def test_install_sh_missing_source_root_fails(tmp_path):
    """source-root 缺资源目录必须报错退出."""
    fake_source = tmp_path / "not-a-qualix-repo"
    fake_source.mkdir()
    result = subprocess.run(
        [
            str(INSTALL_SH),
            "--dry-run",
            "--skip-pip",
            "--source-root",
            str(fake_source),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "缺少必要目录" in result.stderr or "缺少必要目录" in result.stdout
