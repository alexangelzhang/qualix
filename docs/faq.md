# FAQ

## Setup

### `qualix-run` is not found

Install the package in editable mode:

```bash
python -m pip install -e /path/to/qualix
```

Or run from a cloned repository:

```bash
cd /path/to/qualix
./install.sh --dev
```

### Which optional dependencies do I need?

For a first run, none. Use a local Markdown PRD and install the development extra only:

```bash
python -m pip install -e '.[dev]'
```

Optional extras are available for integrations:

```bash
python -m pip install -e '.[feishu]'   # Feishu/Lark ingestion through larkkit
python -m pip install -e '.[vlm]'      # VLM image analysis providers
python -m pip install -e '.[deepeval]' # DeepEval calibration support
```

### Feishu/Lark login fails

Feishu/Lark support is optional. If you need it, install and authenticate `larkkit`:

```bash
python -m pip install larkkit
uvx larkkit auth login
uvx larkkit auth status
```

Local Markdown or text requirement files do not need this setup.

### Do I need to understand every phase first?

No. Start with Q01. It structures a requirement document into traceable items. Then read the output before running downstream phases.

For the short glossary, see [Concepts](concepts.md).

## Project Workflow

### Where do I start?

```bash
qualix-run my-project init --profile java-ddd-tmf
qualix-run my-project startup --json
```

Then invoke `$qualix-starter` in your AI coding agent.

### Why is a phase locked?

The upstream dependency has not been approved yet. The main flow is:

```text
Q01 -> Q02 -> Q03 -> Q04 -> Q07
Q01 -> Q05a -> Q05b -> Q06
```

Complete the nearest incomplete upstream phase first.

### Can I rerun a completed phase?

Yes. Re-execute the phase, then run finalize and approve again:

```bash
qualix-run <project_id> execute <phase_id> --json
qualix-run <project_id> finalize <phase_id> --json
qualix-run <project_id> approve <phase_id> --json
```

### Finalize says `_reasoning_log.md` is missing

Every phase must produce a reasoning log. Ask the agent to create `_reasoning_log.md` for the phase output directory, then run finalize again.

### The generated artifact is wrong

Give specific feedback. For example:

```text
BR-003 is missing the "review status" and "review time" fields. Add them and rerun the self-check.
```

Avoid vague prompts like "regenerate it"; they usually lose useful context.

## Version And Updates

### How do I check the version?

```bash
qualix-run <project_id> version
```

### How do I update?

For a cloned repository:

```bash
git pull --rebase
python -m pip install -e '.[dev]'
```

Then run:

```bash
qualix-run <project_id> doctor
```

## Concepts

### How is Qualix different from a coding agent workflow tool?

Qualix focuses on quality gates: requirement traceability, design coverage, test intent, assertion quality, and evidence-backed review. It can complement coding workflow tools by auditing what they produce.

### Does Qualix support Python, TypeScript, Go, and Java?

Not equally yet. Java is the strongest path. TypeScript, Go, and Python have built-in providers for detection and basic quality gates, but Go and Python are still early compared with Java. See [Language Support](language-support.md) for the honest breakdown.

### Is there a benchmark?

There is a small public seed set under [benchmarks/semantic-coverage](../benchmarks/semantic-coverage/README.md). It is not a leaderboard yet; it is a set of readable cases that show where line coverage can miss requirement semantics.
