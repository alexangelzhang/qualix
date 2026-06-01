# Qualix 0.1 → 0.2 Migration Guide

Qualix 0.2 changed how the tool is distributed. In 0.1, Qualix was used by cloning the repository and running from inside it. In 0.2, Qualix is a standard pip package and your project files live separately from the tool source.

## What Changed

| 0.1 | 0.2 |
| --- | --- |
| `git clone` + run from repo root | `pip install qualix` |
| `skills/`, `references/`, `profiles/` in your cwd | Packaged inside the wheel |
| Output in `output/<pid>/` at repo root | Output in `.qualix/output/<pid>/` in your project |
| No separation between tool source and user config | `.qualix/` workspace separates user config from tool |

## Migration Steps

### 1. Install the new version

```bash
pip install --upgrade qualix
```

Or from the source repository for development:

```bash
git pull
python -m pip install -e '.[dev]'
```

### 2. Initialize your project workspace

In your project directory (not the Qualix repo):

```bash
cd /path/to/your-project
qualix-run --profile <your-profile> <project-id> init
```

This creates `.qualix/` in your project directory with:
- `output/<project-id>/` — phase outputs
- `settings.yaml` — profile and configuration

### 3. Move any custom configurations

| Was in (0.1) | Move to (0.2) |
| --- | --- |
| `profiles/your-profile/` inside Qualix repo | `.qualix/profiles/your-profile/` in your project |
| Modified skill fragments | `.qualix/skill-overrides/` in your project |
| `output/<pid>/` at Qualix repo root | `.qualix/output/<pid>/` in your project |

The `ResourceResolver` checks `.qualix/` first, then `~/.qualix/`, then the installed package. Drop your overrides in `.qualix/` and they take precedence automatically.

### 4. Update your CLAUDE.md (if using Claude Code)

`qualix-run <pid> init` appends a Qualix usage guardrail to your project's `CLAUDE.md` automatically. If you have an existing `CLAUDE.md`, check that the section was added correctly.

### 5. Verify

```bash
qualix-run <project-id> status --json
```

Expected: clean JSON output, no deprecation warnings.

## Common Issues

### Deprecation warning appears

The warning means the current working directory still has `src/qualix/` and `skills/` co-located (the old layout). Run `qualix-run <pid> init` from a directory outside the Qualix repo.

### Output files from 0.1

Old output in `output/<pid>/` at the Qualix repo root can be copied to `.qualix/output/<pid>/` in your project directory. Phase state is stored in `state.json` inside the project output directory.

### Multiple projects

After installing Qualix once, run `qualix-run --profile <profile> <pid> init` in each project directory. Each project gets its own `.qualix/output/`. Shared resources (skills, references, profiles) come from the installed package.

## Related

- [Custom profiles](custom-profile.md)
- [Model setup](model-setup.md)
- [Quick start](quickstart.md)
