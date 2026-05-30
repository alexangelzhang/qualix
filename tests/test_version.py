import importlib.metadata
from pathlib import Path


def test_version_file_exists():
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    assert version_file.exists()
    content = version_file.read_text().strip()
    assert content  # 非空
    assert "\n" not in content  # 单行


def test_package_version_matches_file():
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    file_version = version_file.read_text().strip()
    pkg_version = importlib.metadata.version("qualix")
    assert pkg_version == file_version
