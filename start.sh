#!/bin/bash

# 专利智脑 - 启动脚本
# Usage:
#   ./start.sh dev          # 启动开发环境 (frontend:3000, backend:8000)
#   ./start.sh testing      # 启动测试环境 (frontend:3000, backend:8000, ENVIRONMENT=testing)
#   ./start.sh production   # 启动生产环境 (frontend:10001, backend:10002, ENVIRONMENT=production)
#   ./start.sh stop [env]   # 停止服务 (all/dev/testing/production)
#   ./start.sh backend      # 仅启动后端 (默认 dev)
#   ./start.sh frontend     # 仅启动前端 (默认 dev)

set -e

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
RUNTIME_ROOT="$PROJECT_ROOT/.runtime/start.sh"

# ── 颜色输出 ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── 环境配置 ──────────────────────────────────────────────
# 默认值 (dev)
ENV_MODE="dev"
BACKEND_PORT=8000
FRONTEND_PORT=3000
BACKEND_TITLE="Dev"
FRONTEND_ENV_FILE="$PROJECT_ROOT/frontend/.env.development"
BACKEND_ENV_FILE="$PROJECT_ROOT/backend/.env"

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
            FRONTEND_ENV_FILE="$PROJECT_ROOT/frontend/.env.development"
            BACKEND_ENV_FILE="$PROJECT_ROOT/backend/.env"
            ;;
        testing)
            ENV_MODE="testing"
            ENV_VAR="ENVIRONMENT=testing"
            BACKEND_PORT=8000
            FRONTEND_PORT=3000
            BACKEND_TITLE="Testing"
            FRONTEND_API_URL="http://localhost:8000/api/v1"
            FRONTEND_ENV_FILE="$PROJECT_ROOT/frontend/.env.development"
            BACKEND_ENV_FILE="$PROJECT_ROOT/backend/.env.testing"
            ;;
        production)
            ENV_MODE="production"
            ENV_VAR="ENVIRONMENT=production"
            BACKEND_PORT=10002
            FRONTEND_PORT=10001
            BACKEND_TITLE="Production"
            FRONTEND_API_URL="https://patent-api.lene.fun/api/v1"
            FRONTEND_ENV_FILE="$PROJECT_ROOT/frontend/.env.production"
            BACKEND_ENV_FILE="$PROJECT_ROOT/backend/.env.production"
            ;;
        *)
            echo -e "${RED}❌ 未知环境: $1${NC}"
            echo "可用选项: dev, testing, production"
            exit 1
            ;;
    esac
}

runtime_dir() {
    local env_mode=$1
    echo "$RUNTIME_ROOT/$env_mode"
}

pid_file() {
    local env_mode=$1
    local service=$2
    echo "$(runtime_dir "$env_mode")/${service}.pid"
}

log_file() {
    local env_mode=$1
    local service=$2
    echo "$(runtime_dir "$env_mode")/${service}.log"
}

ensure_runtime_dir() {
    mkdir -p "$(runtime_dir "$ENV_MODE")"
}

is_pid_running() {
    local pid=$1
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
    local file=$1
    if [ -f "$file" ]; then
        tr -d '[:space:]' < "$file"
    fi
    return 0
}

write_pid() {
    local env_mode=$1
    local service=$2
    local pid=$3
    mkdir -p "$(runtime_dir "$env_mode")"
    echo "$pid" > "$(pid_file "$env_mode" "$service")"
}

assert_backend_env_file() {
    if [ ! -f "$BACKEND_ENV_FILE" ]; then
        echo -e "${RED}❌ 后端环境文件不存在: ${BACKEND_ENV_FILE}${NC}"
        exit 1
    fi
}

assert_frontend_env_file() {
    if [ ! -f "$FRONTEND_ENV_FILE" ]; then
        echo -e "${RED}❌ 前端环境文件不存在: ${FRONTEND_ENV_FILE}${NC}"
        exit 1
    fi
}

ensure_not_running() {
    local service=$1
    local file
    local pid
    file=$(pid_file "$ENV_MODE" "$service")
    pid=$(read_pid "$file")
    if is_pid_running "$pid"; then
        echo -e "${YELLOW}⚠ ${service} (${ENV_MODE}) 已运行 (PID: ${pid})${NC}"
        exit 1
    fi
    rm -f "$file"
}

stop_recorded_service() {
    local env_mode=$1
    local service=$2
    local name=$3
    local file
    local pid
    file=$(pid_file "$env_mode" "$service")
    pid=$(read_pid "$file")
    if is_pid_running "$pid"; then
        kill "$pid" 2>/dev/null || true
        for _ in {1..30}; do
            is_pid_running "$pid" || break
            sleep 0.1
        done
        if is_pid_running "$pid"; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
        echo -e "${GREEN}✓ ${name} 已停止 (PID: ${pid})${NC}"
    else
        echo -e "${YELLOW}⚠ ${name} 未运行${NC}"
    fi
    rm -f "$file"
}

stop_recorded_env() {
    local env_mode=$1
    stop_recorded_service "$env_mode" "frontend" "前端 (${env_mode})"
    stop_recorded_service "$env_mode" "backend" "后端 (${env_mode})"
}

stop_started_service() {
    local env_mode=$1
    local service=$2
    local name=$3
    local expected_pid=$4
    local file
    file=$(pid_file "$env_mode" "$service")

    if is_pid_running "$expected_pid"; then
        kill "$expected_pid" 2>/dev/null || true
        for _ in {1..30}; do
            is_pid_running "$expected_pid" || break
            sleep 0.1
        done
        echo -e "${GREEN}✓ ${name} 已停止 (PID: ${expected_pid})${NC}"
    fi

    if [ "$(read_pid "$file")" = "$expected_pid" ]; then
        rm -f "$file"
    fi
}

stop_started_env() {
    local env_mode=$1
    local backend_pid=$2
    local frontend_pid=$3
    stop_started_service "$env_mode" "frontend" "前端 (${env_mode})" "$frontend_pid"
    stop_started_service "$env_mode" "backend" "后端 (${env_mode})" "$backend_pid"
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
    assert_backend_env_file

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

    PATENT_AGENTS_ENV_FILE="$BACKEND_ENV_FILE" python main.py
}

# ── 启动前端 ──────────────────────────────────────────────
start_frontend() {
    local env_mode="${1:-dev}"
    parse_env "$env_mode"

    echo ""
    echo -e "🎨 启动前端服务 (${CYAN}${BACKEND_TITLE}${NC})..."
    echo "-------------------"

    cd "$PROJECT_ROOT/frontend"
    assert_frontend_env_file

    if [ ! -d "node_modules" ]; then
        echo "📦 安装 npm 依赖..."
        npm install
    fi

    echo "✅ 前端启动中..."
    echo "   端口:  ${FRONTEND_PORT}"
    echo "   URL:   http://localhost:${FRONTEND_PORT}"
    echo "   API:   ${FRONTEND_API_URL}"
    echo ""

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
    ensure_runtime_dir
    assert_backend_env_file
    assert_frontend_env_file
    ensure_not_running backend
    ensure_not_running frontend

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
    BACKEND_LOG="$(log_file "$ENV_MODE" backend)"
    mkdir -p "$(dirname "$BACKEND_LOG")"
    echo "📋 后端日志: ${BACKEND_LOG}"
    echo ""

    PATENT_AGENTS_ENV_FILE="$BACKEND_ENV_FILE" nohup python main.py > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    write_pid "$ENV_MODE" backend "$BACKEND_PID"
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

    FRONTEND_LOG="$(log_file "$ENV_MODE" frontend)"
    trap "echo ''; echo '🛑 关闭服务 (${ENV_MODE})...'; stop_started_env '${ENV_MODE}' '${BACKEND_PID}' '${FRONTEND_PID:-}'; exit 0" SIGINT SIGTERM

    if [ "$ENV_MODE" = "production" ]; then
        echo "📦 构建生产版本..."
        npx next build
        echo "🚀 启动生产服务器..."
        nohup npx next start -p "${FRONTEND_PORT}" > "$FRONTEND_LOG" 2>&1 &
    else
        nohup npx next dev -p "${FRONTEND_PORT}" > "$FRONTEND_LOG" 2>&1 &
    fi
    FRONTEND_PID=$!
    write_pid "$ENV_MODE" frontend "$FRONTEND_PID"
    echo -e "${GREEN}✓ 前端已启动 (PID: ${FRONTEND_PID})${NC}"
    wait "$FRONTEND_PID"

    # 前端退出后杀掉后端
    stop_started_env "$ENV_MODE" "$BACKEND_PID" "$FRONTEND_PID"
}

stop_env() {
    local env_mode="${1:-all}"
    echo "========================================"
    echo "   停止服务 (${env_mode})"
    echo "========================================"
    echo ""
    case "$env_mode" in
        dev|development)
            stop_recorded_env dev
            ;;
        testing)
            stop_recorded_env testing
            ;;
        production|prod)
            stop_recorded_env production
            ;;
        all)
            stop_recorded_env dev
            stop_recorded_env testing
            stop_recorded_env production
            ;;
        *)
            echo -e "${RED}❌ 未知环境: $env_mode${NC}"
            echo "可用选项: dev, testing, production, all"
            exit 1
            ;;
    esac
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
    stop)
        stop_env "${2:-all}"
        ;;
    help|--help|-h)
        echo "使用方法:"
        echo "  ./start.sh dev          # 启动开发环境 (frontend:3000, backend:8000)"
        echo "  ./start.sh testing      # 启动测试环境 (frontend:3000, backend:8000)"
        echo "  ./start.sh production   # 启动生产环境 (frontend:10001, backend:10002)"
        echo "  ./start.sh stop [env]   # 停止服务 (all/dev/testing/production)"
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
