# Show HN: Qualix — semantic coverage gates for AI-generated code

> Draft for HN / blog. Adapt tone and length as needed before posting.

---

**Show HN: Qualix — semantic coverage gates for AI-generated code**

AI coding agents write tests. The tests pass. Coverage is green. And then the bug ships.

Here is a concrete example. A PRD says:

> Requests at or above 500 USD require manager and finance approval.

A generated test suite might contain:

```python
def test_low_amount():
    # 120 USD → manager approval only
    assert classify(Decimal("120")) == "manager_only"

def test_high_amount():
    # 600 USD → finance required
    assert classify(Decimal("600")) == "finance_required"
```

Both tests pass. Branch coverage is green. The implementation, however, uses `> 500` instead of `>= 500`. The case of exactly 500 USD — which the PRD says requires finance approval — silently routes to the wrong path.

This is not a clever edge case. It is the boundary the PRD explicitly defined. A coverage tool reports it as fine.

---

**What Qualix does**

Qualix is a quality gate that starts from the requirement, not from the code.

Given the PRD, it extracts semantic expectations (SEs) — the business behaviors that tests should prove:

- SE-003: a request at exactly 500 USD requires manager AND finance approval

It then audits the test suite against those expectations. If no test exercises `amount == 500`, SE-003 is flagged as `PARTIAL` or `MISSING`, regardless of what line coverage says.

The full pipeline:

```
Q01  Structure the PRD into traceable REQ/BR/SE items
Q05a Design test targets from those semantics (EUT matrix)
Q05b Generate test code (optional, needs compile gate)
Q06  Audit the test suite against the original SE items
Q07  Structured code review tied back to requirement IDs
```

It works with your existing test runner. It does not replace pytest, JUnit, or Jest. It sits above them and answers a different question: did the tests prove the requirement, or just execute the code?

---

**Why now**

AI coding agents have made it cheap to generate code and tests. That changes the bottleneck. The bottleneck is no longer "can we write this?" but "does this actually do what the product asked for?"

Line coverage was designed for the world where tests were hand-written. In that world, a developer who wrote the test usually understood the requirement. The test was evidence of understanding.

AI-generated tests are evidence of execution. The model generates what it can infer from the code. If the code has a logic error at the boundary, the generated test will probably pass — because the test is generated from the same (wrong) implementation.

Qualix is an attempt to inject the requirement back into the loop, at a point where it can still catch the gap before the code ships.

---

**Current state**

- Apache 2.0, public alpha (0.2.0a1 on PyPI)
- Java has the deepest path; TypeScript, Go, Python supported at basic level
- GitHub Actions composite action for CI gate integration
- Real-world results: in three production Java services, Q06 found 18 EUT targets with assertion gaps that line coverage did not flag (16 partial, 2 missing)

```bash
pip install qualix
./scripts/run_expense_demo.sh   # no API key needed, shows pre-computed findings
```

---

**What I am looking for**

Feedback on:

- Does the semantic coverage framing make sense? Is there a clearer way to explain the gap between line coverage and business-rule verification?
- Java is the strongest path today. What language / framework would make this immediately useful for your team?
- The current workflow requires an AI coding agent (Claude Code, Codex, Gemini CLI). Is the friction too high for evaluation?

The GitHub repo is at: https://github.com/alexangelzhang/qualix

---

*Notes for posting:*
- *HN title: keep under 80 chars. Options: "Qualix: semantic coverage gates for AI-generated code" or "Show HN: When AI writes tests but misses the 500 USD boundary"*
- *For blog: expand the "why now" section, add the real-world numbers table from docs/real-world-results.md*
- *For Twitter/X thread: use the 500 USD example as the hook tweet, then reply-chain with the 3-point explanation*
