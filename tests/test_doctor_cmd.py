import json
import tarfile

import pytest

from qualix.commands.doctor import (
    build_bundle,
    check_version_consistency,
    redact_text,
)


@pytest.fixture
def project_with_state(tmp_path):
    (tmp_path / ".dqg").mkdir()
    (tmp_path / ".dqg" / "settings.yaml").write_text(
        'dqg_version: "0.2.0"\nprofile: java-ddd\ncode_repos:\n  - /abs/path\n'
    )
    (tmp_path / ".dqg" / "last-run.json").write_text(
        json.dumps(
            {
                "cmd": ["qualix-run", "status"],
                "exit_code": 1,
                "ts": "2026-05-11T14:00:00+0800",
                "cwd": str(tmp_path),
                "stderr_tail": "boom",
            }
        )
    )
    output = tmp_path / ".dqg" / "output" / "proj1"
    output.mkdir(parents=True)
    (output / "state.json").write_text("{}")
    phase_internal = output / "Q01" / "_internal"
    phase_internal.mkdir(parents=True)
    (phase_internal / "_reasoning_log.md").write_text("# log")
    return tmp_path


def test_build_bundle_contains_required_members(project_with_state, tmp_path):
    out = tmp_path / "bundle.tgz"
    build_bundle(
        project_root=project_with_state,
        output=out,
        redact=True,
        include_internal=True,
    )
    assert out.exists()
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert any(n.endswith("manifest.json") for n in names)
    assert any(n.endswith("env.txt") for n in names)
    assert any(n.endswith("settings.yaml") for n in names)
    assert any("recent-errors" in n for n in names)
    assert any("_reasoning_log.md" in n for n in names)


def test_build_bundle_respects_no_include_internal(project_with_state, tmp_path):
    out = tmp_path / "bundle-no-internal.tgz"
    build_bundle(
        project_root=project_with_state,
        output=out,
        redact=True,
        include_internal=False,
    )
    with tarfile.open(out) as tar:
        names = tar.getnames()
    assert not any("_internal/" in n for n in names)


def test_redact_username_in_paths():
    raw = "error at /Users/zhang3/code/app.py line 42"
    out = redact_text(raw)
    assert "/Users/zhang3" not in out
    assert "<user>" in out


def test_redact_linux_home_in_paths():
    raw = "/home/alice/projects/x.py"
    out = redact_text(raw)
    assert "/home/alice" not in out
    assert "<user>" in out


def test_redact_token_prefixes():
    for secret in ("sk-abc123xyz456", "claude-key-xxxxxx", "Bearer token-longlong"):
        assert "***" in redact_text(secret)


def test_version_consistency_mismatch_flag(project_with_state):
    (project_with_state / ".dqg" / "settings.yaml").write_text(
        'dqg_version: "0.0.1"\nprofile: java-ddd\ncode_repos: []\n'
    )
    result = check_version_consistency(
        project_root=project_with_state,
        global_version="0.2.0",
        installed_version="0.2.0",
    )
    assert result["mismatch"] is True
    assert result["settings"] == "0.0.1"


def test_version_consistency_all_match(project_with_state):
    (project_with_state / ".dqg" / "settings.yaml").write_text(
        'dqg_version: "0.2.0"\nprofile: java-ddd\ncode_repos: []\n'
    )
    result = check_version_consistency(
        project_root=project_with_state,
        global_version="0.2.0",
        installed_version="0.2.0",
    )
    assert result["mismatch"] is False


def test_version_consistency_no_settings(tmp_path):
    """When .dqg/settings.yaml is missing, settings is empty but not a mismatch if others agree."""
    result = check_version_consistency(
        project_root=tmp_path,
        global_version="0.2.0",
        installed_version="0.2.0",
    )
    assert result["settings"] == ""
    assert result["mismatch"] is False  # only {0.2.0} in the set


def test_run_doctor_ci_mode_outputs_json(project_with_state, tmp_path, monkeypatch):
    """In CI mode, run_doctor should print a JSON line to stdout and return 0."""
    import json as _json

    from qualix.commands.doctor import run_doctor

    monkeypatch.setenv("CI", "true")
    out_bundle = tmp_path / "bundle.tgz"
    captured = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: captured.append(a[0] if a else ""))

    rc = run_doctor(
        project_root=project_with_state,
        output=out_bundle,
        redact=True,
        include_internal=False,
        no_upload=False,  # CI mode should override this to True
        title=None,
    )
    assert rc == 0
    assert len(captured) == 1
    data = _json.loads(captured[0])
    assert "bundle" in data
    assert data["upload"] == "skipped_ci"
    assert "issues_url" in data


def test_run_doctor_ci_mode_not_triggered_without_env(project_with_state, tmp_path, monkeypatch, capsys):
    """Without CI env vars, run_doctor should print prose (not JSON) and respect no_upload."""
    from qualix.commands.doctor import run_doctor

    for v in ("CI", "GITLAB_CI", "GITHUB_ACTIONS", "JENKINS_URL", "BUILDKITE"):
        monkeypatch.delenv(v, raising=False)

    out_bundle = tmp_path / "bundle2.tgz"
    rc = run_doctor(
        project_root=project_with_state,
        output=out_bundle,
        redact=True,
        include_internal=False,
        no_upload=True,
        title=None,
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Bundle 已生成" in captured
    import json as _json

    try:
        _json.loads(captured.strip().splitlines()[0])
        raise AssertionError("should not be JSON in non-CI mode")
    except (_json.JSONDecodeError, IndexError):
        pass
