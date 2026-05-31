# Model Setup

Qualix can run deterministic checks without an LLM, but the phase workflow is designed to be used with an AI coding agent and optional model-backed judge/critique steps.

For a first trial, keep the setup small:

1. Use a local Markdown PRD.
2. Set one model API key.
3. Skip Feishu/Lark, VLM, and DeepEval until you actually need them.

The expense approval demo works with local files only. No document-platform login is required.

## Environment Variables

Set the key for the provider you want to use. You only need one provider for a first local trial.

| Provider | Example Models | Environment Variable |
| --- | --- | --- |
| Anthropic | `claude-sonnet-*`, `claude-haiku-*` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-*`, `o*`, `codex-*` | `OPENAI_API_KEY` |
| Google Gemini | `gemini-*` | `GEMINI_API_KEY` |
| Qwen | `qwen-plus`, `qwen-max` | `DASHSCOPE_API_KEY` |
| Moonshot/Kimi | `kimi-*`, `moonshot-*` | `MOONSHOT_API_KEY` |

```bash
export ANTHROPIC_API_KEY="..."
# or
export OPENAI_API_KEY="..."
```

Do not commit API keys, `.env` files, shell history, diagnostic bundles, or phase outputs containing secrets.

## What To Install First

Use this for almost everyone starting out:

```bash
python -m pip install -e '.[dev]'
```

Then stop. The optional extras below are not part of the first-run path.

| Need | Install Later | Notes |
| --- | --- | --- |
| Local Markdown PRD | nothing else | Recommended first path |
| Feishu/Lark document URL | `python -m pip install -e '.[feishu]'` | Only for documents you are allowed to process |
| Image-heavy PRD | `python -m pip install -e '.[vlm]'` | Requires a vision model key |
| DeepEval calibration | `python -m pip install -e '.[deepeval]'` | Useful for experiments, not needed for the demo |

## Vision / Image Analysis

Image-heavy PRDs need a vision model provider. Install the optional VLM extra only when you need image parsing:

```bash
python -m pip install -e '.[vlm]'
```

Supported VLM environment variables include:

| Backend | Environment Variable |
| --- | --- |
| OpenAI vision-compatible API | `OPENAI_API_KEY` |
| Anthropic vision | `ANTHROPIC_API_KEY` |
| OpenRouter vision | `OPENROUTER_API_KEY` |
| DashScope/Qwen-VL | `DASHSCOPE_API_KEY` |

## Optional Feishu/Lark Ingestion

Local Markdown and text requirement files work without any document-platform integration. Feishu/Lark ingestion is optional:

```bash
python -m pip install -e '.[feishu]'
export QUALIX_LARK_USER_TOKEN=<your-user-access-token>
qualix-run auth status
```

Only run document ingestion for documents you are allowed to process. Public issues and pull requests must use sanitized examples.

## Recommended First Trial

1. Install Qualix in editable mode.
2. Set one model provider key.
3. Use `examples/expense-approval/prd.md` as a synthetic PRD.
4. Run Q01 first, then inspect the generated report and structured JSON.

```bash
qualix-run hello init --profile java-ddd-tmf
qualix-run hello startup --json
qualix-run hello execute Q01 --json
qualix-run hello finalize Q01 --json
qualix-run hello approve Q01 --json
```

If this is your first run, do not start with a private document URL. Start with the local demo file, make sure the phase lifecycle makes sense, then bring in your own project data.
