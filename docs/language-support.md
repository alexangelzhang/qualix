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

There are three levels of support:

| Level | Meaning |
| --- | --- |
| Profile | Baseline rules and risk vocabulary exist. Useful for Q01-Q04 and agent guidance. |
| Provider | Qualix can detect the language, test framework, assertions, and compile/lint behavior. |
| Turnkey Gate | Common project layouts work with little configuration. |

Java is closest to turnkey. TypeScript has real provider support but still needs more public examples. Go and Python now have lightweight providers, enough for detection and basic checks, but they should still be treated as early support until more real-world examples and benchmark rows exist.

## Choosing A Profile

Use the closest profile rather than waiting for a perfect one:

```bash
qualix-run my-project init --profile java-ddd-tmf
qualix-run my-project init --profile typescript-service
qualix-run my-project init --profile go-service
qualix-run my-project init --profile python-service
```

For another unsupported language, start with Q01 and Q05a. Those phases can still produce useful requirement structure and test intent. Treat Q05b/Q06 as experimental unless you provide clear test commands and examples to the agent.

## Roadmap

The next language work should be practical rather than broad:

1. Add small TypeScript and Go demos parallel to the expense approval example.
2. Expand Go assertion parsing beyond the common `testing` and `testify` patterns.
3. Expand Python provider support for project layouts that keep tests outside the source tree.
4. Publish language-specific benchmark rows instead of claiming blanket support.
