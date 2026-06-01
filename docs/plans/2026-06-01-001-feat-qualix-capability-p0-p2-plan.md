---
title: "feat: Qualix capability improvements P0–P2"
date: 2026-06-01
status: active
origin: docs/brainstorms/2026-06-01-qualix-capability-roadmap-requirements.md
sprint_map:
  sprint1: [U1, U2, U3, U4, U7]
  sprint2: [U5, U6]
  sprint3: [U8, U9, U10]
---

# feat: Qualix Capability Improvements P0–P2

## Summary

Five targeted improvements in three sprints. Sprint 1 fixes Q05b's near-zero first-pass success rate by injecting code skeletons before generation and feeding compile/runtime failures back into the fixer prompt, plus adding a Q01 ReAct loop. Sprint 2 extends the stable Q05b gate chain to TypeScript and Go. Sprint 3 replaces the in-process Judge simulation with subprocess-isolated JudgeRunner calls, achieving true context separation.

---

## Problem Frame

Q05b (unit test codegen) regularly fails to complete in ≤5 Ralph Loop iterations because:
1. The fixer prompt contains no negative examples of the hallucinated symbols that caused compile failure, so the same error recurs.
2. The fixer has no structured diagnosis of which Mock layer was wrong when `mvn test` fails after compile succeeds.

TS/Go projects cannot use Q05b at all — `test_execution_gate.py` has no `language_provider` path and hard-codes Java/JaCoCo.

Q01 processes complex PRDs (multi-state-machine, cross-document) in a single LLM call with no ability to chase references, query the repo, or ask the single most important clarifying question.

The Worker/Judge/Critique pipeline runs in a single Python process. Judge can observe Worker's reasoning traces, violating the independent-reviewer contract.

---

## Requirements

From origin doc:

- **P0-1**: Pre-codegen skeleton injection; post-compile error feedback to fixer; import whitelist gate
- **P0-2**: DDD+TMF layered Mock templates; runtime failure diagnosis feedback to fixer; static mock consistency check
- **P1-1**: TS and Go Q05b full chain (compile + run + coverage); Java path unchanged
- **P1-2**: Q01 Step 2.5 ReAct loop with hard 5-round exit; tool calls logged to `_reasoning_log.md`
- **P2**: Subprocess-isolated JudgeRunner calls; concurrent Judge dispatch; context leak verified by absence of `<thinking>` in `_judge_result.json`

Non-goals (from origin doc): Q03/Q04/Q07 skill changes, Python Q05b, JaCoCo coverage target increase, cross-machine distributed agents.

---

## Key Technical Decisions

**KTD-1: P0-1 skeleton injection at skill layer, not harness**
`extract_skeleton_for_files(file_paths) -> dict[str, SkeletonResult]` returns one `SkeletonResult` per file. The skill iterates the dict values, calls `.skeleton_text` on each, and concatenates into a fenced preamble block. `SkeletonResult.classes[*].methods[*].name` provides the authoritative method-name whitelist. Injecting at the skill prompt level (Step 2, per-EUT batch preamble) is less invasive than a harness-side preprocessing step. The skill already loads `_q05_target_modules.json`; the skeleton call is one additional read from the same file list.
*(see origin: docs/brainstorms/2026-06-01-qualix-capability-roadmap-requirements.md)*

**KTD-2: Compile error feedback via structured `ErrorFeedback` injected into handoff document**
The T14 schema-feedback pattern (handoff_builder.py injects `S-N. [schema] <error>` into fixer context) is the established precedent. Compile errors follow the same pattern: parse `javac`/`mvn test-compile` stderr for `error: cannot find symbol` lines, serialize as `C-N. [compile] <symbol> not found in <class> — known methods: [...]`, append to `_handoff_iter{N}.md` in a `## Compile Errors` block. The fixer prompt already reads the handoff document.

**KTD-3: Import whitelist gate uses `_q05_target_modules.json` as ground truth**
`_q05_target_modules.json` already maps EUT target classes to their source paths. The gate parses generated `@Test` files' import statements and checks each fully-qualified class against: (a) the known classes list from `_q05_target_modules.json`, (b) standard Java library prefixes (`java.`, `javax.`, `org.junit.`, `org.mockito.`). Anything outside these is flagged WARNING (not BLOCKED) to avoid false positives from project-internal utility classes. A second BLOCKED threshold fires only when >50% of EUT imports in a batch are unrecognized.

**KTD-4: P0-2 Mock templates are reference-only, not schema-enforced**
DDD+TMF layer detection (Domain/Application/Infrastructure) requires knowing the class package prefix, which varies per project. Encoding templates as `references/test-generation-rules.md` sections that the skill reads is sufficient; a new schema field for layer annotation would add schema complexity for marginal gain. The static mock consistency check can heuristically detect layer mismatch from class name patterns (`*Repository`, `*ServiceImpl`, `*Adapter`).

**KTD-5: test_execution_gate.py refactored around a language-dispatching entry point**
The current `check_q05_test_execution()` inlines Java-specific logic. Refactor to: detect language via `language_provider` (passed from `handlers_execute.py` shared context) → dispatch to `_run_java_gate()` (existing logic extracted), `_run_ts_gate()` (calls `TypeScriptProvider.run_tests()`), or `_run_go_gate()` (calls `GoProvider.compile_check()` then `go test -json`). JaCoCo coverage parsing stays Java-only; TS uses new `ts_coverage_parser.py` (lcov); Go uses `go test -cover` stdout parsing.

**KTD-6: Q01 ReAct loop is purely a skill-layer concern**
`Agent.run()` already supports tool-call loops (up to 10 rounds). The Q01 skill's `allowed-tools` already includes `Read`, `Grep`, and `AskUserQuestion`. Step 2.5 only needs to define the stopping rule (2 consecutive rounds with no new SE candidates found, or 5-round hard cap) and the evidence-logging convention (`_reasoning_log.md` `## ReAct Evidence` block). No harness changes required.

**KTD-7: P2 isolation via subprocess, not Agent re-dispatch**
`spawn_subagent()` is in-process (same Python heap). `Agent.run()` is not thread-safe for the same instance (lazy `_backend` init is lock-free). True isolation: each `_run_single_judge()` call in `judge_vote.py` is replaced with a subprocess that executes `python -m qualix.agents.judge_runner_subprocess` — a thin CLI wrapper around `JudgeRunner.run()`. The actual `JudgeRunner.run()` signature is `run(self, phase, report_path, output_dir, model, fallback=None, *, rubric='', ...)` — the subprocess wrapper serializes these fields to a temp JSON input file; the wrapper deserializes and calls with correct keyword args. The parent process `subprocess.run()`s it with `capture_output=True`. `JudgeResult` serialization uses an explicit `to_dict()` helper (not `dataclasses.asdict()`, which mishandles the `_schema_version` underscore field and nested dicts). Concurrent dispatch: `ThreadPoolExecutor` across subprocess calls (processes are independent, no shared state). The `None` return from `multi_judge_vote()` on HARD_BLOCK is preserved — the rationalization guard check remains in the parent process, unchanged.

---

## High-Level Technical Design

### P0-1/P0-2: Q05b Fixer Feedback Loop

```
Ralph Loop iteration N:
  ┌─────────────────────────────────────────────────────┐
  │ Step 2 (generate batch)                             │
  │   skeleton_preamble = extract_skeleton_for_files()  │
  │   prompt += "Available methods:\n" + skeleton_preamble │
  │   → write @Test methods                             │
  ├─────────────────────────────────────────────────────┤
  │ Step 3.0: import_whitelist_check() → WARNING/BLOCKED│
  │ Step 3.1: C9 check (EUT-xxx annotation present)     │
  │ Step 3.2: mvn test-compile                          │
  │   PASS → continue                                   │
  │   FAIL → parse "cannot find symbol" lines           │
  │        → append C-N errors to _handoff_iter{N}.md   │
  │        → loop back to Step 2 (fixer mode)           │
  │ Step 3.3: mock_consistency_check() → WARNING        │
  │ Step 3.4: mvn test                                  │
  │   FAIL → parse Surefire XML → extract @Test + cause │
  │        → append R-N errors to _handoff_iter{N}.md   │
  │        → loop back to Step 2 (fixer mode)           │
  └─────────────────────────────────────────────────────┘
```

### P1-1: test_execution_gate language dispatch

```
check_q05_test_execution(output_dir, project_id, language_provider)
  │
  ├─ language_provider is None or Java → _run_java_gate() [existing]
  ├─ language_provider.language_id == "typescript" → _run_ts_gate()
  │    TypeScriptProvider.run_tests() → parse JSON reporter
  │    ts_coverage_parser.parse_lcov()
  └─ language_provider.language_id == "go" → _run_go_gate()
       GoProvider.compile_check() [zero-test compile]
       subprocess: go test ./... -json -count=1
       go test -cover → parse coverage line
```

### P2: subprocess-isolated JudgeRunner

```
adaptive_loop._execute_iteration()
  │
  ├─ Worker Agent (unchanged — in-process, iterative fixer)
  │
  └─ multi_judge_vote() [modified]
       │
       ├─ ThreadPoolExecutor (N models, N subprocesses)
       │    subprocess: python -m qualix.agents.judge_runner_subprocess
       │                  --input /tmp/judge_input_{uuid}.json
       │                  --output /tmp/judge_output_{uuid}.json
       │    parent reads output JSON → VoteResult
       │
       └─ aggregate votes (unchanged consensus logic)

judge_runner_subprocess.py (new CLI wrapper):
  reads: {report_path, rubric, model, output_dir, project_id, phase_id}
  calls: JudgeRunner.run(...)
  writes: serialized JudgeResult JSON
  no inherited Python heap state
```

---

## Implementation Units

### U1. Skeleton injection and compile-error feedback (P0-1, skill layer)

**Goal**: Inject method-name ground truth before each @Test batch; feed `cannot find symbol` errors back into the fixer handoff document.

**Requirements**: P0-1 pre-codegen skeleton injection; P0-1 post-compile feedback

**Dependencies**: none

**Files**:
- `skills/unit-test-codegen/SKILL.md` — Step 2: add skeleton preamble block before each batch; Step 3.2: add compile-error parsing and handoff injection
- `references/test-generation-rules.md` — add "Skeleton contract" section: agent must only call methods listed in the skeleton preamble; if a required method is not in the skeleton, flag as OPEN and skip that EUT

**Approach**: In Step 2, the skill instructs the agent to first read `_q05_target_modules.json`, call `extract_skeleton_for_files(file_paths)` for the batch's target class source files, iterate the returned `dict[str, SkeletonResult]` values, concatenate each `.skeleton_text`, and prepend as a fenced block labeled `## Available Methods (do not invent others)`. In Step 3.2 compile failure handling, the skill instructs the agent to parse `mvn test-compile` stderr for lines matching `error: cannot find symbol`, extract symbol name and class context, and append a `## Compile Errors (fix in next iteration)` block to `_handoff_iter{N}.md` using the `C-N. [compile]` prefix convention (same as T14's `S-N. [schema]`).

**Patterns to follow**: `handoff_builder.py` schema error injection pattern (lines 52–58); `extract_skeleton_for_files()` in `context/analysis/code_skeleton.py`

**Test scenarios**:
- Skeleton preamble includes all public methods of the target class and no others
- When compile fails with `cannot find symbol: method buildXxxDto()`, the handoff document for the next iteration contains `C-1. [compile] buildXxxDto not found in XxxService — known methods: [createXxx, updateXxx]`
- When compile succeeds, no compile error block is appended to the handoff document
- A second fixer iteration does not repeat the same `cannot find symbol` error when the agent respects the skeleton constraint

**Verification**: Run Q05b on a test project; observe `mvn test-compile` succeeds on first or second iteration; handoff documents for failed iterations contain `C-N.` lines; same hallucination does not recur across iterations.

---

### U2. Import whitelist gate (P0-1, harness gate)

**Goal**: Catch phantom imports before compile by comparing generated imports against known class paths.

**Requirements**: P0-1 import whitelist validation

**Dependencies**: U1 (skill change lands first so gate has test data to validate against)

**Files**:
- `src/qualix/quality/checks/import_whitelist_check.py` — new module
- `src/qualix/quality/checks/finalize_checks.py` — register new check in Q05b gate chain
- `tests/test_import_whitelist_check.py` — new test file

**Approach**: Parse all `import` statements from generated `*Test.java` files in the code repo's test directory. Build a known-classes set from `_q05_target_modules.json` (all fully-qualified class names) plus standard prefix allowlist (`java.`, `javax.`, `org.junit.`, `org.mockito.`, `org.springframework.`, `com.fasterxml.`). For each import not in either set, emit a WARNING line. If >50% of non-standard imports in a batch are unrecognized, emit a BLOCKED line. Register in `finalize_checks.py` after `check_phase_b_compilation()`.

**Patterns to follow**: `q05_checks/_checks_eut_basic.py` check function signature and error prefix conventions; `_q05_target_modules.json` loading pattern from `_checks_coverage.py`

**Test scenarios**:
- Import of `java.util.List` → no warning (standard prefix)
- Import of `org.junit.jupiter.api.Test` → no warning (standard prefix)
- Import of a class that appears in `_q05_target_modules.json` → no warning
- Import of `com.example.NonExistentHelper` → WARNING line containing the class name
- Batch where 3 out of 4 non-standard imports are unrecognized → BLOCKED
- Batch where 1 out of 4 non-standard imports is unrecognized → WARNING only, not BLOCKED
- Empty test file → no warnings

**Verification**: `pytest tests/test_import_whitelist_check.py -q` passes; full test suite green.

---

### U3. DDD+TMF Mock templates and static mock consistency check (P0-2)

**Goal**: Give the agent a layer-specific Mock template to select from; statically detect when `@InjectMocks` class and `when()` mock targets belong to different DDD layers.

**Requirements**: P0-2 Mock template library; P0-2 mock consistency check

**Dependencies**: none (independent of U1/U2)

**Files**:
- `references/test-generation-rules.md` — add `## DDD+TMF Mock Templates` section with three subsections: Domain Service, Application Service, Infrastructure Adapter; each shows the `@ExtendWith` + `@InjectMocks` + `@Mock` setup block
- `src/qualix/quality/checks/mock_consistency_check.py` — new module
- `src/qualix/quality/checks/finalize_checks.py` — register after C9, before `mvn test`
- `tests/test_mock_consistency_check.py` — new test file

**Approach**: The templates section gives the agent a concrete `@ExtendWith(MockitoExtension.class)` block per layer. The static check (`mock_consistency_check.py`) parses the generated test files using regex (not tree-sitter, to keep the check fast and dependency-free). It finds the class annotated `@InjectMocks`, infers its layer from name suffix/package heuristic (`*Repository`/`*Mapper` → Infrastructure, `*Service`/`*Manager` → Application or Domain, `*DomainService` → Domain). It then checks that `@Mock`-annotated fields and `when(mockField.method())` call targets belong to the expected dependency layer(s) for that level. Mismatches produce WARNING lines with the specific field name and expected layer.

**Patterns to follow**: `q05_structure_checks.py` regex-based Java parsing patterns; check function signature and return type from `_checks_eut_basic.py`

**Test scenarios**:
- `@InjectMocks XxxDomainService` with `@Mock XxxRepository` → no warning (Domain Service may depend on Repository)
- `@InjectMocks XxxApplicationService` with `@Mock XxxRepository` directly (skipping domain layer) → WARNING naming the field and expected pattern
- `@InjectMocks XxxService` (inner class, not annotated correctly) → WARNING noting inner class incompatibility
- A test file with no `@InjectMocks` annotation → no warnings
- `verify(mockRepo, exactly(1))` on a mock that is a Domain-layer object when `@InjectMocks` is Application-layer → WARNING

**Verification**: `pytest tests/test_mock_consistency_check.py -q` passes; full test suite green.

---

### U4. Runtime failure diagnosis feedback (P0-2, skill layer)

**Goal**: Parse `mvn test` Surefire failures and inject structured per-`@Test` failure context into the fixer handoff document.

**Requirements**: P0-2 runtime failure diagnosis

**Dependencies**: U3 (Mock templates must exist before runtime feedback references them)

**Files**:
- `skills/unit-test-codegen/SKILL.md` — Step 3.4: add Surefire XML parsing and handoff injection
- `references/test-generation-rules.md` — add `## Runtime Failure Feedback Format` section documenting `R-N. [runtime]` prefix convention

**Approach**: When `mvn test` fails, the skill instructs the agent to read the Surefire XML reports from `target/surefire-reports/*.xml`. For each `<testcase>` element with a `<failure>` or `<error>` child, extract: test class name, test method name, failure message (first line only), and the stack frame pointing to the test file line. Format as `R-N. [runtime] {TestClass}#{method}: {failure_message} (line {L})`. Append as `## Runtime Failures (fix in next iteration)` block to `_handoff_iter{N}.md`. If a failure message contains `NullPointerException` on a mock field, cross-reference the Mock Templates section: "This is likely a layer mismatch — check DDD+TMF Mock Templates".

**Patterns to follow**: T14 schema error handoff pattern; `_handoff_iter{N}.md` structure from `handoff_builder.py`

**Test scenarios**:
- Surefire XML with one `<failure>` element → handoff contains one `R-1. [runtime]` line with correct class, method, and truncated failure message
- Surefire XML with NPE on mock field → handoff contains the NPE line plus the layer-mismatch hint
- `mvn test` succeeds → no runtime failure block appended
- Multiple failures across multiple test classes → each gets its own `R-N.` line, ordered by class then method name

**Verification**: Review generated handoff documents after a `mvn test` failure; fixer prompt contains actionable `R-N.` lines; `mvn test` first-pass success rate measurably improves on the expense-approval-demo project.

---

### U5. test_execution_gate language dispatch (P1-1)

**Goal**: Refactor `test_execution_gate.py` to dispatch to language-specific test runners via `language_provider`, while keeping the Java path byte-for-byte identical.

**Requirements**: P1-1 TS and Go Q05b gate

**Dependencies**: U1, U2, U3, U4 (Q05b must be stable on Java before adding new language paths)

**Files**:
- `src/qualix/quality/checks/test_execution_gate.py` — refactor: extract `_run_java_gate()`, add `_run_ts_gate()`, add `_run_go_gate()`, dispatch in `check_q05_test_execution()`
- `src/qualix/quality/checks/ts_coverage_parser.py` — new: parse lcov `coverage-summary.json` output
- `src/qualix/runtime/handlers/handlers_execute.py` — pass `language_provider` from shared context into `check_q05_test_execution()` call
- `tests/test_test_execution_gate_multilang.py` — new test file

**Approach**: `check_q05_test_execution()` gains a `language_provider` kwarg (default `None`, which preserves current Java behavior). Java path: extract current logic verbatim into `_run_java_gate()`. TS path (`_run_ts_gate()`): call `TypeScriptProvider.run_tests(repo_path, test_pattern="")`, parse the returned dict for `success`, `stdout` (JSON reporter output). Parse coverage from `coverage/coverage-summary.json` via `ts_coverage_parser.py`. Go path (`_run_go_gate()`): call `GoProvider.compile_check()` first (zero-test build); if passed, run `go test ./... -json -count=1 -timeout=300s` via subprocess, parse JSON output for `Action: "pass"/"fail"`, parse coverage from `go test -cover` stdout. Existing `check_q05b_coverage_increase()` stays Java-only (it reads JaCoCo XML); TS/Go coverage increase check is a follow-up.

**Patterns to follow**: `compile_check.py` language_provider dispatch pattern (lines 306–312); `GoProvider.compile_check()` in `languages/go/provider.py`; `TypeScriptProvider.run_tests()` in `languages/typescript/provider.py`

**Test scenarios**:
- `language_provider=None` → existing Java gate runs unchanged; all existing Q05b Java tests pass
- TS provider: `run_tests()` returns `{"success": True}` → gate returns empty list (no errors)
- TS provider: `run_tests()` returns `{"success": False, "stdout": "...FAIL..."}` → gate returns BLOCKED line with test output summary
- Go provider: `compile_check()` returns `CompileResult(passed=True)` and `go test` exits 0 → gate returns empty list
- Go provider: `compile_check()` returns `CompileResult(passed=False)` → gate returns BLOCKED compile error line
- Go provider: compile passes but `go test` exits non-zero → gate returns BLOCKED with failing test names extracted from JSON output

**Verification**: `pytest tests/test_test_execution_gate_multilang.py -q` passes; full suite green; smoke test with a synthetic TS project (package.json + jest) runs Q05b end-to-end.

---

### U6. Q05b skill multi-language templates (P1-1)

**Goal**: Add TypeScript and Go @Test generation templates to the skill so the agent produces idiomatic test code for each language.

**Requirements**: P1-1 skill multi-language template

**Dependencies**: U5 (gate must exist before skill templates are useful)

**Files**:
- `skills/unit-test-codegen/SKILL.md` — Step 2: add language detection block reading `_upstream_context.md` `language` field; add TS template (`describe/it/expect` + `jest.mock()` pattern); add Go template (`TestXxx(t *testing.T)` + `testify` mock pattern)
- `references/test-generation-rules.md` — add `## TypeScript Template Rules` and `## Go Template Rules` sections

**Approach**: At the top of Step 2, the skill instructs the agent to check `_upstream_context.md` for a `language:` field (or fall back to detecting `package.json` / `go.mod`). If `language: typescript`, use the Jest/Vitest template. If `language: go`, use the `testing` + `testify` template. If `language: java` or undetected, use the existing Java template. Each template includes the EUT traceability comment convention (`// EUT-xxx`) at the top of each test function — identical format across all three languages.

**Patterns to follow**: Existing Java template in `skills/unit-test-codegen/SKILL.md` Step 2; `references/test-generation-rules.md` existing Java rules structure

**Test scenarios** (for the skill document itself — verified by review, not automated test):
- TS template includes `describe` block, `it` or `test` function, `expect` assertion, `jest.mock()` for dependencies, and `// EUT-xxx` comment
- Go template includes `func TestXxx(t *testing.T)`, `testify/assert` assertion, `testify/mock` for mocked interfaces, and `// EUT-xxx` comment
- Both templates explicitly state the `// EUT-xxx` traceability comment is required (C9 gate depends on it)

**Verification**: Manual review of skill document; run Q05b against a synthetic TS or Go project and confirm generated test files match the template structure.

---

### U7. Q01 Step 2.5 ReAct loop (P1-2)

**Goal**: Insert a bounded tool-calling evidence-gathering phase between Q01 Step 2 (comprehension) and Step 3 (structuring) to improve SE completeness on complex multi-document PRDs.

**Requirements**: P1-2 Q01 ReAct loop with 5-round hard exit; tool calls logged to `_reasoning_log.md`

**Dependencies**: none (independent of all P0/P1-1 units)

**Files**:
- `skills/requirement-structuring/SKILL.md` — insert Step 2.5 between existing Step 2 and Step 3
- `references/react-tooling-guide.md` — new document defining ReAct loop rules, stopping conditions, evidence format
- `src/qualix/quality/checks/finalize_checks.py` — add optional bonus evidence check: if `_reasoning_log.md` contains a `## ReAct Evidence` block, `source_annotation` completeness score increases by 5% (soft bonus, not gate)

**Approach**: Step 2.5 runs after the agent has established initial business understanding. The agent is instructed to identify up to 3 "unresolved references" — cross-document links, incomplete state machine transitions, ambiguous exception paths. For each, it may use `Read` (to fetch a referenced document section), `Grep` (to search for a keyword across the evidence pack), or `AskUserQuestion` (for exactly one clarifying question per ReAct session, reserved for the highest-priority OPEN). After each tool call, the agent assesses whether it found at least one new SE candidate. If two consecutive rounds yield no new SE candidates, or if 5 rounds have elapsed, the loop exits. All tool call inputs and findings are appended to `_reasoning_log.md` under `## ReAct Evidence` (one entry per round: tool used, query, finding summary, new SE candidates if any).

**Patterns to follow**: Existing Step 2 → Step 3 handoff convention in `skills/requirement-structuring/SKILL.md`; `_reasoning_log.md` evidence format from finalize_checks source annotation checks; SE ID format rule from CLAUDE.md (`SE-001` not `SE-1`)

**Test scenarios** (verified by inspection against a test PRD run):
- Step 2.5 fires when the PRD references an external system spec ("see API contract doc")
- Step 2.5 exits after round 2 when rounds 1 and 2 both find no new SE candidates
- Step 2.5 exits after exactly round 5 regardless of findings
- `_reasoning_log.md` contains a `## ReAct Evidence` section with N entries matching the number of rounds executed
- A Q01 run on the expense-approval-demo PRD produces ≥1 additional SE compared to a run with Step 2.5 commented out (manual baseline comparison)

**Verification**: Run Q01 on `examples/expense-approval/prd.md` with and without Step 2.5; compare SE counts; confirm `_reasoning_log.md` ReAct Evidence section is present.

---

### U8. JudgeRunner subprocess wrapper (P2)

**Goal**: Create a thin CLI entry point that wraps `JudgeRunner.run()` so it can be called as an isolated subprocess with no inherited Python heap state.

**Requirements**: P2 subprocess-isolated Judge execution

**Dependencies**: U1–U7 all green (P2 is Sprint 3, starts only after Sprint 1+2 stable)

**Files**:
- `src/qualix/agents/judge_runner_subprocess.py` — new CLI module (`python -m qualix.agents.judge_runner_subprocess`)
- `tests/test_judge_runner_subprocess.py` — new test file

**Approach**: The module's `__main__` block accepts `--input <path>` and `--output <path>` CLI args. It reads a JSON file from `--input` containing `{phase, report_path, output_dir, model, rubric, fallback}`. It calls `JudgeRunner().run(phase, report_path, output_dir, model, fallback=fallback, rubric=rubric)` — note `JudgeRunner()` takes no constructor args; all context goes into `run()`. The result is serialized via an explicit `to_dict()` helper (not `dataclasses.asdict()`, which drops `_schema_version` and double-wraps nested dicts), written to `--output`. Exit code 0 on success, 1 on exception (exception message written to stderr). No global state is modified; no SQLite connections are opened in the parent process as a side effect.

**Patterns to follow**: `JudgeRunner.run()` interface in `src/qualix/quality/judge/judge_runner.py`; existing JSON serialization patterns using `save_json()`

**Test scenarios**:
- Valid input JSON → output JSON contains `verdict`, `score`, `issues` fields matching a `JudgeResult`
- `report_path` points to a nonexistent file → exit code 1, stderr contains error message
- Output JSON contains no `<thinking>` substring (context isolation assertion)
- Running two subprocess calls concurrently with different models → both complete successfully, no file collisions (temp file paths are UUID-suffixed)

**Verification**: `pytest tests/test_judge_runner_subprocess.py -q` passes; subprocess can be invoked via `python -m qualix.agents.judge_runner_subprocess --help` without error.

---

### U9. multi_judge_vote subprocess dispatch (P2)

**Goal**: Replace in-process `_run_single_judge()` with subprocess calls to `judge_runner_subprocess.py`, achieving true context isolation between Worker and Judge.

**Requirements**: P2 subprocess dispatch; concurrent Judge; context leak prevention

**Dependencies**: U8

**Files**:
- `src/qualix/quality/judge/judge_vote.py` — modify `_run_single_judge()`: replace `JudgeRunner(output_dir).run(...)` with subprocess call via `judge_runner_subprocess`
- `tests/test_multi_agent_isolation.py` — new test file verifying context isolation
- `tests/test_judge_vote.py` — update existing tests for the new dispatch path

**Approach**: `_run_single_judge()` writes a temp JSON input file to `output_dir/_internal/judge_input_{uuid}.json`, invokes `subprocess.run(["python", "-m", "qualix.agents.judge_runner_subprocess", "--input", ..., "--output", ...], timeout=120, capture_output=True)`, reads the output JSON, deserializes to `JudgeResult`, removes the temp files. The `ThreadPoolExecutor` in `multi_judge_vote()` already parallelizes calls; since each subprocess is independent, no additional locking is needed. Timeout: 120s per subprocess call (same as current `DEFAULT_TIMEOUT`). On timeout, raise `TimeoutError` (current behavior preserved).

**Patterns to follow**: Existing `ThreadPoolExecutor` pattern in `multi_judge_vote()` (lines 298–306 of `judge_vote.py`); use `tempfile.mkstemp()` or `uuid4()`-suffixed paths in `output_dir/_internal/` for temp input/output JSON files

**Test scenarios**:
- Worker produces a report with a long `<thinking>` block → `_judge_result.json` written by subprocess contains no `<thinking>` substring
- Two Judge models dispatched concurrently → both results arrive; `multi_judge_vote()` consensus is computed correctly
- One subprocess times out → `TimeoutError` is raised and propagated; other concurrent subprocess completes normally
- Subprocess exits with code 1 (exception) → `_run_single_judge()` raises a descriptive `RuntimeError`
- Full `adaptive_loop` integration: all existing `test_adaptive_schema_feedback_t14.py` tests pass unchanged

**Verification**: `pytest tests/test_multi_agent_isolation.py tests/test_judge_vote.py -q` passes; full test suite green; `_judge_result.json` from a real Q01 run contains no `<thinking>` content.

---

### U10. multi_agent.py upgrade and agent_orchestrator concurrent Critique (P2)

**Goal**: Upgrade `multi_agent.py` from prompt-generator to true dispatch coordinator; enable Critique to run immediately after Judge without waiting for a round-trip.

**Requirements**: P2 Critique concurrency; clean up Phase 1 scaffolding comment

**Dependencies**: U9

**Files**:
- `src/qualix/agents/multi_agent.py` — replace "Phase 1 implementation" comment with actual dispatch logic using `MultiAgentOrchestrator.run_phase()` coordinating Worker (via adaptive_loop) → Judge (via subprocess) → Critique (via subprocess, started after Judge completes)
- `src/qualix/agents/agent_orchestrator.py` — add `_run_critique_subprocess()` mirroring Judge subprocess dispatch; update `run_pipeline()` to start Critique immediately after Judge result is available
- `tests/test_multi_agent_orchestrator.py` — update/extend existing orchestrator tests

**Approach**: `run_pipeline()` in `agent_orchestrator.py` currently calls Worker → Judge → Critique in sequence within the same process. Refactor: Worker remains in-process (adaptive_loop manages fixer iterations). After Worker completes, Judge subprocess is dispatched (U9). After Judge result is written, Critique subprocess is dispatched concurrently (it only reads `phase_a_report.md` + `_judge_result.json`, so it can start as soon as Judge output file exists). `multi_agent.py` `run_phase()` now calls `agent_orchestrator.run_pipeline()` which orchestrates this sequence; the `PHASE_A_AGENTS` dataclass definitions remain as the source of truth for input/output file contracts.

**Patterns to follow**: `_run_judge_subprocess()` from U9; `PHASE_A_AGENTS` file contract definitions in `multi_agent.py`

**Test scenarios**:
- `run_phase("project", "Q01", {})` produces `_judge_result.json` and `_critique.json` in the phase output directory
- `_critique.json` does not contain content from Worker's reasoning trace (verified by checking for absence of Worker-only strings from a controlled test report)
- Critique start time (from file timestamp) is within 1s of Judge completion time (concurrency verification)
- `run_phase()` returns cleanly when Worker, Judge, and Critique all succeed
- If Judge subprocess fails, `run_phase()` raises an error before starting Critique

**Verification**: `pytest tests/test_multi_agent_orchestrator.py -q` passes; full test suite green; end-to-end Q01 run produces all three output files with no context leakage.

---

## Scope Boundaries

### Deferred to Follow-Up Work

- Q05b coverage increase check for TS/Go (currently Java/JaCoCo only; `check_q05b_coverage_increase()` is Java-specific)
- Python Q05b support (test generation paradigm differs significantly)
- Q03/Q04/Q07 skill changes
- P2 cross-machine distributed Agent dispatch
- JaCoCo coverage target increase beyond current 80%
- `spawn_subagent()` refactor (in-process, remains for non-isolation use cases)

### Outside Scope

- New Phase definitions
- Changes to Q05a EUT matrix design
- Frontend/dashboard changes
- CI/CD integration changes

---

## Risks and Dependencies

| Risk | Mitigation |
|------|-----------|
| Skeleton injection increases prompt length significantly for large classes | Cap skeleton to top 20 methods; if class has >20 methods, include only the EUT's `when` field method names |
| subprocess overhead makes concurrent Judge 2× slower than in-process | Measure baseline first; if subprocess latency > 200ms per judge, fall back to `Agent(new_instance).run()` per-call pattern |
| Go `go test -json` output format varies by Go version | Test against Go 1.20, 1.21, 1.22 output samples; parse defensively |
| Q01 ReAct loop queries the same document repeatedly (no loop progress) | The 2-consecutive-no-new-SE stopping rule prevents this; `_reasoning_log.md` entries make the agent's loop state visible |
| `mock_consistency_check.py` false positives on legitimate cross-layer dependencies | Gate is WARNING-only (not BLOCKED); false positive rate is acceptable if it surfaces real issues most of the time |

---

## Open Questions

- **OQ-1 (deferred)**: Should `import_whitelist_check.py` be promoted to BLOCKED at a lower threshold (e.g., any unrecognized import) for projects where `_q05_target_modules.json` is known to be complete? Leave configurable via a field in the project profile.
- **OQ-2 (deferred)**: Go coverage: should the gate require a minimum line coverage percentage (similar to Java's 80% JaCoCo gate) or just require `go test` to pass? Decide when P1-1 is tested against a real Go project.

---

## Test File Index

| Test file | Units covered |
|-----------|--------------|
| `tests/test_import_whitelist_check.py` | U2 |
| `tests/test_mock_consistency_check.py` | U3 |
| `tests/test_test_execution_gate_multilang.py` | U5 |
| `tests/test_judge_runner_subprocess.py` | U8 |
| `tests/test_multi_agent_isolation.py` | U9, U10 |
| `tests/test_judge_vote.py` | U9 (update) |
| `tests/test_multi_agent_orchestrator.py` | U10 (update) |

---

## Sources and Research

- `src/qualix/agents/adaptive_loop.py` — multi_judge_vote call site (line 721)
- `src/qualix/agents/handoff_builder.py` — T14 schema error injection pattern (lines 52–56, `S-N. [schema]` prefix convention)
- `src/qualix/context/analysis/code_skeleton.py` — SkeletonResult.classes[*].methods[*] interface
- `src/qualix/quality/checks/finalize_checks.py` — Q05b gate chain ordering
- `src/qualix/quality/checks/test_execution_gate.py` — full Java gate; identified language_provider gap
- `src/qualix/languages/typescript/provider.py` (436 lines) — run_tests() return contract
- `src/qualix/languages/go/provider.py` — compile_check() only; no run_tests()
- `src/qualix/quality/judge/judge_vote.py` — _run_single_judge() replacement point
- `docs/anti-hallucination-framework-evaluation.md` — claim/evidence/verifier/gate architecture direction
- `docs/brainstorms/2026-06-01-qualix-capability-roadmap-requirements.md` — origin requirements
