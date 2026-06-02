#!/bin/bash

# 专利智脑 - 启动脚本
# Usage:
#   ./start.sh dev          # 启动开发环境 (frontend:3000, backend:8000)
#   ./start.sh testing      # 启动测试环境 (frontend:3000, backend:8000, ENVIRONMENT=testing)
#   ./start.sh production   # 启动生产环境 (frontend:10001, backend:10002, ENVIRONMENT=production)
#   ./start.sh backend      # 仅启动后端 (默认 dev)
#   ./start.sh frontend     # 仅启动前端 (默认 dev)

set -e

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 环境配置 ──────────────────────────────────────────────
# 默认值 (dev)
ENV_MODE="dev"
ENV_VAR=""
BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_TITLE="Dev"

# ── 函数: 解析环境参数 ────────────────────────────────────
parse_env() {
    case "${1:-dev}" in
        dev)
            ENV_MODE="dev"
            ENV_VAR=""
            BACKEND_PORT=8000
            FRONTEND_PORT=3000
            BACKEND_TITLE="Dev"
            FRONTEND_API_URL="http://localhost:8000/api/v1"
            ;;
        testing)
            ENV_MODE="testing"
            ENV_VAR="ENVIRONMENT=testing"
            BACKEND_PORT=8000
            FRONTEND_PORT=3000
            BACKEND_TITLE="Testing"
            FRONTEND_API_URL="http://localhost:8000/api/v1"
            ;;
        production)
            ENV_MODE="production"
            ENV_VAR="ENVIRONMENT=production"
            BACKEND_PORT=10002
            FRONTEND_PORT=10001
            BACKEND_TITLE="Production"
            FRONTEND_API_URL="https://patent-api.lene.fun/api/v1"
            ;;
        *)
            echo -e "${RED}❌ 未知环境: $1${NC}"
            echo "可用选项: dev, testing, production"
            exit 1
            ;;
    esac
}

# ── 检查工具 ──────────────────────────────────────────────
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Python: $(python3 --version)${NC}"
}

check_node() {
    if ! command -v node &> /dev/null; then
        echo -e "${RED}❌ Node.js 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Node.js: $(node --version)${NC}"
}

# ── 启动后端 ──────────────────────────────────────────────
start_backend() {
    local env_mode="${1:-dev}"
    parse_env "$env_mode"

    echo ""
    echo -e "🚀 启动后端服务 (${CYAN}${BACKEND_TITLE}${NC})..."
    echo "-------------------"

    cd "$PROJECT_ROOT/backend"

    # 创建/激活虚拟环境
    if [ ! -d "venv" ]; then
        echo "📦 创建 Python 虚拟环境..."
        python3 -m venv venv
    fi
    source venv/bin/activate

    # 安装依赖
    if [ ! -f "venv/.deps_installed" ]; then
        echo "📦 安装 Python 依赖..."
        pip install -r requirements.txt
        touch venv/.deps_installed
    fi

    echo "✅ 后端启动中..."
    echo "   端口:  ${BACKEND_PORT}"
    echo "   API:   http://localhost:${BACKEND_PORT}"
    echo "   Docs:  http://localhost:${BACKEND_PORT}/docs"
    echo ""

    if [ -n "$ENV_VAR" ]; then
        eval "$ENV_VAR python main.py"
    else
        python main.py
    fi
}

# ── 启动前端 ──────────────────────────────────────────────
start_frontend() {
    local env_mode="${1:-dev}"
    parse_env "$env_mode"

    echo ""
    echo -e "🎨 启动前端服务 (${CYAN}${BACKEND_TITLE}${NC})..."
    echo "-------------------"

    cd "$PROJECT_ROOT/frontend"

    if [ ! -d "node_modules" ]; then
        echo "📦 安装 npm 依赖..."
        npm install
    fi

    echo "✅ 前端启动中..."
    echo "   端口:  ${FRONTEND_PORT}"
    echo "   URL:   http://localhost:${FRONTEND_PORT}"
    echo "   API:   ${FRONTEND_API_URL}"
    echo ""

    echo "NEXT_PUBLIC_API_URL=${FRONTEND_API_URL}" > "$PROJECT_ROOT/frontend/.env.local"

    if [ "$ENV_MODE" = "production" ]; then
        echo "📦 构建生产版本..."
        npx next build
        echo "🚀 启动生产服务器..."
        npx next start -p "${FRONTEND_PORT}"
    else
        npx next dev -p "${FRONTEND_PORT}"
    fi
}

# ── 一键启动 (前后端) ────────────────────────────────────
start_all() {
    local env_mode="${1:-dev}"
    parse_env "$env_mode"

    echo "========================================"
    echo "   专利智脑 - AI专利申请多智能体系统"
    echo "   环境: ${CYAN}${BACKEND_TITLE}${NC}"
    echo "========================================"
    echo ""

    check_python
    check_node

    echo ""
    echo "📋 启动前后端..."
    echo "   后端 → http://localhost:${BACKEND_PORT}"
    echo "   前端 → http://localhost:${FRONTEND_PORT}"
    echo ""

    cd "$PROJECT_ROOT/backend"

    # 创建/激活虚拟环境
    if [ ! -d "venv" ]; then
        echo "📦 创建 Python 虚拟环境..."
        python3 -m venv venv
    fi
    source venv/bin/activate

    # 安装后端依赖
    if [ ! -f "venv/.deps_installed" ]; then
        echo "📦 安装 Python 依赖..."
        pip install -r requirements.txt
        touch venv/.deps_installed
    fi

    # 启动后端 (后台)
    BACKEND_LOG="$PROJECT_ROOT/backend/logs/server.log"
    mkdir -p "$(dirname "$BACKEND_LOG")"
    echo "📋 后端日志: ${BACKEND_LOG}"
    echo ""

    if [ -n "$ENV_VAR" ]; then
        eval "$ENV_VAR nohup python main.py > \"$BACKEND_LOG\" 2>&1 &"
    else
        nohup python main.py > "$BACKEND_LOG" 2>&1 &
    fi
    BACKEND_PID=$!
    echo -e "${GREEN}✓ 后端已启动 (PID: ${BACKEND_PID})${NC}"

    cd "$PROJECT_ROOT/frontend"
    if [ ! -d "node_modules" ]; then
        echo "📦 安装 npm 依赖..."
        npm install
    fi

    echo ""
    echo -e "🎨 启动前端..."
    echo "   API:   ${FRONTEND_API_URL}"
    echo ""

    trap "echo ''; echo '🛑 关闭后端 (PID: ${BACKEND_PID})...'; kill ${BACKEND_PID} 2>/dev/null; exit 0" SIGINT SIGTERM

    echo "NEXT_PUBLIC_API_URL=${FRONTEND_API_URL}" > "$PROJECT_ROOT/frontend/.env.local"

    if [ "$ENV_MODE" = "production" ]; then
        echo "📦 构建生产版本..."
        npx next build
        echo "🚀 启动生产服务器..."
        npx next start -p "${FRONTEND_PORT}"
    else
        npx next dev -p "${FRONTEND_PORT}"
    fi

    # 前端退出后杀掉后端
    kill $BACKEND_PID 2>/dev/null
}

# ── 主逻辑 ──────────────────────────────────────────────
case "${1:-help}" in
    dev|development)
        start_all dev
        ;;
    testing)
        start_all testing
        ;;
    production|prod)
        start_all production
        ;;
    backend)
        parse_env "${2:-dev}"
        check_python
        start_backend "${2:-dev}"
        ;;
    frontend)
        parse_env "${2:-dev}"
        check_node
        start_frontend "${2:-dev}"
        ;;
    help|--help|-h)
        echo "使用方法:"
        echo "  ./start.sh dev          # 启动开发环境 (frontend:3000, backend:8000)"
        echo "  ./start.sh testing      # 启动测试环境 (frontend:3000, backend:8000)"
        echo "  ./start.sh production   # 启动生产环境 (frontend:10001, backend:10002)"
        echo ""
        echo "  ./start.sh backend [env]   # 仅后端服务"
        echo "  ./start.sh frontend [env]  # 仅前端服务"
        echo "  ./start.sh help            # 显示帮助"
        ;;
    *)
        echo -e "${RED}❌ 未知参数: $1${NC}"
        echo "使用: ./start.sh help 查看帮助"
        exit 1
        ;;
esac
