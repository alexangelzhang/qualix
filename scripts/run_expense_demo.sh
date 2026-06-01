#!/usr/bin/env bash
# run_expense_demo.sh — End-to-end Qualix demo using the expense-approval example.
#
# Usage:
#   ./scripts/run_expense_demo.sh              # show pre-computed results (no API key needed)
#   ./scripts/run_expense_demo.sh --live       # run Q01 + Q05a + Q06 with a real LLM
#
# The pre-computed path shows what Qualix would find on the expense-approval PRD
# without making any API calls. Use --live to run the actual pipeline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ID="expense-demo"
PRD_PATH="$REPO_ROOT/examples/expense-approval/prd.md"
EXPECTED_DIR="$REPO_ROOT/examples/expense-approval/expected"

# ── helpers ──────────────────────────────────────────────────────────────────

bar() { printf '\n%s\n' "$(printf '═%.0s' {1..60})"; }
hdr() { bar; printf '  %s\n' "$1"; bar; }

check_qualix() {
    if ! command -v qualix-run &>/dev/null; then
        echo "qualix-run not found. Install with: pip install qualix" >&2
        exit 1
    fi
}

# ── pre-computed path (no API key required) ───────────────────────────────────

show_precomputed() {
    hdr "Qualix Demo — Expense Approval  (pre-computed, no API key)"
    echo
    echo "PRD: $PRD_PATH"
    echo
    echo "The expense-approval PRD describes a simple approval workflow."
    echo "These are the findings Qualix produces when the full pipeline runs."
    echo

    printf '\n── Q01: Requirements Structuring ──────────────────────────\n\n'
    cat "$EXPECTED_DIR/q01-summary.md"

    printf '\n── Q05a: EUT Matrix Design ─────────────────────────────────\n\n'
    cat "$EXPECTED_DIR/q05a-eut-matrix.md"

    printf '\n── Q06: Coverage Audit ─────────────────────────────────────\n\n'
    cat "$EXPECTED_DIR/q06-audit.md"

    bar
    echo
    echo "The key finding: tests/test_expense_policy.py checks 120 USD and 600 USD."
    echo "Both branches pass. But 500 USD — the boundary — is never tested."
    echo "The implementation uses '> 500' instead of '>= 500': a silent logic error"
    echo "that line coverage cannot catch."
    echo
    echo "To run the live pipeline against your own PRD:"
    echo "  export ANTHROPIC_API_KEY=..."
    echo "  $0 --live"
    echo
    echo "To try on your own project:"
    echo "  qualix-run --profile python-service my-project init"
    echo "  qualix-run ingest /path/to/prd.md --project my-project"
    echo "  qualix-run my-project startup --json"
    bar
    echo
}

# ── live path (requires API key) ─────────────────────────────────────────────

run_live() {
    hdr "Qualix Demo — Expense Approval  (live run)"

    if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ -z "${OPENAI_API_KEY:-}" ]] && \
       [[ -z "${GEMINI_API_KEY:-}" ]] && [[ -z "${DASHSCOPE_API_KEY:-}" ]]; then
        echo "No model API key found. Set one of:" >&2
        echo "  ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, DASHSCOPE_API_KEY" >&2
        exit 1
    fi

    echo "Step 1/5: Initializing project..."
    qualix-run --profile python-service "$PROJECT_ID" init --json >/dev/null

    echo "Step 2/5: Ingesting PRD..."
    qualix-run ingest "$PRD_PATH" --project "$PROJECT_ID" --json >/dev/null

    echo "Step 3/5: Running Q01 (requirements structuring)..."
    qualix-run "$PROJECT_ID" execute Q01 --json
    qualix-run "$PROJECT_ID" finalize Q01 --json
    qualix-run "$PROJECT_ID" approve Q01 --json

    echo "Step 4/5: Running Q05a (EUT matrix design)..."
    qualix-run "$PROJECT_ID" execute Q05a \
        --code-repo "$REPO_ROOT/examples/expense-approval" --json
    qualix-run "$PROJECT_ID" finalize Q05a --json
    qualix-run "$PROJECT_ID" approve Q05a --json

    echo "Step 5/5: Running Q06 (coverage audit)..."
    qualix-run "$PROJECT_ID" execute Q06 \
        --code-repo "$REPO_ROOT/examples/expense-approval" --json
    qualix-run "$PROJECT_ID" finalize Q06 --json

    hdr "Results"
    echo
    REPORT_DIR="$(qualix-run "$PROJECT_ID" path output --json 2>/dev/null \
        | python3 -c 'import sys,json; print(json.load(sys.stdin).get("data",{}).get("output_dir",""))' \
        2>/dev/null || echo "")"
    if [[ -n "$REPORT_DIR" ]]; then
        echo "Reports written to: $REPORT_DIR"
        echo
        if [[ -f "$REPORT_DIR/Q06/phase_c_report.md" ]]; then
            cat "$REPORT_DIR/Q06/phase_c_report.md"
        fi
    fi
    echo
    echo "Run 'qualix-run $PROJECT_ID startup' to see the full phase status."
    bar
}

# ── main ─────────────────────────────────────────────────────────────────────

check_qualix

if [[ "${1:-}" == "--live" ]]; then
    run_live
else
    show_precomputed
fi
