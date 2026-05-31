# 专利智脑 — 运行状态总览

> 最后更新: 2026-05-31

## 服务状态

| 服务 | 端口 | 状态 | PID | 访问地址 |
|------|------|------|-----|---------|
| **Frontend** (Next.js 14) | 10001 | ✅ 正常运行 (HTTP 200) | 72242 | http://localhost:10001 |
| **Backend** (FastAPI) | 10002 | ✅ 正常运行 (HTTP 200) | 64612 | http://localhost:10002/docs |

## 最近操作

### 本轮修复
1. ❌ **Frontend 500 错误** — 旧版 `.next/` build artifacts 缺少 `vendor-chunks/tailwind-merge.js`
   - 修复: `rm -rf .next && npm run build` 后重新启动
   - ✅ 现在 HTTP 200，日志零错误

### 之前成功
1. ✅ Backend 启动成功 (PID 64612, port 10002)
   - 日志: `frontend/src/logs/app-10002.log`
   - 健康端点: `GET /health` → `{"status":"healthy"}`
   - 根端点: `GET /` → `{"name":"专利智脑...","version":"1.0.0","status":"running"}`
2. ✅ Frontend 构建成功 (9 路由全部生成)
3. ✅ Backend 端口成功迁移 10001 → 10002 (避免与前端端口冲突)

## 当前 Session 上下文

- **PID 记录**: Backend=64612, Frontend=72242
- **日志文件**: `backend/logs/startup-10002.log`, `frontend/frontend-10001.log`
- **Git 状态**: 无未提交更改
- **关键配置**: 
  - 无 `.env` 文件 (直接使用默认值)
  - 数据库: SQLite (开发模式)
  - LLM: 未配置 API key (开发者手动指定)

## 如果需要重置

```bash
# 停止所有服务
kill 64612 72242 2>/dev/null

# 重启后端
poetry run uvicorn main:app --host 0.0.0.0 --port 10002 --reload

# 重建并重启前端
cd frontend && rm -rf .next && npm run build && npx next start -p 10001 &
```
