#!/bin/bash
# Qualix Headless Pipeline Runner
# 每个 Phase 独立执行，支持断点续跑、并行调度、失败重试
#
# 用法:
#   ./scripts/run_pipeline.sh <project_id> [--parallel] [--max-retry 2]
#
# 特性:
#   - 每个 Phase 是独立的 claude 调用，quota 耗尽不影响其他 Phase
#   - 自动检测已完成的 Phase，从断点继续
#   - 支持 A.5 + A.6 + B 并行执行
#   - 失败自动重试（默认 2 次）
#   - 执行日志写入 output/<project>/pipeline.log

set -euo pipefail

PROJECT_ID="${1:?用法: $0 <project_id> [--parallel] [--max-retry N]}"
PARALLEL=false
MAX_RETRY=2
BASE_DIR="."

shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --parallel) PARALLEL=true; shift ;;
        --max-retry) MAX_RETRY="$2"; shift 2 ;;
        --base-dir) BASE_DIR="$2"; shift 2 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

Qualix="python -m qualix.runner ${PROJECT_ID} --base-dir ${BASE_DIR}"
LOG_DIR="output/${PROJECT_ID}"
LOG_FILE="${LOG_DIR}/pipeline.log"
mkdir -p "${LOG_DIR}"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" | tee -a "${LOG_FILE}"
}

# 检查 Phase 状态
phase_status() {
    local phase="$1"
    ${Qualix} status 2>/dev/null | grep -oP "Phase ${phase}.*?status: \K\w+" || echo "not_started"
}

# 执行单个 Phase（headless）
run_phase() {
    local phase="$1"
    local status
    status=$(phase_status "$phase")

    if [[ "$status" == "approved" || "$status" == "skipped" ]]; then
        log "Phase ${phase}: 已完成 (${status})，跳过"
        return 0
    fi

    local attempt=0
    while [[ $attempt -lt $MAX_RETRY ]]; do
        attempt=$((attempt + 1))
        log "Phase ${phase}: 开始执行 (第 ${attempt}/${MAX_RETRY} 次)"

        # Step 1: Execute
        if [[ "$status" != "in_progress" && "$status" != "pending_review" ]]; then
            log "Phase ${phase}: execute..."
            if ! ${Qualix} execute "${phase}" >> "${LOG_FILE}" 2>&1; then
                log "Phase ${phase}: execute 失败"
                continue
            fi
        fi

        # Step 2: Headless Agent 执行（使用 claude CLI）
        local skill_prompt
        skill_prompt=$(${Qualix} orchestrate "${phase}" 2>/dev/null | grep worker | awk '{print $NF}')

        if [[ -n "$skill_prompt" && -f "$skill_prompt" ]]; then
            log "Phase ${phase}: 调用 claude headless..."
            claude -p "读取 ${skill_prompt} 并执行其中的任务。项目: ${PROJECT_ID}, Phase: ${phase}。完成后将产物写入 output/${PROJECT_ID}/ 目录。" \
                --allowedTools "Read,Edit,Write,Bash,Grep,Glob" \
                --max-turns 50 \
                >> "${LOG_FILE}" 2>&1 || true
        fi

        # Step 3: Finalize
        log "Phase ${phase}: finalize..."
        if ${Qualix} finalize "${phase}" >> "${LOG_FILE}" 2>&1; then
            log "Phase ${phase}: finalize 成功"

            # Step 4: Auto-approve (headless 模式)
            ${Qualix} approve "${phase}" -c "headless pipeline auto-approve" >> "${LOG_FILE}" 2>&1 || true
            log "Phase ${phase}: 完成"
            return 0
        else
            log "Phase ${phase}: finalize 失败（可能缺少推理日志或产物不完整）"
        fi
    done

    log "Phase ${phase}: 达到最大重试次数 (${MAX_RETRY})，标记失败"
    return 1
}

# 主流程
log "=========================================="
log "Qualix Headless Pipeline — ${PROJECT_ID}"
log "并行模式: ${PARALLEL}, 最大重试: ${MAX_RETRY}"
log "=========================================="

# Phase A（无依赖）
run_phase "A" || { log "Phase A 失败，流水线终止"; exit 1; }

if [[ "$PARALLEL" == "true" ]]; then
    # A.5 + A.6 + B 并行
    log "并行执行: A.5 + A.6 + B"
    run_phase "A.5" &
    PID_A5=$!
    run_phase "A.6" &
    PID_A6=$!
    run_phase "B" &
    PID_B=$!

    # 等待并行任务完成
    FAILED=0
    wait $PID_A5 || { log "Phase A.5 失败"; FAILED=$((FAILED+1)); }
    wait $PID_A6 || { log "Phase A.6 失败"; FAILED=$((FAILED+1)); }
    wait $PID_B  || { log "Phase B 失败"; FAILED=$((FAILED+1)); }

    if [[ $FAILED -gt 0 ]]; then
        log "${FAILED} 个并行 Phase 失败"
    fi
else
    # 串行执行
    run_phase "A.5" || log "Phase A.5 失败，继续"
    run_phase "A.6" || log "Phase A.6 失败，继续"
    run_phase "B"   || log "Phase B 失败，继续"
fi

# C 依赖 B
run_phase "C" || log "Phase C 失败，继续"

# D 依赖 A.5 + A.6
run_phase "D" || log "Phase D 失败，继续"

# 汇总
log "=========================================="
log "Pipeline 完成"
log "=========================================="
${Qualix} status 2>/dev/null | tee -a "${LOG_FILE}"
