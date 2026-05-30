#!/bin/bash
# Post-edit guard: run pytest when critical Qualix source files are modified
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('file_path', ''))
except:
    print('')
" 2>/dev/null)

# Only trigger on src/qualix/ Python files
echo "$FILE_PATH" | grep -q "src/qualix/.*\.py$" || exit 0

cd /Users/zhangyiqian/Dev/qualix
pytest tests/ -q --tb=short -x 2>&1 | tail -20
