# Qualix Phase Status — VS Code Extension (MVP)

A minimal VS Code sidebar that shows the status of Qualix phases (Q01–Q07) for projects in the current workspace, without leaving the editor for the terminal.

## What it does

- Activates only in workspaces that contain a `.qualix/` folder.
- Sidebar **Qualix → Phases**: one section per project under `.qualix/output/`, one row per phase, showing:
  - Phase ID (`Q01`–`Q07`)
  - Status icon: `✅ approved` / `⚠️ pending_review` / `❌ hard_blocked` / `— not_started`
  - For `Q06`: appends SE semantic coverage (e.g. `72% semantic`) when available
- Status bar: shows the first project's Q06 SE coverage (e.g. `Qualix: 72% SE`); click to reveal the sidebar.
- Three commands:
  - `Qualix: Refresh` — re-read state from disk (also bound to `F5` while the view is focused, and a refresh button on the view title).
  - `Qualix: Run Phase` — right-click a phase row, or pick from the command palette; runs `qualix-run <pid> execute <phase> --json` in an integrated terminal.
  - `Qualix: Open Dashboard` — runs `qualix dashboard start` in an integrated terminal.

## Installation

This MVP is plain JavaScript — there is no compile step.

```bash
# From the repo root, package and install:
cd vscode-extension
npx --yes @vscode/vsce package --no-dependencies
code --install-extension qualix-phases-0.1.0.vsix
```

Or, for local development, open the `vscode-extension/` folder in VS Code and press `F5` to launch an Extension Development Host.

## Data sources

The extension reads files directly; it does **not** import the `qualix` Python package.

| File | Use |
|---|---|
| `.qualix/output/<pid>/state.json` | Phase statuses (`phases.<phase_id>.status`) |
| `.qualix/output/<pid>/Q06/_gate_verdict.json` | Preferred source for `semantic_coverage.semantic_coverage_rate` |
| `.qualix/output/<pid>/Q06/_semantic_coverage_report.json` | Fallback source (top-level `semantic_coverage_rate`) |

If `state.json` is missing the project is shown with a `no state.json` hint and all phases default to `not_started`. If the workspace has no `.qualix/output/<pid>/` directories, the view shows `No Qualix projects found. Run: qualix-run <pid> init`.

## Auto-refresh

A file watcher on `.qualix/output/**/{state.json,_gate_verdict.json,_semantic_coverage_report.json}` triggers automatic refresh, so running `qualix-run` in a terminal updates the sidebar without manual reload.

## Limitations (MVP scope)

- Only the first workspace folder is inspected.
- Only `Q06` shows coverage; other quality metrics are not surfaced.
- No webview / detail panel — clicking a phase does not open Q06 verdict JSON. Use `Qualix: Run Phase` to drive execution from the terminal.
