# Custom Profiles

A Qualix profile defines how the tool interacts with a specific language or technology stack. Profiles are used by Q05a, Q05b, Q06, and Q07 to find test files, run compilation checks, detect weak assertions, and apply language-specific rules.

## Profile Directory Layout

```
profiles/
└── my-profile/
    ├── profile.json      # Required — profile metadata and quality thresholds
    └── baseline.md       # Optional — language-specific rules for Q05a/Q06
```

## profile.json Fields

```json
{
  "profile_id": "my-profile",
  "version": "1.0.0",
  "name": "My Framework",
  "description": "Short description of what this profile targets.",
  "language": "java",
  "baseline_path": "profiles/my-profile/baseline.md",
  "risk_catalog_path": "references/risk-catalog-risks.md",
  "exception_catalog_path": "references/risk-catalog-exceptions.md",
  "quality_thresholds": {
    "line_coverage": 0.8,
    "branch_coverage": 0.8
  }
}
```

| Field | Required | Description |
| --- | --- | --- |
| `profile_id` | yes | Unique identifier, used in `qualix-run --profile <id>` |
| `version` | yes | Profile version string |
| `name` | yes | Human-readable display name |
| `description` | yes | One sentence describing the target stack |
| `language` | yes | Primary language: `java`, `typescript`, `go`, or `python` |
| `baseline_path` | no | Relative path to a language-specific rules file |
| `risk_catalog_path` | no | Overrides the default risk catalog for Q01–Q04 |
| `exception_catalog_path` | no | Overrides the default exception catalog for Q06 |
| `quality_thresholds` | no | Coverage gate thresholds (defaults to 0.8 if omitted) |

## baseline.md

The baseline file provides language-specific rules that agents load before running Q05a and Q06. It is not required — if absent, the agent uses general rules from the shared `references/` files.

A baseline is most useful when your stack has a specific architecture pattern (like DDD layering or a particular test framework) that affects which assertions are considered weak or strong.

See `profiles/java-ddd-tmf/baseline.md` as a reference. A baseline typically covers:

- Architecture layer responsibilities and what each layer should/should not do
- Framework-specific mock patterns (e.g., `@MockBean` vs `@InjectMocks`)
- Assertion idioms that are considered strong vs weak in your ecosystem
- Any naming conventions that affect how EUT targets are identified

## Selecting a Profile

```bash
qualix-run --profile my-profile my-project init
```

If you omit `--profile`, Qualix falls back to the closest built-in profile based on detected language.

## Built-in Profiles

| Profile ID | Language | Best for |
| --- | --- | --- |
| `java-ddd-tmf` | Java | DDD microservices with TMF orchestration |
| `typescript-service` | TypeScript | Node.js services with Jest or Vitest |
| `go-service` | Go | Standard library or testify-based Go services |
| `python-service` | Python | pytest-based Python packages and services |

## Creating a Profile Step by Step

1. Create the directory: `mkdir -p profiles/my-profile`

2. Write `profile.json` using the fields above. Start with an existing profile as a template.

3. Optionally write `baseline.md` with framework-specific rules. Keep it focused — a shorter baseline that is accurate is better than a long one that is aspirational.

4. Test it against a synthetic project:
   ```bash
   qualix-run --profile my-profile test-project init
   qualix-run ingest examples/expense-approval/prd.md --project test-project
   qualix-run test-project execute Q01 --json
   ```

5. If contributing back, add a benchmark case to `benchmarks/semantic-coverage/cases.md` that shows a finding your profile enables.

## Profile Validation

Run `qualix-run doctor` after creating a profile to check for structural issues. A malformed `profile.json` will be reported with the specific validation error.
