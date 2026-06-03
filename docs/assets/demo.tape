Output demo.gif

Set FontSize 15
Set Width 1200
Set Height 520
Set Theme "Dracula"
Set Padding 28
Set TypingSpeed 50ms

# ── Scene 1: tests pass ───────────────────────────────────────────────────────

Type "# Two tests, branch coverage 100%. Both pass."
Enter
Sleep 0.8s

Type "python -m pytest examples/expense-approval/tests/ -v 2>/dev/null | tail -5"
Enter
Sleep 4s
Sleep 3s

# ── Scene 2: the bug in the code ─────────────────────────────────────────────

Type "# PRD says '>= 500'. The code says '> 500'. Exactly 500 USD misrouted."
Enter
Sleep 0.8s

Type "grep -n '> 500' examples/expense-approval/src/expense_policy.py"
Enter
Sleep 2s
Sleep 3s

# ── Scene 3: Qualix Q06 catches it ───────────────────────────────────────────

Type "# Qualix Q06 audit — finds it from the PRD, no API key needed:"
Enter
Sleep 0.8s

Type "cat examples/expense-approval/expected/q06-findings-short.txt"
Enter
Sleep 2.5s
Sleep 5s
