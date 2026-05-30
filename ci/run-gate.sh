#!/usr/bin/env bash
# Qualix Quality Gate — 通用 shell 脚本
# 零外部依赖（除了 Python 和已安装的 qualix），适用于任何 CI 平台。
#
# 用法：
#   ./ci/run-gate.sh <project-id> <phase> [fail-on] [--pr-comment]
#
# 示例：
#   ./ci/run-gate.sh mrs Q06
#   ./ci/run-gate.sh mrs Q06 soft
#   ./ci/run-gate.sh mrs Q06 hard --pr-comment
#   QUALIX_ALL_PHASES=1 ./ci/run-gate.sh mrs
#
# 环境变量：
#   QUALIX_ALL_PHASES=1      检查所有 Phase
#   QUALIX_FAIL_ON           失败级别（hard/soft/any），默认 hard
#   QUALIX_OUTPUT_DIR        output 目录，默认 output

set -euo pipefail

PROJECT_ID="${1:-}"
PHASE="${2:-Q06}"
FAIL_ON="${3:-${QUALIX_FAIL_ON:-hard}}"
PR_COMMENT="${4:-}"

if [ -z "$PROJECT_ID" ]; then
  echo "用法: $0 <project-id> [phase] [fail-on] [--pr-comment]" >&2
  exit 2
fi

# 检查 qualix-run 是否可用
if ! command -v qualix-run &>/dev/null; then
  echo "ERROR: qualix-run 未找到，请先执行 pip install -e ." >&2
  exit 2
fi

# 构造参数
if [ "${QUALIX_ALL_PHASES:-0}" = "1" ]; then
  PHASE_FLAG="--all-phases"
else
  PHASE_FLAG="$PHASE"
fi

PR_FLAG=""
if [ "$PR_COMMENT" = "--pr-comment" ]; then
  PR_FLAG="--pr-comment"
fi

echo "==== Qualix Quality Gate ===="
echo "Project: $PROJECT_ID  Phase: ${QUALIX_ALL_PHASES:-0 == 1 and 'ALL' or $PHASE}  Fail-on: $FAIL_ON"
echo ""

# 运行 gate
qualix-run "$PROJECT_ID" ci-gate $PHASE_FLAG \
  --fail-on "$FAIL_ON" \
  $PR_FLAG
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
  echo "==== PASS ===="
else
  echo "==== FAIL (exit $EXIT_CODE) ===="
fi

exit $EXIT_CODE
