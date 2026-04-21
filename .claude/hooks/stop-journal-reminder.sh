#!/bin/bash
# Stop hook: prompt Claude to record session journal before exiting
JOURNAL_DIR="$(dirname "$0")/../journals"
mkdir -p "$JOURNAL_DIR"

echo "请在结束前执行 /record-session，将本次工作摘要写入 journal 供下次 session 使用。"
