# GitHub 协作规范

## 提交 PR 要写什么

提交 PR 时使用 `.github/PULL_REQUEST_TEMPLATE.md`, 至少说明:

- 这次改了什么
- 变更类型
- 影响范围
- 本地验证结果
- 风险与回滚方式
- 关联的 Issue 或任务

## 提 Bug 要写什么

提交 Bug 时使用 `.github/ISSUE_TEMPLATE/bug_report.md`, 至少说明:

- 问题描述
- 复现步骤
- 期望结果
- 实际结果
- 环境信息
- 日志或截图

## 每次 push 后自动跑什么检查

`.github/workflows/ai-painting-ci.yml` 会在 Pull Request、任意分支 push 和手动触发时自动运行:

- 后端测试: 安装 `backend/requirements.txt`, 编译 `backend/app` 与 `backend/tests`, 执行 `python -m pytest backend/tests -q`
- 前端构建: 执行 `npm ci --prefix frontend`, 再执行 `npm run build --prefix frontend`
- API smoke test: 启动 FastAPI 服务, 请求 `GET /health` 验证后端可启动
- Docker 备用部署检查: 校验 `docker-compose.yml`, 并构建后端与前端备用部署镜像

`.github/workflows/cd.yml` 会在 `main` 分支 push、`v*` tag 和手动触发时自动运行:

- 后端测试
- 前端构建
- 组装发布 zip 产物
- 上传 GitHub Actions artifact
- 当 push 的是 `v*` tag 时自动创建 GitHub Release

CI/CD 使用 `.node-version` 固定 Node.js 24。工作流中的官方 GitHub Actions 也需要使用支持 Node.js 24 runtime 的版本, 否则即使项目 Node 版本是 24, 仍可能出现 Node.js 20 deprecation warning。
