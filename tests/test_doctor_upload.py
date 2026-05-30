from unittest.mock import MagicMock, patch


def test_detect_glab_absent(monkeypatch):
    from dqg.commands.doctor import detect_glab

    monkeypatch.setenv("PATH", "/nonexistent")
    ok, reason = detect_glab()
    assert ok is False
    assert reason


def test_parse_issue_url():
    from dqg.commands.doctor import parse_issue_url_from_stdout

    out = "creating issue...\nhttps://github.com/your-org/rd-gate/-/issues/42\n"
    parsed = parse_issue_url_from_stdout(out)
    assert parsed == "https://github.com/your-org/rd-gate/-/issues/42"


def test_parse_issue_url_none():
    from dqg.commands.doctor import parse_issue_url_from_stdout

    assert parse_issue_url_from_stdout("no url here") is None


def test_resolve_issues_url_from_metadata():
    from dqg.commands.doctor import resolve_issues_url

    url = resolve_issues_url()
    # URL 来自 pyproject.toml 的 [project.urls].Issues
    assert "github.com" in url
    assert "dev-quality-gate" in url


def test_repo_path_from_url():
    from dqg.commands.doctor import _repo_path_from_url

    assert (
        _repo_path_from_url("https://github.com/your-org/rd-gate/-/issues")
        == "nr-car-service/dev-quality-gate"
    )
    assert (
        _repo_path_from_url("https://github.com/your-org/rd-gate/issues")
        == "nr-car-service/dev-quality-gate"
    )


@patch("dqg.commands.doctor.subprocess.run")
def test_upload_via_glab_success(mock_run, tmp_path):
    from dqg.commands.doctor import upload_via_glab

    bundle = tmp_path / "b.tgz"
    bundle.write_bytes(b"x")
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="created: https://github.com/your-org/rd-gate/-/issues/7\n",
        stderr="",
    )
    ok, url, err = upload_via_glab(
        title="t",
        description="d",
        bundle=bundle,
        repo_path="nr-car-service/dev-quality-gate",
        timeout=5,
    )
    assert ok
    assert url and "issues/7" in url
    assert err == ""


@patch("dqg.commands.doctor.subprocess.run")
def test_upload_via_glab_error(mock_run, tmp_path):
    from dqg.commands.doctor import upload_via_glab

    bundle = tmp_path / "b.tgz"
    bundle.write_bytes(b"x")
    # Both --file attempt and fallback fail
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="permission denied",
    )
    ok, url, err = upload_via_glab(
        title="t",
        description="d",
        bundle=bundle,
        repo_path="x/y",
        timeout=5,
    )
    assert ok is False
    assert "permission denied" in err


def test_run_doctor_no_upload(tmp_path, capsys):
    """--no-upload should generate bundle but not call glab."""
    from dqg.commands.doctor import run_doctor

    (tmp_path / ".dqg").mkdir()
    (tmp_path / ".dqg" / "settings.yaml").write_text('dqg_version: "0.2.0"\nprofile: java-ddd\ncode_repos: []\n')
    rc = run_doctor(
        project_root=tmp_path,
        output=None,
        redact=True,
        include_internal=True,
        no_upload=True,
        title=None,
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "Bundle" in captured.out or "bundle" in captured.out
    # Should mention issue URL for manual upload
    assert "github.com" in captured.out


def test_run_doctor_redact_false_with_upload_rejected(tmp_path, capsys):
    """--no-redact combined with upload (no --no-upload) must be rejected."""
    from dqg.commands.doctor import run_doctor

    (tmp_path / ".dqg").mkdir()
    rc = run_doctor(
        project_root=tmp_path,
        output=None,
        redact=False,
        include_internal=True,
        no_upload=False,
        title=None,
    )
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "redact" in combined.lower() or "脱敏" in combined
