# Model Setup

Qualix can run deterministic checks without an LLM, but the phase workflow is designed to be used with an AI coding agent and optional model-backed judge/critique steps.

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

## Vision / Image Analysis

Image-heavy PRDs need a vision model provider. Install the optional VLM extra when you need image parsing:

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
uvx larkkit auth login
uvx larkkit auth status
```

Only run document ingestion for documents you are allowed to process. Public issues and pull requests must use sanitized examples.

## Recommended First Trial

1. Install Qualix in editable mode.
2. Set one model provider key.
3. Use `examples/hello-prd.md` as a synthetic PRD.
4. Run Q01 first, then inspect the generated report and structured JSON.

```bash
qualix-run hello init --profile java-ddd-tmf
qualix-run hello startup --json
qualix-run hello execute Q01 --json
qualix-run hello finalize Q01 --json
qualix-run hello approve Q01 --json
```

