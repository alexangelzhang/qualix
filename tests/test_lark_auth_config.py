import time

from qualix.commands.auth import run_auth_status
from qualix.feishu.auth_config import load_lark_auth_config
from qualix.feishu.client import _get_user_email, _get_user_token


def test_lark_auth_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("QUALIX_LARK_USER_TOKEN", "token-from-env")
    monkeypatch.setenv("QUALIX_LARK_USER_EMAIL", "dev@example.com")
    monkeypatch.setenv("QUALIX_LARK_TOKEN_EXPIRES_AT", "123")

    auth = load_lark_auth_config()

    assert auth.user_token == "token-from-env"
    assert auth.email == "dev@example.com"
    assert auth.token_expired_at == 123
    assert auth.source == "env:QUALIX_LARK_USER_TOKEN"
    assert _get_user_token() == "token-from-env"
    assert _get_user_email() == "dev@example.com"


def test_lark_auth_reads_qualix_config(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("QUALIX_LARK_USER_TOKEN", raising=False)
    auth_dir = tmp_path / ".qualix" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "lark.ini").write_text(
        "[lark]\nuser_token = token-from-file\nemail = file@example.com\ntoken_expired_at = 456\n",
        encoding="utf-8",
    )

    auth = load_lark_auth_config()

    assert auth.user_token == "token-from-file"
    assert auth.email == "file@example.com"
    assert auth.token_expired_at == 456
    assert auth.source.endswith(".qualix/auth/lark.ini")


def test_auth_status_reports_missing_config(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("QUALIX_LARK_USER_TOKEN", raising=False)

    assert run_auth_status() == 1
    output = capsys.readouterr().out
    assert "QUALIX_LARK_USER_TOKEN" in output
    assert ".qualix/auth/lark.ini" in output


def test_auth_status_accepts_valid_env_token(monkeypatch, capsys) -> None:
    monkeypatch.setenv("QUALIX_LARK_USER_TOKEN", "token-from-env")
    monkeypatch.setenv("QUALIX_LARK_TOKEN_EXPIRES_AT", str(int(time.time()) + 3600))

    assert run_auth_status() == 0
    output = capsys.readouterr().out
    assert "env:QUALIX_LARK_USER_TOKEN" in output
