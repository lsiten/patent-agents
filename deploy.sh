#!/bin/bash
# ==================== 专利智脑 - 本机部署脚本 ====================
# 部署端口：前端 10001，后端 10002
# 不修改任何 dev 配置文件，仅通过环境变量覆盖
# ================================================================
set -e

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BACKEND_PORT=10002
FRONTEND_PORT=10001

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${YELLOW}正在关闭服务...${NC}"
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null && echo "后端已停止"
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && echo "前端已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "========================================"
echo "   专利智脑 - 本机部署"
echo "   前端端口: ${FRONTEND_PORT}"
echo "   后端端口: ${BACKEND_PORT}"
echo "========================================"
echo ""

# ── 检查环境 ──
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

check_python
check_node

# ── 后端：检查虚拟环境和依赖 ──
cd "$PROJECT_ROOT/backend"
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 创建 Python 虚拟环境...${NC}"
    python3 -m venv venv
fi
source venv/bin/activate
if [ ! -f "venv/.deps_installed" ]; then
    echo -e "${YELLOW}📦 安装 Python 依赖...${NC}"
    pip install -r requirements.txt -q
    touch venv/.deps_installed
fi

# 检查 .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${YELLOW}⚠️  已创建 backend/.env，请配置 API Key 后重新运行${NC}"
    exit 1
fi

# ── 前端：检查 node_modules ──
cd "$PROJECT_ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 安装 npm 依赖...${NC}"
    npm install
fi

# ── 构建前端 (production build, 注入后端地址) ──
echo ""
echo -e "${YELLOW}🏗️  构建前端 (API: http://localhost:${BACKEND_PORT})...${NC}"
NEXT_PUBLIC_API_URL="http://localhost:${BACKEND_PORT}/api/v1" npm run build
echo -e "${GREEN}✓ 前端构建完成${NC}"

# ── 启动后端 ──
echo ""
echo -e "${YELLOW}🚀 启动后端服务 (端口 ${BACKEND_PORT})...${NC}"
cd "$PROJECT_ROOT/backend"
PORT=${BACKEND_PORT} python main.py &
BACKEND_PID=$!
echo -e "${GREEN}✓ 后端 PID: ${BACKEND_PID}${NC}"

# ── 启动前端 ──
echo -e "${YELLOW}🚀 启动前端服务 (端口 ${FRONTEND_PORT})...${NC}"
cd "$PROJECT_ROOT/frontend"
npx next start -p ${FRONTEND_PORT} &
FRONTEND_PID=$!
echo -e "${GREEN}✓ 前端 PID: ${FRONTEND_PID}${NC}"

# ── 等待后端就绪 ──
echo ""
echo -n "等待后端就绪"
for i in $(seq 1 30); do
    if curl -s "http://localhost:${BACKEND_PORT}/health" > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}✓ 后端已就绪${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "========================================"
echo -e "${GREEN}  ✅ 部署完成${NC}"
echo ""
echo "  前端地址: http://localhost:${FRONTEND_PORT}"
echo "  后端API:  http://localhost:${BACKEND_PORT}"
echo "  API文档:  http://localhost:${BACKEND_PORT}/docs"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "========================================"

# ── 等待任意子进程退出 ──
wait
