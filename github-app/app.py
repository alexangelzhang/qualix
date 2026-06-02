"""Qualix GitHub App webhook handler.

Listens for ``pull_request`` events, fetches the verdict file
(``output/<project_id>/Q06/_gate_verdict.json``) from the PR head commit via
the GitHub Contents API, renders a Markdown summary using
``qualix.commands.ci._render_pr_comment``, and posts it as a PR comment.

The handler performs **zero** LLM calls. The verdict file must already exist
in the repository (committed locally or pushed by CI before this runs).

Required environment variables:

* ``GITHUB_WEBHOOK_SECRET`` — shared secret configured on the GitHub App
* ``GITHUB_APP_ID`` — numeric GitHub App ID
* ``GITHUB_APP_PRIVATE_KEY`` — PEM-encoded RSA private key (literal newlines
  or ``\\n`` escapes are both accepted)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

import jwt
import requests
import yaml
from fastapi import FastAPI, Header, HTTPException, Request

# qualix is installed via requirements.txt; import the rendering helper.
from qualix.commands.ci import _render_pr_comment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("qualix.github_app")

app = FastAPI(title="Qualix GitHub App", version="0.1.0")

GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY", "")
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID", "")

GITHUB_API = "https://api.github.com"
USER_AGENT = "qualix-github-app/0.1"
HTTP_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(payload: bytes, sig_header: str) -> bool:
    """Verify the ``X-Hub-Signature-256`` header against the shared secret.

    Returns ``True`` only when the HMAC matches. Constant-time comparison is
    used to avoid timing attacks.
    """
    if not GITHUB_WEBHOOK_SECRET or not sig_header:
        return False
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header)


# ---------------------------------------------------------------------------
# GitHub App authentication (JWT -> installation access token)
# ---------------------------------------------------------------------------

def _normalize_private_key(raw: str) -> str:
    """Accept PEM keys that come from env vars with escaped newlines."""
    if "\\n" in raw and "\n" not in raw:
        return raw.replace("\\n", "\n")
    return raw


def _build_app_jwt() -> str:
    if not GITHUB_APP_ID or not GITHUB_APP_PRIVATE_KEY:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY must be set")
    now = int(time.time())
    payload = {
        "iat": now - 60,         # tolerate small clock skew
        "exp": now + 9 * 60,     # GitHub max is 10 minutes
        "iss": GITHUB_APP_ID,
    }
    return jwt.encode(payload, _normalize_private_key(GITHUB_APP_PRIVATE_KEY), algorithm="RS256")


def get_installation_token(installation_id: int) -> str:
    """Exchange an App JWT for an installation access token."""
    jwt_token = _build_app_jwt()
    resp = requests.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"installation token exchange failed: {resp.status_code} {resp.text[:200]}"
        )
    data = resp.json()
    token = data.get("token")
    if not token:
        raise RuntimeError(f"installation token response missing 'token': {data}")
    return token


# ---------------------------------------------------------------------------
# Verdict lookup and rendering
# ---------------------------------------------------------------------------

def _gh_get_contents(repo: str, path: str, ref: str, token: str) -> Optional[dict[str, Any]]:
    """GET /repos/{repo}/contents/{path}?ref={ref}, return JSON or None on 404."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{path}"
    resp = requests.get(
        url,
        params={"ref": ref},
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {path}@{ref} failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


def _decode_content(payload: dict[str, Any]) -> bytes:
    """Decode the base64 ``content`` field of a Contents API response."""
    encoding = payload.get("encoding", "base64")
    if encoding != "base64":
        raise RuntimeError(f"unexpected content encoding: {encoding}")
    return base64.b64decode(payload.get("content", ""))


def _resolve_project_id(repo: str, sha: str, token: str) -> str:
    """Return ``project_id`` from ``.qualix/settings.yaml`` or the repo name.

    The repository may store the project id under either top-level
    ``project_id:`` or nested ``qualix.project_id``. Both are accepted.
    """
    fallback = repo.split("/", 1)[-1]
    try:
        item = _gh_get_contents(repo, ".qualix/settings.yaml", sha, token)
    except Exception as exc:  # pragma: no cover - network errors logged only
        log.warning("read settings.yaml failed (%s); fallback to repo name", exc)
        return fallback
    if item is None:
        return fallback
    try:
        text = _decode_content(item).decode("utf-8")
        settings = yaml.safe_load(text) or {}
    except Exception as exc:
        log.warning("parse settings.yaml failed (%s); fallback to repo name", exc)
        return fallback
    pid = settings.get("project_id")
    if not pid and isinstance(settings.get("qualix"), dict):
        pid = settings["qualix"].get("project_id")
    return pid or fallback


def build_pr_comment(repo: str, sha: str, token: str) -> Optional[str]:
    """Read ``output/<pid>/Q06/_gate_verdict.json`` at ``sha`` and render Markdown.

    Returns ``None`` when the verdict file does not exist for this commit; the
    caller should silently skip commenting in that case (the user has not yet
    committed any verdict).
    """
    project_id = _resolve_project_id(repo, sha, token)
    log.info("resolved project_id=%s for repo=%s sha=%s", project_id, repo, sha[:8])

    verdict_path = f"output/{project_id}/Q06/_gate_verdict.json"
    item = _gh_get_contents(repo, verdict_path, sha, token)
    if item is None:
        log.info("no verdict at %s @ %s; skipping comment", verdict_path, sha[:8])
        return None

    try:
        verdict = json.loads(_decode_content(item).decode("utf-8"))
    except Exception as exc:
        log.error("decode verdict failed: %s", exc)
        return None

    # Optional: pull semantic coverage report alongside the verdict.
    sem_cov: Optional[dict[str, Any]] = None
    sem_path = f"output/{project_id}/Q06/_semantic_coverage_report.json"
    sem_item = _gh_get_contents(repo, sem_path, sha, token)
    if sem_item is not None:
        try:
            sem_cov = json.loads(_decode_content(sem_item).decode("utf-8"))
        except Exception as exc:
            log.warning("decode semantic coverage failed (%s); ignoring", exc)

    return _render_pr_comment({"Q06": verdict}, sem_cov)


# ---------------------------------------------------------------------------
# Comment posting (with idempotency: update existing Qualix comment if any)
# ---------------------------------------------------------------------------

_QUALIX_COMMENT_MARKER = "## Qualix Quality Gate"


def _find_existing_qualix_comment(repo: str, pr_number: int, token: str) -> Optional[int]:
    """Return the id of an existing Qualix comment authored by this app, if any."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=HTTP_TIMEOUT)
    if resp.status_code >= 400:
        log.warning("list comments failed: %s %s", resp.status_code, resp.text[:200])
        return None
    for c in resp.json():
        body = c.get("body") or ""
        if body.startswith(_QUALIX_COMMENT_MARKER):
            return c.get("id")
    return None


def post_pr_comment(repo: str, pr_number: int, body: str, token: str) -> None:
    """Create or update the Qualix verdict comment on the PR."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    existing_id = _find_existing_qualix_comment(repo, pr_number, token)
    if existing_id is not None:
        url = f"{GITHUB_API}/repos/{repo}/issues/comments/{existing_id}"
        resp = requests.patch(url, headers=headers, json={"body": body}, timeout=HTTP_TIMEOUT)
    else:
        url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
        resp = requests.post(url, headers=headers, json={"body": body}, timeout=HTTP_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"comment write failed: {resp.status_code} {resp.text[:200]}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Liveness probe used by Railway / uptime monitors."""
    return {
        "status": "ok",
        "config": {
            "webhook_secret": bool(GITHUB_WEBHOOK_SECRET),
            "app_id": bool(GITHUB_APP_ID),
            "private_key": bool(GITHUB_APP_PRIVATE_KEY),
        },
    }


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
) -> dict[str, Any]:
    body = await request.body()

    # Always verify in production. If the secret is unset, fail closed: refuse
    # to process anything rather than silently accepting unsigned requests.
    if not GITHUB_WEBHOOK_SECRET:
        log.error("GITHUB_WEBHOOK_SECRET is not configured; refusing request")
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    if not verify_signature(body, x_hub_signature_256 or ""):
        raise HTTPException(status_code=401, detail="invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    try:
        repo_full_name = payload["repository"]["full_name"]
        pr_number = int(payload["number"])
        head_sha = payload["pull_request"]["head"]["sha"]
        installation_id = int(payload["installation"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"missing webhook field: {exc}")

    log.info(
        "pull_request %s repo=%s pr=%s sha=%s install=%s",
        action, repo_full_name, pr_number, head_sha[:8], installation_id,
    )

    try:
        token = get_installation_token(installation_id)
    except Exception as exc:
        log.exception("installation token failed")
        raise HTTPException(status_code=502, detail=f"github auth failed: {exc}")

    try:
        comment = build_pr_comment(repo_full_name, head_sha, token)
    except Exception as exc:
        log.exception("build comment failed")
        raise HTTPException(status_code=502, detail=f"build comment failed: {exc}")

    if comment is None:
        return {"status": "skipped", "reason": "no_verdict_at_head"}

    try:
        post_pr_comment(repo_full_name, pr_number, comment, token)
    except Exception as exc:
        log.exception("post comment failed")
        raise HTTPException(status_code=502, detail=f"post comment failed: {exc}")

    return {"status": "ok", "pr": pr_number, "sha": head_sha}
