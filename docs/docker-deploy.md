# Docker 备用部署方案

> 本方案只作为备用部署和服务器验证路径。本机开发仍默认使用 `快速启动.bat`, 不要求 Docker。

## 1. 适用场景

- 临时在 Windows 11、Linux 服务器或云主机上启动完整前后端服务
- 验证发布包是否能在干净容器环境运行
- 给后续生产部署、反向代理和 HTTPS 网关预留基础

## 2. 服务结构

- `backend`: FastAPI 服务, 容器内监听 `8080`, 使用 SQLite volume 持久化数据
- `frontend`: Nginx 静态服务, 容器内监听 `80`, 默认映射到宿主机 `5173`
- `frontend/nginx.conf`: 把 `/api/` 和 `/health` 代理到 `backend:8080`
- `ai-painting-backend-data`: 保存 `backend/data/ai_painting.sqlite3`

## 3. 启动命令

在源码仓库根目录执行。当前 GitHub Release zip 是轻量运行包, 不包含完整前端源码, 不作为 Docker 构建上下文。

```powershell
docker compose build
docker compose up -d
```

访问前端:

```txt
http://127.0.0.1:5173
```

访问后端健康检查:

```txt
http://127.0.0.1:8080/health
```

查看日志:

```powershell
docker compose logs -f
```

停止服务:

```powershell
docker compose down
```

停止并删除 SQLite volume:

```powershell
docker compose down -v
```

## 4. 可选环境变量

Docker Compose 会从当前 PowerShell 环境变量或项目根目录 `.env` 读取插值变量。`.env` 不要提交到 Git。

```powershell
$env:MIMO_API_KEY="<你的 Xiaomi MiMo API Key>"
$env:AI_PAINTING_ENABLE_LLM_PLANNER="true"
$env:AI_PAINTING_ASR_PROVIDERS="xiaomi,local"
$env:AI_PAINTING_FRONTEND_PORT="5173"
$env:AI_PAINTING_BACKEND_PORT="8080"
docker compose up -d --build
```

如果本地 Qwen3-ASR 服务运行在宿主机 `9001` 端口, Windows Docker 可以这样让后端容器访问宿主机服务:

```powershell
$env:AI_PAINTING_LOCAL_ASR_URL="http://host.docker.internal:9001/asr"
docker compose up -d --build
```

默认 Docker 镜像不会安装 Qwen3-ASR 大模型依赖, 避免备用部署镜像过重。需要完整本地 ASR 时, 优先把 Qwen3-ASR 作为独立服务部署。

## 5. 当前边界

- 不包含 HTTPS, 生产环境需要放到反向代理或网关后面
- 不内置小米 API Key, 需要通过环境变量注入
- 不自动下载本地 ASR 模型权重
- 不替代 Windows 本地开发脚本
