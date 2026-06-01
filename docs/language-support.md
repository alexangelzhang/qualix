# Language Support

Qualix separates requirement-level checks from language-specific code analysis. Q01, Q02, Q03, and Q04 are mostly language-independent. Q05b and Q06 care more about test frameworks, assertions, compilation, and coverage reports.

## Current Support

| Ecosystem | Current State | What Works Best Today |
| --- | --- | --- |
| Java | Strongest path | DDD-style services, JUnit tests, assertion-quality review, compile/test gates where project commands are available |
| TypeScript | Active provider support | Node services with Jest or Vitest, assertion scanning, coverage parsing, test skeleton/context support |
| Go | Basic provider support | `go.mod` detection, `go test` compile checks, `go vet`, `_test.go` discovery, basic weak-assertion scanning |
| Python | Basic provider support | `pyproject.toml`/pytest detection, `compileall`, optional `ruff`, `test_*.py` discovery, basic weak-assertion scanning |

## What “Support” Means

There are four levels of support:

| Level | Meaning |
| --- | --- |
| Profile | Baseline rules and risk vocabulary exist. Useful for Q01-Q04 and agent guidance. |
| Provider | Qualix can detect the language, test framework, assertions, and compile/lint behavior. |
| Code Intelligence | Qualix can read source symbols and parse diagnostics through an optional provider. |
| Turnkey Gate | Common project layouts work with little configuration. |

Java is closest to turnkey. TypeScript has real provider support but still needs more public examples. Go and Python now have lightweight providers, enough for detection and basic checks, but they should still be treated as early support until more real-world examples and benchmark rows exist.

## Code Intelligence

Qualix now has a small `CodeIntelligenceProvider` abstraction for source-level enrichment. It is separate from the language provider layer:

| Layer | Responsibility |
| --- | --- |
| `LanguageProvider` | Detect project language, test framework, compile/lint commands, test-file locations, and assertion patterns. |
| `CodeIntelligenceProvider` | Extract file-local symbols, parse diagnostics, and simple definition locations. |

The first implementation is `TreeSitterCodeIntelligenceProvider`. It supports Java, TypeScript, Go, and Python when the optional parser packages are installed:

```bash
python -m pip install -e '.[tree-sitter]'
```

Tree-sitter is intentionally treated as optional. If a grammar is missing, Qualix leaves code intelligence unavailable for that language and continues with the normal phase workflow. This keeps the first-run path short while still giving Q05a/Q06 a better view of source structure when the parsers are present.

Q05a now uses that source structure when `_q05_target_modules.json` lists changed files. If Tree-sitter is available, Qualix enriches the target-module file with `code_symbols` and warns when changed classes, functions, or methods are not mentioned by any EUT `when` field. That check is intentionally a warning: it catches likely blind spots without blocking projects that are still mapping code targets by hand.

This is not an LSP integration. It does not run a project-wide language server, resolve cross-file references, or depend on editor configuration. LSP can be added later for teams that need richer symbol graphs, but Tree-sitter is the lower-friction baseline for public users.

## Choosing A Profile

Use the closest profile rather than waiting for a perfect one:

```bash
qualix-run --profile java-ddd-tmf my-project init
qualix-run --profile typescript-service my-project init
qualix-run --profile go-service my-project init
qualix-run --profile python-service my-project init
```

For another unsupported language, start with Q01 and Q05a. Those phases can still produce useful requirement structure and test intent. Treat Q05b/Q06 as experimental unless you provide clear test commands and examples to the agent.

## Roadmap

The next language work should be practical rather than broad:

1. Add small TypeScript and Go demos parallel to the expense approval example.
2. Expand Go assertion parsing beyond the common `testing` and `testify` patterns.
3. Expand Python provider support for project layouts that keep tests outside the source tree.
4. Expand Q05a target-symbol checks from warnings into configurable gates once more public fixtures exist.
5. Publish language-specific benchmark rows instead of claiming blanket support.
