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

Optional Feishu/Lark ingestion support:

```bash
python -m pip install -e '.[feishu]'
uvx larkkit auth login
```

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

Q01 accepts a local PRD/requirements document. Feishu/Lark URLs are optional and require the `feishu` extra plus `larkkit` login.

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
- See [FAQ](faq.md) for common setup and workflow questions.
