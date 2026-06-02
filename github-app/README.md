# Qualix GitHub App

A lightweight FastAPI webhook handler that turns Qualix's locally produced
quality-gate verdict into an automatic Pull Request comment.

> Zero LLM calls. The App only reads the verdict file (`output/<pid>/Q06/_gate_verdict.json`)
> that you have already committed to the repository (or that your CI pipeline
> generates and pushes before the App fires).

## How it works

```
PR opened/updated  ──►  GitHub  ──►  webhook  ──►  Railway service
                                                       │
                                                       ▼
                                          download .qualix/settings.yaml
                                          download output/<pid>/Q06/_gate_verdict.json
                                                       │
                                                       ▼
                                          render Markdown via
                                          qualix.commands.ci._render_pr_comment
                                                       │
                                                       ▼
                                          POST/PATCH PR comment (idempotent)
```

The handler:

1. Verifies the `X-Hub-Signature-256` header against a shared webhook secret.
2. Filters to `pull_request` events with action `opened`, `synchronize`, or `reopened`.
3. Exchanges an App JWT for an installation access token.
4. Reads `.qualix/settings.yaml` (top-level `project_id` or nested `qualix.project_id`)
   from the PR head commit; falls back to the repo name.
5. Reads `output/<project_id>/Q06/_gate_verdict.json` (and `_semantic_coverage_report.json`
   if present) at the PR head commit via the GitHub Contents API.
6. Renders the Markdown via the same `_render_pr_comment` function the local CLI uses.
7. Creates the comment, or updates the previous Qualix comment if one already exists
   on the PR (matched by the `## Qualix Quality Gate` header line).

If no verdict file exists at the PR head, the App returns `status: skipped` and
posts nothing.

---

## 1. Create the GitHub App

1. Open https://github.com/settings/apps and click **New GitHub App**.
2. **App name**: pick something unique, e.g. `qualix-<yourname>`.
3. **Homepage URL**: any URL you control (e.g. your Qualix README on GitHub).
4. **Webhook URL**: leave as a placeholder for now (e.g. `https://example.com/webhook`).
   You will replace this with the Railway domain in step 4.
5. **Webhook secret**: generate a strong random value and save it. You will set
   it as `GITHUB_WEBHOOK_SECRET` later.
6. **Repository permissions** (request only what is needed):
   - **Contents**: Read-only (to fetch the verdict file)
   - **Pull requests**: Read & write (to post the comment)
   - **Metadata**: Read-only (mandatory)
7. **Subscribe to events**: check **Pull request** only.
8. **Where can this GitHub App be installed?**: Any account (or only your account
   if private).
9. After creation, scroll to **Private keys** and click **Generate a private key**.
   A `.pem` file downloads. Keep it safe — you will paste its contents into the
   `GITHUB_APP_PRIVATE_KEY` env var.
10. Note the numeric **App ID** at the top of the settings page.

## 2. Deploy to Railway

The simplest path is to deploy this directory directly:

```bash
# from the qualix repo root
cd github-app
railway init             # create a new Railway project (or use the dashboard)
railway up               # uploads source and triggers a Nixpacks build
```

Alternatively, in the Railway dashboard: **New Project → Deploy from GitHub repo**,
pick your fork of `qualix`, and set the **Root Directory** to `github-app/`.

The included `railway.toml` declares:

- Builder: Nixpacks (auto-detects Python via `requirements.txt`)
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Healthcheck: `GET /healthz`

## 3. Set environment variables on Railway

In the service's **Variables** tab, add:

| Variable | Value |
|----------|-------|
| `GITHUB_WEBHOOK_SECRET` | the secret you generated in step 1.5 |
| `GITHUB_APP_ID` | the numeric App ID from step 1.10 |
| `GITHUB_APP_PRIVATE_KEY` | the full contents of the `.pem` file (Railway accepts either real newlines or `\n` escapes) |

After saving, Railway redeploys automatically. Confirm `GET /healthz` returns
`{"status":"ok","config":{"webhook_secret":true,"app_id":true,"private_key":true}}`.

## 4. Point the GitHub App at Railway

1. Copy the public Railway domain for this service, e.g. `https://qualix-app.up.railway.app`.
2. Back in the App settings, set **Webhook URL** to `https://<your-domain>/webhook`.
3. Save. GitHub sends a `ping` event; you can verify delivery under
   **Advanced → Recent Deliveries**.

## 5. Install the App on your repositories

1. From the App settings page, click **Install App**.
2. Pick the account or organisation, choose **Only select repositories**, and
   pick the repos where you want Qualix verdict comments.
3. Confirm.

## 6. Make sure verdicts exist on the PR head

Because the App reads files from the PR head commit, the verdict must be
present there. Two common patterns:

- **Commit verdicts directly** (simplest): run `qualix-run <pid> finalize Q06`
  locally and commit `output/<pid>/Q06/_gate_verdict.json` along with your
  changes.
- **Generate in CI and push**: have your CI pipeline run `finalize` and either
  commit the verdict back to the PR branch or push it to a separate branch your
  workflow merges. (See `action.yml` at the repo root for the GitHub Action.)

The App also looks for `output/<pid>/Q06/_semantic_coverage_report.json` and
includes coverage comparison in the comment if present.

### Resolving `<project_id>`

The App resolves the project id in this order:

1. `project_id` at the top level of `.qualix/settings.yaml` on the PR head commit.
2. `qualix.project_id` nested inside `.qualix/settings.yaml`.
3. The repository name (`<owner>/<repo>` → `<repo>`).

---

## Local development

```bash
cd github-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# qualix is published on PyPI; if you want to run against the local checkout:
pip install -e ..

export GITHUB_WEBHOOK_SECRET=test-secret
export GITHUB_APP_ID=000000
export GITHUB_APP_PRIVATE_KEY="$(cat /path/to/private-key.pem)"

uvicorn app:app --port 8080 --reload
```

### Smoke test the signature path

The signature check fails closed when the secret is unset. With the secret
configured, an unsigned request should be rejected with `401`:

```bash
curl -i -X POST http://localhost:8080/webhook \
  -H 'X-GitHub-Event: pull_request' \
  -H 'Content-Type: application/json' \
  -d '{"action":"opened"}'
# expect: HTTP/1.1 401 Unauthorized
```

To craft a valid signature for a JSON file `event.json`:

```bash
SIG=sha256=$(python3 -c 'import os,sys,hmac,hashlib;\
print(hmac.new(os.environ["GITHUB_WEBHOOK_SECRET"].encode(),\
sys.stdin.buffer.read(), hashlib.sha256).hexdigest())' < event.json)

curl -i -X POST http://localhost:8080/webhook \
  -H 'X-GitHub-Event: pull_request' \
  -H "X-Hub-Signature-256: $SIG" \
  -H 'Content-Type: application/json' \
  --data-binary @event.json
```

Without valid `installation.id` and a real installation token the call will
ultimately fail at the GitHub API step, but you can confirm signature
verification, header routing, and JSON parsing this way.

## Troubleshooting

- **`503 webhook secret not configured`** — set `GITHUB_WEBHOOK_SECRET` and redeploy.
- **`401 invalid signature`** — the secret on Railway and on the GitHub App must match exactly.
- **`502 github auth failed`** — verify `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY`. The PEM
  must be the *full* contents of the `.pem` file, including the `BEGIN`/`END` lines.
- **No comment appears, response is `{"status":"skipped","reason":"no_verdict_at_head"}`** —
  the verdict file is not on the PR head commit. Commit it or have CI push it.
- **Comment posted to wrong path** — the App resolved a different `project_id` than you
  expected. Confirm `.qualix/settings.yaml` is committed on the PR head and contains
  `project_id: <your-pid>`.

## Security notes

- The webhook secret is the only authenticator for incoming requests; treat it
  like a password.
- The installation token is short-lived (~1h) and scoped to repos that have the
  App installed, with the permissions configured in step 1.6.
- This service never reads request bodies before signature verification
  succeeds — bodies are read once, verified, then parsed.
