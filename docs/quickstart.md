# 5-Minute Quick Start

This is the shortest path from a fresh clone to a working Qualix project.

## Prerequisites

- Python 3.11+
- git
- An AI coding agent such as Codex, Claude Code, Cursor, or Gemini CLI

## 1. Clone And Install

```bash
git clone https://github.com/alexangelzhang/qualix.git
cd qualix
./install.sh --dev
```

For a minimal editable install:

```bash
python -m pip install -e '.[dev]'
```

Optional Tree-sitter source parsing for Java, TypeScript, Go, and Python:

```bash
python -m pip install -e '.[tree-sitter]'
```

Optional Feishu/Lark ingestion support:

```bash
python -m pip install -e '.[feishu]'
```

Skip optional integrations for the first run. Local Markdown/text/html files are enough. For private enterprise documents, Qualix is moving toward a provider-based ingest layer so Q01 can consume URLs, browser-assisted exports, and local files through the same bundle format.

## 2. Initialize A Project

Run this inside the repository you want to analyze:

```bash
qualix-run my-first-project init --profile java-ddd-tmf
qualix-run my-first-project startup --json
```

The init command creates a local `.qualix/` workspace for project state and output files.

## 3. Start From An AI Agent

Inside Codex or another AI coding agent, invoke the Qualix starter:

```text
$qualix-starter
```

The agent should show the available phase menu and wait for your choice.

## 4. Run Q01 Manually

You can also run the first phase directly:

```bash
qualix-run my-first-project execute Q01 --json
qualix-run my-first-project finalize Q01 --json
qualix-run my-first-project approve Q01 --json
```

Q01 consumes an ingest bundle. For a local file:

```bash
qualix-run ingest docs/prd.md --project my-first-project
```

The same operation is available from Python when embedding Qualix:

```python
from pathlib import Path
from qualix.ingest import ingest_document

ingest_document("docs/prd.md", Path(".qualix/output/my-first-project/Q01/ingest"))
```

Feishu/Lark URLs are optional and require the `feishu` extra plus a valid Lark auth token configured through `QUALIX_LARK_USER_TOKEN` or `~/.qualix/auth/lark.ini`.

## Common Commands

| Command | Purpose |
| --- | --- |
| `qualix-run <project> init` | Initialize a project workspace |
| `qualix-run <project> startup --json` | Emit the project phase menu as JSON |
| `qualix-run <project> status --json` | Show phase status |
| `qualix-run <project> doctor` | Collect environment diagnostics |
| `qualix-run <project> execute Q01 --json` | Execute one phase |
| `qualix-run <project> finalize Q01 --json` | Run phase gates |
| `qualix-run <project> approve Q01 --json` | Approve a phase |
| `$qualix-starter` | AI-agent guided workflow |

## Next Steps

- Read the root [README](../README.md) for the phase model.
- Skim [Concepts](concepts.md) if Phase/Gate/Judge/EUT terms feel dense.
- Configure model providers with [Model Setup](model-setup.md).
- Check [Language Support](language-support.md) before assuming a language is turnkey.
- Understand the product boundary in [Comparison](comparison.md).
- Inspect [Benchmark](benchmark.md) for the current public semantic-coverage seed set.
- Read the fuller [expense approval demo](../examples/expense-approval/README.md) for a concrete semantic-coverage example.
- See [FAQ](faq.md) for common setup and workflow questions.
