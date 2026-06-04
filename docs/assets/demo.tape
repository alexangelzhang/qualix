Output demo.gif

Set FontSize 15
Set Width 1200
Set Height 560
Set Theme "Dracula"
Set Padding 28
Set TypingSpeed 50ms

# ── Scene 1: the tests are green ──────────────────────────────────────────────

Type "# Two unit tests. Both pass. Coverage is green."
Enter
Sleep 0.8s

Type "cd examples/expense-approval && python -m pytest tests/ --cov=src -q"
Enter
Sleep 4s
Sleep 3s

# ── Scene 2: but the PRD rule and the code disagree ──────────────────────────

Type "# PRD says approval threshold is '>= 500'. The code says '> 500'."
Enter
Sleep 0.8s

Type "grep -n '> 500' src/expense_policy.py"
Enter
Sleep 2.5s
Sleep 2.5s

Type "# Exactly 500 USD silently routes to the wrong branch. No test catches it."
Enter
Sleep 2.5s

# ── Scene 3: Qualix Q06 sees what coverage cannot ────────────────────────────

Type "# Qualix audits the tests against the PRD — green coverage, zero proof:"
Enter
Sleep 0.8s

Type "cat expected/q06-findings-short.txt"
Enter
Sleep 3s
Sleep 5s
