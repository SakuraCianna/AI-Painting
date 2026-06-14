# AI Painting

**一款纯语音控制的可编辑绘图 Agent, 面向结构图、矢量场景、文生图与图生图精修。**

[![CI](https://github.com/SakuraCianna/AI-Painting/actions/workflows/ai-painting-ci.yml/badge.svg)](https://github.com/SakuraCianna/AI-Painting/actions/workflows/ai-painting-ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-24-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111111)](https://react.dev/)
[![Coverage](https://img.shields.io/badge/Coverage-85%25%20gate-34A853)](#测试与质量)

[简体中文](README.md) | [English](README_EN.md)

AI Painting 是一个只能通过语音完成创作的绘图工作台。它把用户语音转成可验证、可撤销、可继续编辑的绘图计划, 再由程序化渲染或图像模型完成画面生成。

项目目标不是普通文生图 Demo, 而是一套可长期扩展的绘图 Agent:

```txt
语音 -> ASR -> 渲染策略路由 -> 规则解析 / Drawing Agent -> 结构化计划 -> SVG 画布 / 图片对象
```

![AI Painting workspace](docs/screenshots/voice-drawing-workspace.png)

## 核心特性

- **纯语音绘图**: 绘图、编辑、撤销、恢复、导出都通过语音指令完成。
- **专业图表优先 PlantUML**: ER 图、系统架构图、流程图、时序图、UML 类图、组织结构图、甘特图和泳道图会生成 PlantUML 源码并渲染为 SVG 图层, 保留源码便于后续语音修改。
- **矢量场景优先**: 房子、草地、太阳、树和简单场景走程序化 SVG 渲染, 便于精确修改。
- **生图增强**: 水墨画、二次元人物、商业视觉图等艺术类任务可以走 GPT-image-2 或 OpenAI 兼容 Provider。
- **图生图精修**: 支持基于上一张图片和追改指令继续精修, 例如“把右边那个人的眼睛调亮”。
- **复杂指令拆解**: Drawing Agent 能把复杂语音拆成结构化步骤, 再由执行器逐步落到画布。
- **安全确认链**: 清空画布等高风险操作保留 `requires_confirmation`, 确认后才真正执行。
- **复合撤销**: 一条语音生成的多步操作可以整体撤销和恢复。
- **ASR 多级兜底**: 小米 MiMo ASR 优先, 本地 Qwen3-ASR 和 Web Speech API 作为备用路径。
- **延迟观测**: 记录 ASR、规划、执行和端到端耗时, 方便继续优化响应速度。

## 当前能力

| 能力 | 状态 | 示例 |
| --- | --- | --- |
| 基础图形 | 已支持 | “画一个蓝色圆形在中间, 半径一百” |
| 复合场景 | 已支持 | “画一个房子, 红色屋顶, 蓝色门, 两扇窗户” |
| 批量绘制 | 已支持 | “画三颗黄色星星, 从左到右变小” |
| 语义编辑 | 已支持 | “把房子的窗户都变大” |
| 高级选择 | 已支持 | “把屋顶下面的门改成绿色” |
| 复合撤销 | 已支持 | 一次撤销整条语音计划 |
| 清空确认 | 已支持 | “清空画布” -> “确认清空” |
| Agent 模板 | 第一版 | 客厅、PlantUML 专业图表、信息图、海报、UI 草图、开放场景 |
| PlantUML 专业图表 | 第一版 | ER 图、系统架构图、流程图、时序图、UML 类图、组织结构图、甘特图、泳道图 |
| 开放场景构图 | 第一版 | “画一个公园场景, 有草地、太阳、两棵树、一条小路和长椅” |
| 文生图 | Provider 链路已支持 | “生成一张二次元动漫人物” |
| 图生图精修 | Provider 链路已支持 | “继续把他的头发柔和一点” |
| 语音导出 | 已支持 | “导出 PNG”“导出 SVG”“导出项目 JSON” |
| 本地 ASR | 服务脚手架已支持 | Qwen3-ASR HTTP 服务 |

## 技术栈

| 层 | 技术 |
| --- | --- |
| Backend | Python 3.12.10, FastAPI, SQLite, pytest, pytest-cov |
| Agent | LangGraph, SceneGraph v2, PlantUML, Pydantic schema validation |
| Frontend | React 19, TypeScript, Vite, Web Audio API, Web Speech API, Iconify |
| AI Providers | Xiaomi MiMo ASR, Xiaomi MiMo-v2.5-Pro, Xiaomi MiMo TTS, Qwen3-ASR, OpenAI-compatible image APIs |
| Quality | GitHub Actions, pytest-cov, Vitest coverage, Ruff, mypy, pre-commit, Docker Compose validation |

## 快速开始

### 环境要求

- Windows 11
- PowerShell 7
- Python 3.12.10
- Node.js 24
- npm
- Chromium 内核浏览器或其他支持麦克风录音的浏览器

### 安装依赖

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm ci --prefix frontend
```

需要运行本地质量门禁时, 额外安装开发依赖:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

### 配置环境变量

```powershell
Copy-Item .env.example .env
```

没有真实模型密钥时, 项目仍可以使用占位 Provider 跑通主要开发流程。真实密钥只写入本地 `.env`, 不要写入 README、Issue、PR、提交信息或日志。

### 启动开发环境

推荐使用快速启动脚本:

```powershell
.\快速启动.bat
```

默认服务地址:

- Backend: `http://127.0.0.1:8084`
- Frontend: `http://127.0.0.1:3001`

也可以手动启动:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8084 --reload
```

```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8084"
npm run dev --prefix frontend -- --host 127.0.0.1 --port 3001 --strictPort
```

### 可选启动本地 Qwen3-ASR

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-local-asr.txt
.\.venv\Scripts\python.exe backend\local_asr_qwen3.py
```

更多说明见 [本地 Qwen3-ASR 文档](docs/local-asr-qwen3.md)。

## 常用语音示例

```txt
新建一张横向白色画布
画一个房子, 红色屋顶, 蓝色门, 两扇窗户
画一个语音绘图流程图, 从用户语音到 ASR, 再到规划器, 最后到画布执行
画一个AI绘图系统架构图, 包含前端、后端、ASR服务、Agent规划器、SQLite数据库和图像生成服务
画一个用户订单ER图, 包含用户、订单、商品和支付
画一个语音绘图调用时序图
画一个绘图 Agent UML 类图
画一个图书馆借阅ER图, 实体包括读者、图书、借阅记录、馆员, 关系包括读者借阅图书、馆员管理图书
画一个产品团队组织结构图, 包括负责人、产品经理、设计负责人、研发负责人、前端工程师、后端工程师
画一个产品迭代项目排期甘特图, 包含需求、设计、开发、测试和上线里程碑
画一个泳道图, 泳道包括产品、设计、研发、测试, 节点包括需求评审、原型设计、开发联调、验收发布
画一个公园场景, 有草地、太阳、两棵树、一条小路和长椅
把左边第二棵树改成黄色
生成一张二次元动漫人物
精修我的图片
清空画布
确认清空
撤销
恢复
导出 PNG
导出 SVG
导出项目 JSON
```

## 环境变量

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 前端请求后端地址 | `http://127.0.0.1:8084` |
| `AI_PAINTING_DB` | SQLite 数据库路径 | `backend\data\ai_painting.sqlite3` |
| `AI_PAINTING_SQLITE_CACHE_SIZE_KIB` | SQLite 连接页缓存大小, 单位 KiB | `8192` |
| `AI_PAINTING_CORS_ORIGINS` | 后端 CORS 允许来源 | `http://localhost:3001,http://127.0.0.1:3001` |
| `MIMO_API_KEY` | 小米 MiMo API Key | 空 |
| `AI_PAINTING_ASR_PROVIDERS` | 后端 ASR Provider 顺序 | `xiaomi,local` |
| `AI_PAINTING_ENABLE_AGENT_PLANNER` | 启用 Drawing Agent | `true` |
| `AI_PAINTING_LOCAL_ASR_URL` | 本地 ASR HTTP 服务地址 | `http://127.0.0.1:9001/asr` |
| `AI_PAINTING_TEXT_IMAGE_MODEL` | 文生图模型 | `gpt-image-2` |
| `AI_PAINTING_IMAGE_EDIT_MODEL` | 图生图模型 | `gpt-image-2` |
| `AI_PAINTING_OPENAI_API_KEY` | OpenAI 官方备用 API Key | 空 |
| `AI_PAINTING_OPENAI_BASE_URL` | OpenAI 官方备用 Base URL | `https://api.openai.com/v1` |
| `AI_PAINTING_PLANTUML_JAR` | PlantUML 本地 jar 路径, 配置后优先本地渲染 | 空 |
| `AI_PAINTING_PLANTUML_SERVER_URL` | PlantUML Server 地址, 为空时不会上传源码到外部服务 | 空 |
| `AI_PAINTING_PLANTUML_SECURITY_PROFILE` | PlantUML 安全模式 | `SANDBOX` |
| `AI_PAINTING_PLANTUML_TIMEOUT_SECONDS` | PlantUML 渲染超时时间, 单位秒 | `8` |
| `AI_PAINTING_PLANTUML_MAX_SOURCE_CHARS` | PlantUML 最大源码长度 | `12000` |
| `AI_PAINTING_JAVA_BIN` | Java 命令路径 | `java` |

文字转图片和图生图精修的中转站请求尺寸由后端运行时决定: 空白画布生成图片时使用当前画布尺寸, 基于已有图片精修时沿用源图片尺寸。旧的固定尺寸变量不再建议配置。

PlantUML 图表会优先使用 `AI_PAINTING_PLANTUML_JAR` 本地渲染, 其次使用显式配置的 `AI_PAINTING_PLANTUML_SERVER_URL`。两者都为空时, 后端会生成安全的 SVG 源码预览图层, 不会阻断语音绘图流程。

完整变量说明见 [.env.example](.env.example)。

## 测试与质量

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m pytest backend\tests --cov=app --cov-report=term-missing --cov-fail-under=85
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
.\.venv\Scripts\python.exe -m ruff format --check backend\app backend\tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\pre-commit.exe run --all-files
npm run test:coverage --prefix frontend
npm run test:e2e --prefix frontend
npm run build --prefix frontend
git diff --check
```

真实 Provider 评测脚手架:

```powershell
.\.venv\Scripts\python.exe backend\evaluate_asr_samples.py docs\evaluation\asr-samples.example.json --output reports\asr-xiaomi.json
.\.venv\Scripts\python.exe backend\evaluate_image_provider.py docs\evaluation\image-provider-samples.example.json --output reports\image-provider.json
```

首次运行 e2e 如果提示缺少 Chromium 浏览器, 先在 Windows PowerShell 执行:

```powershell
npm --prefix frontend exec -- playwright install chromium
```

`npm run test:e2e --prefix frontend` 会启动 Vite dev server, 使用 Playwright Chromium 模拟 Web Speech API 最终转写文本, 验证无键盘快捷绘图入口、语音新建画布、绘制、编辑、撤销、恢复、PNG/SVG/项目 JSON 下载边界、SVG 像素抽样、重叠语音指令单飞保护、麦克风拒绝后的 Web Speech fallback 和无语音识别能力时的禁用状态。

CI 会在 `push`、`pull_request` 和手动触发时运行 Ruff、渐进式 mypy、pre-commit、后端测试、前端测试、前端构建、Docker 校验和 API smoke test。当前 mypy 先覆盖 Agent 图执行、SceneGraph、编译器、validator、metrics、ASR/图片评测和策略模块, planner 大文件仍在后续拆分计划内。

## 项目结构

```txt
.
├── backend
│   ├── app
│   ├── evaluate_asr_samples.py
│   ├── evaluate_image_provider.py
│   ├── local_asr_qwen3.py
│   ├── requirements-dev.txt
│   ├── requirements.txt
│   └── tests
├── frontend
│   ├── src
│   ├── package.json
│   └── vite.config.ts
├── docs
│   ├── agent-architecture.md
│   ├── evaluation
│   ├── local-asr-qwen3.md
│   └── status
├── .github
├── .pre-commit-config.yaml
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── README_EN.md
├── ROADMAP.md
├── 需求文档.md
├── 设计文档.md
└── 快速启动.bat
```

## 文档索引

- [English README](README_EN.md)
- [产品路线图](ROADMAP.md)
- [设计文档](设计文档.md)
- [需求文档](需求文档.md)
- [Drawing Agent 架构](docs/agent-architecture.md)
- [当前差距评估](docs/status/voice-drawing-gap-analysis.md)
- [复杂命令评测集](docs/evaluation/command-evaluation.md)
- [ASR 样本评测](docs/evaluation/asr-benchmark.md)
- [图片 Provider 评测](docs/evaluation/image-provider-benchmark.md)
- [本地 Qwen3-ASR](docs/local-asr-qwen3.md)
- [Docker 备用部署](docs/docker-deploy.md)

## 已知限制

- 当前处于 MVP 后产品化扩展阶段, 还不是已经完成商业级验收的产品。
- 小米 ASR、本地 Qwen3-ASR、真实麦克风输入和 GPT-image-2 出图质量仍需要更多真实样本评测。
- 图生图局部精修目前主要依赖文本目标描述和上一轮图片元数据, 尚未实现视觉分割、mask 编辑或自动目标检测。
- SVG 是当前主编辑层, 已增加 layer/z-index 稳定排序和运行时能力标记, 但复杂像素级笔刷、滤镜、大画布、无限画布和高频动画仍需要 Canvas / OffscreenCanvas 增强。
- Ruff 和 pre-commit 已全仓落地, mypy 仍是渐进式门禁, 尚未覆盖 planner、repositories、drawing_engine 等历史大文件。

## 贡献

提交 PR 前请阅读:

- [.github/GITHUB_WORKFLOW.md](.github/GITHUB_WORKFLOW.md)
- [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)
- [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md)

PR 描述需要包含修改内容、修改原因、关键文件、已运行检查、检查结果、已知风险、截图或录屏以及后续建议。
