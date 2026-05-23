#!/bin/bash

# 专利智脑 - 启动脚本
# Usage:
#   ./start.sh          # 启动前端 + 后端
#   ./start.sh backend  # 仅启动后端
#   ./start.sh frontend # 仅启动前端

set -e

echo "========================================"
echo "   专利智脑 - AI专利申请多智能体系统"
echo "========================================"
echo ""

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python 3 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Python: $(python3 --version)${NC}"
}

# 检查 Node.js
check_node() {
    if ! command -v node &> /dev/null; then
        echo -e "${RED}❌ Node.js 未安装${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Node.js: $(node --version)${NC}"
}

# 启动后端
start_backend() {
    echo ""
    echo "🚀 启动后端服务..."
    echo "-------------------"

    cd "$PROJECT_ROOT/backend"

    # 创建虚拟环境（如果不存在
    if [ ! -d "venv" ]; then
        echo "📦 创建 Python 虚拟环境..."
        python3 -m venv venv
    fi

    # 激活虚拟环境
    source venv/bin/activate

    # 安装依赖
    if [ ! -f "venv/.deps_installed" ]; then
        echo "📦 安装 Python 依赖..."
        pip install -r requirements.txt
        touch venv/.deps_installed
    fi

    # 复制环境配置
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo ""
        echo -e "${YELLOW}⚠️  已创建默认配置: backend/.env${NC}"
        echo -e "${YELLOW}   请配置 API Key 后重新启动${NC}"
        echo ""
    fi

    echo "✅ 后端服务启动在 http://localhost:8000"
    echo "📖 API文档: http://localhost:8000/docs"
    echo ""

    python main.py
}

# 启动前端
start_frontend() {
    echo ""
    echo "🎨 启动前端服务..."
    echo "-------------------"

    cd "$PROJECT_ROOT/frontend"

    # 安装依赖
    if [ ! -d "node_modules" ]; then
        echo "📦 安装 npm 依赖..."
        npm install
    fi

    echo "✅ 前端服务启动在 http://localhost:3000"
    echo ""

    npm run dev
}

# 主逻辑
case "${1:-all}" in
    backend)
        check_python
        start_backend
        ;;

    frontend)
        check_node
        start_frontend
        ;;

    all)
        check_python
        check_node

        echo ""
        echo "📋 启动模式: 前端 + 后端 (需要两个终端窗口
        echo "------------------------------------------------"

        if [ -z "$TMUX" ] && [ -z "$(which tmux)" ]; then
            echo -e "${YELLOW}💡 建议: 在不同终端分别运行:${NC}"
            echo "   ./start.sh backend"
            echo "   ./start.sh frontend"
            echo ""
            echo "   或安装 tmux 实现一键启动多窗口: brew install tmux"
        fi

        # 检查是否安装 concurrently
        if command -v concurrently &> /dev/null; then
            concurrently --names "BACKEND,FRONTEND" -c "bgBlue.bold,bgMagenta.bold" \
                "$PROJECT_ROOT/start.sh backend 2>&1 | head -20" \
                "$PROJECT_ROOT/start.sh frontend 2>&1 | head -20"
        else
            echo ""
            echo "请分别在两个终端运行："
            echo ""
            echo "终端 1 (后端):"
            echo "  cd $PROJECT_ROOT && ./start.sh backend"
            echo ""
            echo "终端 2 (前端):"
            echo "  cd $PROJECT_ROOT && ./start.sh frontend"
            echo ""
        fi
        ;;

    help)
        echo "使用方法:"
        echo "  ./start.sh          # 显示启动说明"
        echo "  ./start.sh backend  # 启动后端服务"
        echo "  ./start.sh frontend # 启动前端服务"
        echo "  ./start.sh help     # 显示帮助"
        ;;
    *)
        echo -e "${RED}未知参数: $1${NC}"
        echo ""
        echo "使用 ./start.sh help 查看帮助"
        exit 1
        ;;
esac
