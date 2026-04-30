#!/usr/bin/env bash
set -euo pipefail

# DQG 一键安装脚本
# 用法: ./scripts/install.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo "=========================================="
echo "  DQG 一键安装"
echo "=========================================="
echo ""

ERRORS=0

# ---------------------------------------------------------------------------
# 1. Python >= 3.11
# ---------------------------------------------------------------------------
echo "检查 Python..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$PY_MINOR" -ge 11 ]; then
        ok "Python $PY_VER"
    else
        fail "Python $PY_VER < 3.11，请升级"
        echo "    macOS: brew install python@3.11"
        echo "    Linux: sudo apt install python3.11"
        ERRORS=$((ERRORS + 1))
    fi
else
    fail "Python 未安装"
    echo "    macOS: brew install python@3.11"
    echo "    Linux: sudo apt install python3.11"
    ERRORS=$((ERRORS + 1))
fi

if [ $ERRORS -gt 0 ]; then
    echo ""
    fail "Python 版本不满足，请先安装后重新运行此脚本"
    exit 1
fi

# ---------------------------------------------------------------------------
# 2. pip install
# ---------------------------------------------------------------------------
echo ""
echo "安装 Python 依赖..."
cd "$PROJECT_DIR"
pip install -e . -q && ok "dqg (pip install -e .)" || { fail "pip install -e . 失败"; ERRORS=$((ERRORS + 1)); }
pip install larkkit -q 2>/dev/null && ok "larkkit" || warn "larkkit 安装失败（飞书摄入不可用）"

# ---------------------------------------------------------------------------
# 3. Tesseract OCR
# ---------------------------------------------------------------------------
echo ""
echo "安装 OCR 引擎..."
if command -v tesseract &>/dev/null; then
    ok "tesseract 已安装"
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            echo "    $ brew install tesseract tesseract-lang"
            brew install tesseract tesseract-lang 2>/dev/null && ok "tesseract + 中文语言包" || warn "tesseract 安装失败（图片 OCR 不可用）"
        else
            warn "需要 Homebrew 安装 tesseract (https://brew.sh)"
        fi
    elif [[ "$OSTYPE" == "linux"* ]]; then
        echo "    $ sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim"
        sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim 2>/dev/null && ok "tesseract + 中文语言包" || warn "tesseract 安装失败"
    else
        warn "请手动安装 tesseract: https://github.com/tesseract-ocr/tesseract"
    fi
fi

# 验证中文语言包
if command -v tesseract &>/dev/null; then
    if tesseract --list-langs 2>/dev/null | grep -q "chi_sim"; then
        ok "tesseract 中文语言包 (chi_sim)"
    else
        warn "tesseract 缺少中文语言包"
    fi
fi

# ---------------------------------------------------------------------------
# 4. Node.js + agent-browser
# ---------------------------------------------------------------------------
echo ""
echo "安装 agent-browser..."
if command -v node &>/dev/null; then
    ok "Node.js $(node --version)"
    if command -v agent-browser &>/dev/null; then
        ok "agent-browser 已安装 ($(agent-browser --version 2>/dev/null || echo 'unknown'))"
    else
        echo "    $ npm install -g agent-browser"
        npm install -g agent-browser 2>/dev/null && ok "agent-browser" || warn "agent-browser 安装失败（画板截图不可用）"
        if command -v agent-browser &>/dev/null; then
            echo "    $ agent-browser install"
            agent-browser install 2>/dev/null && ok "agent-browser install" || warn "agent-browser install 失败"
        fi
    fi
else
    warn "Node.js 未安装，跳过 agent-browser"
    echo "    安装 Node.js: https://nodejs.org/ 或 brew install node"
fi

# ---------------------------------------------------------------------------
# 5. 配置 AI IDE MCP
# ---------------------------------------------------------------------------
echo ""
echo "配置 AI IDE..."

configure_mcp() {
    local mcp_path="$1"
    local ide_name="$2"
    local mcp_dir
    mcp_dir="$(dirname "$mcp_path")"

    if [ "$mcp_dir" != "$PROJECT_DIR" ] && [ ! -d "$mcp_dir" ]; then
        mkdir -p "$mcp_dir"
    fi

    if [ -f "$mcp_path" ]; then
        ok "$ide_name MCP 已存在 ($mcp_path)"
    else
        cat > "$mcp_path" << 'MCPEOF'
{
  "mcpServers": {}
}
MCPEOF
        ok "$ide_name MCP 已创建 ($mcp_path)"
    fi
}

# Claude Code
if command -v claude &>/dev/null || [ -d "$HOME/.claude" ]; then
    configure_mcp "$PROJECT_DIR/.mcp.json" "Claude Code"
fi

# Cursor
if [ -d "$HOME/.cursor" ] || [ -d "$PROJECT_DIR/.cursor" ]; then
    mkdir -p "$PROJECT_DIR/.cursor"
    configure_mcp "$PROJECT_DIR/.cursor/mcp.json" "Cursor"
fi

# Windsurf
if [ -d "$HOME/.windsurf" ] || [ -d "$PROJECT_DIR/.windsurf" ]; then
    mkdir -p "$PROJECT_DIR/.windsurf"
    configure_mcp "$PROJECT_DIR/.windsurf/mcp.json" "Windsurf"
fi

# Codex 不需要 MCP 配置
if command -v codex &>/dev/null; then
    ok "Codex 已安装（无需 MCP 配置）"
fi

# ---------------------------------------------------------------------------
# 6. 验证
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "  验证安装结果"
echo "=========================================="
echo ""

cd "$PROJECT_DIR"
dqg-run any-project doctor 2>/dev/null || true

echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "  ${GREEN}安装完成！${NC}"
else
    echo -e "  ${YELLOW}安装完成（有 $ERRORS 个问题需要手动处理）${NC}"
fi
echo ""
echo "  下一步:"
echo "    1. dqg-run <project-id> init --profile java-ddd-tmf"
echo "    2. 在 AI IDE 中执行 @dqg_starter.md"
echo "=========================================="
echo ""
