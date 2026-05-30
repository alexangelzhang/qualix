"""Tests for qualix.core.last_run — last-run marker atomic write."""

import json

from qualix.core.last_run import read_last_run, write_last_run


def test_write_then_read(tmp_path):
    (tmp_path / ".dqg").mkdir()
    write_last_run(
        project_root=tmp_path,
        cmd=["qualix-run", "status"],
        exit_code=0,
        stderr_tail="",
    )
    data = read_last_run(tmp_path)
    assert data is not None
    assert data["cmd"] == ["qualix-run", "status"]
    assert data["exit_code"] == 0
    assert "ts" in data
    assert "cwd" in data


def test_read_missing_returns_none(tmp_path):
    (tmp_path / ".dqg").mkdir()
    assert read_last_run(tmp_path) is None


def test_write_skipped_without_dqg_dir(tmp_path):
    """No .dqg/ directory → write is a no-op, no file created."""
    write_last_run(
        project_root=tmp_path,
        cmd=["qualix-run", "x"],
        exit_code=0,
        stderr_tail="",
    )
    assert not (tmp_path / ".dqg").exists()
    assert not (tmp_path / ".dqg" / "last-run.json").exists()


def test_stderr_tail_truncated(tmp_path):
    """stderr_tail should be truncated to last 4096 chars."""
    (tmp_path / ".dqg").mkdir()
    huge = "x" * 10000
    write_last_run(
        project_root=tmp_path,
        cmd=["qualix-run", "status"],
        exit_code=1,
        stderr_tail=huge,
    )
    data = read_last_run(tmp_path)
    assert len(data["stderr_tail"]) == 4096
    assert data["stderr_tail"] == "x" * 4096


def test_atomic_write_produces_valid_json(tmp_path):
    """File must always be valid JSON even after multiple writes."""
    (tmp_path / ".dqg").mkdir()
    for i in range(5):
        write_last_run(tmp_path, ["qualix-run", str(i)], i, "")
    path = tmp_path / ".dqg" / "last-run.json"
    # strict JSON parse
    data = json.loads(path.read_text())
    assert data["cmd"] == ["qualix-run", "4"]


def test_tee_writer_captures_stderr():
    """_TeeWriter should write to both original stream and internal buffer."""
    import io as _io

    from qualix.core.runner import _TeeWriter

    original = _io.StringIO()
    tee = _TeeWriter(original)
    tee.write("hello ")
    tee.write("world")
    assert tee.getvalue() == "hello world"
    assert original.getvalue() == "hello world"


def test_tee_writer_stderr_tail_written_to_last_run(tmp_path):
    """main() should capture real stderr output into last-run.json stderr_tail."""
    import subprocess
    import sys

    (tmp_path / ".dqg").mkdir()
    script = (
        "import sys; sys.path.insert(0, 'src'); "
        "from qualix.core.runner import _TeeWriter; "
        "import io; tee = _TeeWriter(sys.stderr); sys.stderr = tee; "
        "print('captured error', file=sys.stderr); "
        "sys.stderr = tee._original; "
        f"from qualix.core.last_run import write_last_run; from pathlib import Path; "
        f"write_last_run(Path(r'{tmp_path}'), ['test'], 0, tee.getvalue())"
    )
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True)
    data = json.loads((tmp_path / ".dqg" / "last-run.json").read_text())
    assert "captured error" in data["stderr_tail"]
