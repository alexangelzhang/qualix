Output demo.gif

Set FontSize 15
Set Width 1000
Set Height 550
Set Theme "Dracula"
Set Padding 24
Set TypingSpeed 50ms

# 1. version
Type "qualix version"
Enter
Sleep 1s

# 2. init
Type "qualix-run --profile python-service expense-demo init"
Enter
Sleep 2s

# 3. ingest
Type "qualix-run ingest examples/expense-approval/prd.md --project expense-demo"
Enter
Sleep 2.5s

# 4. Q01 expected output
Type "cat examples/expense-approval/expected/q01-summary.md"
Enter
Sleep 3.5s

# 5. Q06 audit
Type "cat examples/expense-approval/expected/q06-audit.md"
Enter
Sleep 4s

Sleep 1.5s
