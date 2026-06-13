# AI Painting

AI Painting 是一款纯语音控制的绘图工具原型。用户在应用内不通过鼠标或键盘绘图, 而是通过中文语音指令创建画布、绘制图形、修改样式、撤销恢复、保存作品和导出图片。

## 功能特性

- 语音识别文本到绘图操作的解析闭环
- 支持创建画布、绘制基础图形、修改最近对象样式、移动对象、撤销和恢复
- 支持“清空画布 -> 确认清空”的高风险确认链, 清空后可撤销和恢复
- 支持“画一个房子, 红色屋顶, 蓝色门, 两扇窗户”这类复杂指令拆解
- 支持“画一个人物肖像”生成可继续编辑的矢量头像组合
- 支持“画一个温馨的小屋, 左边有两棵树, 右边有一条弯曲小路, 天空有三朵云”这类多主体场景模板
- 支持“画三颗黄色星星, 从左到右变小”这类批量绘制指令
- 支持“把所有蓝色图形改成绿色, 然后整体向上移动一点”这类批量编辑指令
- 支持最近对象缩放, 例如“把它放大一倍”
- 支持局部语义对象形状替换, 例如“把窗户改成圆形”
- 支持空间语义筛选, 例如“把左边窗户改大一点”
- 支持对象命名、图层元数据和语义标签, 例如“画一个黄色圆形, 命名为太阳, 放到前景层”
- 支持按语义标签批量编辑, 例如“把房子的窗户都变大”
- 支持多边形、路径和贝塞尔曲线, 例如“画一个绿色五边形”“画一条弯曲小路”
- 支持文字转图片 Provider 脚手架, 生成图片会作为 `image` 对象插入画布并支持撤销
- 支持渲染策略路由, 结构精确类图形走程序生成, 艺术表现类图形走生图模型
- 支持 Drawing Agent + SceneGraph v2 复杂规划入口, 例如“画一个温馨客厅, 有沙发、茶几、窗户和落地灯”
- 支持本地流程图 Agent 模板, 例如“画一个语音绘图流程图, 从用户语音到 ASR, 再到规划器, 最后到画布执行”
- 支持本地信息图 Agent 模板, 例如“画一个销售增长信息图, 包含营收、转化率、复购率和三个月柱状图”
- 支持本地海报 Agent 模板, 例如“画一个 AI 语音绘图新品发布海报, 突出主标题、产品视觉、三个卖点和立即体验按钮”
- 支持本地 UI 草图 Agent 模板, 例如“画一个语音绘图产品的 UI 草图, 包含侧边导航、顶部栏、搜索框、主卡片、趋势图和新建作品按钮”
- 支持本地组织结构图 Agent 模板, 例如“画一个产品团队组织结构图, 包括负责人、产品组、设计组、研发组和执行角色”
- 支持本地甘特图 Agent 模板, 例如“画一个产品迭代项目排期甘特图, 包含需求、设计、开发、测试和上线里程碑”
- 提供复杂语音指令评测集, 区分规则已支持用例、Agent 用例和后续规划器用例
- 支持低置信度追问, 多主体场景不会被规则解析器误执行为半成品
- 支持小米 MiMo ASR、本地 ASR、Web Speech API 三层语音识别降级
- 提供 Windows 11 本地 Qwen3-ASR 备用服务脚手架, 默认模型为 `Qwen/Qwen3-ASR-0.6B`
- 支持小米 MiMo-v2.5-Pro 作为 Drawing Agent 的复杂 SceneGraph 规划兜底
- 支持执行计划来源、解释文本、ScenePlan 步骤展示和小米 MiMo TTS 语音反馈
- 支持 ASR、规划、执行和端到端延迟指标展示
- 语音输入需要手动点击麦克风开始, 页面加载后不会自动录音
- 使用 SVG 渲染画布对象
- 使用 SQLite 保存作品、绘图对象、操作历史、作品版本和语音指令日志
- 绘图对象已支持 `layer_id`、`group_id`、`semantic_tags` 和 `transform` 元数据
- 前端工作台不提供鼠标拖拽绘图或键盘快捷绘图入口

## 产品路线图

长期目标和产品级扩展计划见 [ROADMAP.md](ROADMAP.md)。

## 当前状态与差距

当前项目处于 MVP 后产品化扩展阶段。它已经打通语音识别、指令解析、结构化绘图、持久化、撤销恢复和确认链, 但距离商业可用的纯语音绘图工具仍需要补齐真实 ASR 评测、复杂场景规划、复合撤销分组、无鼠标端到端验收和延迟 SLO。

阶段差距评估见 [docs/status/voice-drawing-gap-analysis.md](docs/status/voice-drawing-gap-analysis.md)。

## 技术栈

- Python 3.12.10
- FastAPI
- SQLite
- pytest
- LangGraph
- React
- TypeScript
- Vite
- Web Audio API
- Web Speech API
- Xiaomi MiMo ASR
- Qwen3-ASR local fallback
- Xiaomi MiMo-v2.5-Pro
- Xiaomi MiMo TTS
- Iconify

## 环境要求

- Windows 11
- PowerShell 7
- Python 3.12.10
- Node.js 24 和 npm
- 支持麦克风录音的浏览器, 例如 Chromium 内核浏览器

## 安装依赖

在项目根目录执行:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm install --prefix frontend
```

可选安装本地 Qwen3-ASR 备用服务:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-local-asr.txt
```

## 本地开发

快速启动前后端:

```powershell
.\快速启动.bat
```

脚本固定使用后端 `8084` 和前端 `3001`, 并打开前端地址。如果端口被占用, 对应服务会启动失败, 需要先关闭占用端口的进程。

启用本地 Qwen3-ASR 备用服务:

```powershell
$env:AI_PAINTING_START_LOCAL_ASR="1"
.\快速启动.bat
```

首次安装本地 ASR 可选依赖并启动:

```powershell
$env:AI_PAINTING_START_LOCAL_ASR="1"
$env:AI_PAINTING_INSTALL_LOCAL_ASR="1"
.\快速启动.bat
```

启动后端:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8084 --reload
```

启动前端:

```powershell
npm run dev --prefix frontend
```

默认访问地址:

```txt
http://127.0.0.1:3001
```

默认后端地址:

```txt
http://127.0.0.1:8084
```

## 构建命令

```powershell
npm run build --prefix frontend
```

## CI/CD

仓库内置 GitHub Actions 工作流:

- `.github/workflows/ai-painting-ci.yml`: 在 Pull Request、任意分支推送和手动触发时运行后端测试、前端构建和 API smoke test
- CI 还会校验 Docker Compose 配置并构建备用部署镜像
- `.github/workflows/cd.yml`: 在 `main` 推送、`v*` tag 和手动触发时构建发布包, tag 触发时自动创建 GitHub Release

CI 使用 Python `3.12.10` 和 `.node-version` 指定的 Node.js `24`。CD 产物包含后端源码、前端 `dist`、项目文档和 `快速启动.bat`。

## 测试或检查命令

后端测试:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

前端构建:

```powershell
npm run build --prefix frontend
```

Git 空白检查:

```powershell
git diff --check
```

## 环境变量说明

当前项目不要求必须配置 `.env` 文件。需要真实 ASR、TTS、Agent 或图片模型时, 可以复制示例文件后填写本机密钥:

```powershell
Copy-Item .env.example .env
```

可选环境变量:

```powershell
$env:AI_PAINTING_DB="E:\CodeHome\AI Painting\backend\data\ai_painting.sqlite3"
$env:VITE_API_BASE_URL="http://127.0.0.1:8084"
$env:MIMO_API_KEY="<你的 Xiaomi MiMo API Key>"
$env:AI_PAINTING_ASR_PROVIDERS="xiaomi,local"
$env:AI_PAINTING_ASR_LANGUAGE="zh"
$env:AI_PAINTING_LOCAL_ASR_URL="http://127.0.0.1:9001/asr"
$env:AI_PAINTING_LOCAL_ASR_LABEL="Qwen3-ASR 本地服务"
$env:AI_PAINTING_CORS_ORIGINS="http://localhost:3001,http://127.0.0.1:3001"
$env:QWEN3_ASR_MODEL="Qwen/Qwen3-ASR-0.6B"
$env:QWEN3_ASR_DEVICE="auto"
$env:QWEN3_ASR_DTYPE="auto"
$env:AI_PAINTING_ENABLE_AGENT_PLANNER="true"
$env:AI_PAINTING_MIMO_LLM_MODEL="mimo-v2.5-pro"
$env:AI_PAINTING_MIMO_TTS_MODEL="mimo-v2-tts"
$env:AI_PAINTING_MIMO_TTS_VOICE="default_zh"
$env:AI_PAINTING_MIMO_TTS_STYLE="自然 清晰"
$env:AI_PAINTING_IMAGE_PROVIDER="placeholder"
$env:AI_PAINTING_TEXT_IMAGE_URL="http://127.0.0.1:9010/generate"
$env:AI_PAINTING_TEXT_IMAGE_BASE_URL="https://corenode.best/v1"
$env:AI_PAINTING_TEXT_IMAGE_MODEL="local-text-to-image"
$env:AI_PAINTING_TEXT_IMAGE_API_KEY="<你的中转站 API Key>"
$env:AI_PAINTING_TEXT_IMAGE_SIZE="1024x768"
$env:AI_PAINTING_TEXT_IMAGE_WIDTH="512"
$env:AI_PAINTING_TEXT_IMAGE_HEIGHT="512"
$env:AI_PAINTING_IMAGE_EDIT_PROVIDER="openai_compatible"
$env:AI_PAINTING_IMAGE_EDIT_BASE_URL="https://corenode.best/v1"
$env:AI_PAINTING_IMAGE_EDIT_MODEL="gpt-image-2"
$env:AI_PAINTING_IMAGE_EDIT_API_KEY="<你的中转站 API Key>"
$env:AI_PAINTING_IMAGE_EDIT_SIZE="1024x768"
$env:AI_PAINTING_IMAGE_EDIT_RESPONSE_FORMAT="b64_json"
$env:AI_PAINTING_OPENAI_API_KEY=""
$env:AI_PAINTING_OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_API_KEY=""
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:AI_PAINTING_OPENAI_IMAGE_MODEL="gpt-image-2"
$env:AI_PAINTING_OPENAI_IMAGE_SIZE="auto"
```

说明:

- `AI_PAINTING_DB`: 后端 SQLite 数据库路径, 未设置时默认使用 `backend\data\ai_painting.sqlite3`
- `VITE_API_BASE_URL`: 前端请求后端 API 的地址, 未设置时默认使用 `http://127.0.0.1:8084`
- `MIMO_API_KEY`: 小米 MiMo API Key, 配置后后端会优先调用 `mimo-v2.5-asr`
- `AI_PAINTING_ASR_PROVIDERS`: 后端 ASR Provider 顺序, 默认是 `xiaomi,local`
- `AI_PAINTING_ASR_LANGUAGE`: 后端 ASR 语种, 默认是 `zh`, 小米接口也支持 `auto` 和 `en`
- `AI_PAINTING_LOCAL_ASR_URL`: 本地 ASR HTTP 服务地址, 作为小米 ASR 后的第一备用方案
- `AI_PAINTING_LOCAL_ASR_LABEL`: 前端展示的本地 ASR Provider 名称
- `AI_PAINTING_CORS_ORIGINS`: 后端允许的前端来源列表, 用英文逗号分隔, 默认只允许 `3001`
- `AI_PAINTING_LOCAL_ASR_COMMAND`: 本地 ASR 命令模板, 作为本地 HTTP 服务的替代方案, 命令需要把识别文本输出到 stdout
- `QWEN3_ASR_MODEL`: 本地 Qwen3-ASR 模型 ID 或本地模型目录, 默认是 `Qwen/Qwen3-ASR-0.6B`
- `QWEN3_ASR_DEVICE`: 本地 Qwen3-ASR 推理设备, 默认 `auto`
- `QWEN3_ASR_DTYPE`: 本地 Qwen3-ASR dtype, 默认 `auto`
- `AI_PAINTING_ENABLE_AGENT_PLANNER`: 是否启用 Drawing Agent 复杂指令规划, 可选值为 `true` 或 `false`
- `AI_PAINTING_ENABLE_LLM_PLANNER`: 旧规划器开关兼容变量, 未设置 `AI_PAINTING_ENABLE_AGENT_PLANNER` 时仍会读取
- `AI_PAINTING_MIMO_LLM_MODEL`: Agent 调用的小米复杂 SceneGraph 规划模型, 默认是 `mimo-v2.5-pro`
- `AI_PAINTING_MIMO_TTS_MODEL`: 小米语音合成模型, 默认是 `mimo-v2-tts`
- `AI_PAINTING_MIMO_TTS_VOICE`: 小米语音合成音色, 默认是 `default_zh`
- `AI_PAINTING_MIMO_TTS_STYLE`: 小米语音合成风格, 默认可不设置
- `AI_PAINTING_IMAGE_PROVIDER`: 文字转图片 Provider, 默认 `placeholder`, 可设置为 `http`、`openai_compatible` 或 `disabled`
- `AI_PAINTING_TEXT_IMAGE_URL`: HTTP 文字转图片服务地址, 仅 `AI_PAINTING_IMAGE_PROVIDER=http` 时需要
- `AI_PAINTING_TEXT_IMAGE_BASE_URL`: OpenAI 兼容文字转图片 Base URL, 设置为中转站地址时优先调用中转站
- `AI_PAINTING_TEXT_IMAGE_API_KEY`: HTTP 或 OpenAI 兼容文字转图片服务 Key, 可选, 不要写入 README 或 PR 描述
- `AI_PAINTING_TEXT_IMAGE_MODEL`: HTTP 或 OpenAI 兼容文字转图片模型名, 可选
- `AI_PAINTING_TEXT_IMAGE_SIZE`: OpenAI 兼容文字转图片输出尺寸, 用于中转站
- `AI_PAINTING_TEXT_IMAGE_WIDTH`: 默认生成图片宽度, 默认 512
- `AI_PAINTING_TEXT_IMAGE_HEIGHT`: 默认生成图片高度, 默认 512
- `AI_PAINTING_IMAGE_EDIT_PROVIDER`: 图生图精修 Provider, 默认 `placeholder`, 可设置为 `openai_compatible` 或 `disabled`
- `AI_PAINTING_IMAGE_EDIT_BASE_URL`: OpenAI 兼容图像编辑接口 Base URL, 设置为中转站地址时优先调用中转站
- `AI_PAINTING_IMAGE_EDIT_API_KEY`: 图生图精修 API Key, 不要提交到 git
- `AI_PAINTING_IMAGE_EDIT_MODEL`: 图生图精修模型名
- `AI_PAINTING_IMAGE_EDIT_SIZE`: 图生图精修输出尺寸, 用于中转站, 默认跟随画布尺寸
- `AI_PAINTING_IMAGE_EDIT_RESPONSE_FORMAT`: 图生图精修响应格式, 默认 `b64_json`
- `AI_PAINTING_OPENAI_API_KEY`: OpenAI 官方 API Key, 仅作为中转站失败后的备用, 也可使用标准 `OPENAI_API_KEY`
- `AI_PAINTING_OPENAI_BASE_URL`: OpenAI 官方 Base URL, 默认 `https://api.openai.com/v1`
- `OPENAI_API_KEY`: 标准 OpenAI API Key, 当 `AI_PAINTING_OPENAI_API_KEY` 为空时作为官方备用 Key
- `OPENAI_BASE_URL`: 标准 OpenAI Base URL, 当 `AI_PAINTING_OPENAI_BASE_URL` 为空时作为官方备用地址
- `AI_PAINTING_OPENAI_IMAGE_MODEL`: OpenAI 官方图片模型, 默认继承 `gpt-image-2`
- `AI_PAINTING_OPENAI_IMAGE_SIZE`: OpenAI 官方图片尺寸, 默认 `auto`, 官方接口支持 `1024x1024`、`1024x1536`、`1536x1024` 或 `auto`
- `AI_PAINTING_OPENAI_IMAGE_QUALITY`: OpenAI 官方图片质量, 默认 `auto`
- `AI_PAINTING_OPENAI_IMAGE_OUTPUT_FORMAT`: OpenAI 官方图片输出格式, 默认 `png`

本地 ASR HTTP 服务约定:

- 请求方式: `POST`
- 请求体: `multipart/form-data`
- 文件字段: `file`
- 语种字段: `language`
- 响应: JSON 中包含 `text`、`transcript` 或 `content`, 也可以直接返回纯文本

本地 ASR 命令模板示例:

```powershell
$env:AI_PAINTING_LOCAL_ASR_COMMAND='python E:\tools\local_asr.py --audio "{audio}" --language "{language}"'
```

命令模板只建议在可信本机开发环境使用。可用占位符包括 `{audio}`、`{language}`、`{workdir}`。后端会校验 `language` 只包含字母、数字、下划线或连字符, 并且不会通过 shell 执行命令模板, 因此不要在模板里依赖重定向、管道等 shell 语法。

本地 Qwen3-ASR 备用服务详见 [docs/local-asr-qwen3.md](docs/local-asr-qwen3.md)。

Docker 备用部署方案详见 [docs/docker-deploy.md](docs/docker-deploy.md)。本机开发仍默认使用 `快速启动.bat`, 不要求 Docker。

语音识别优先级:

1. 后端小米 MiMo ASR
2. 后端本地 ASR
3. 前端 Web Speech API

默认情况下, 如果 `.env` 中配置了 `MIMO_API_KEY` 且 `AI_PAINTING_ASR_PROVIDERS` 为 `xiaomi,local`, 应用会优先使用小米 ASR。前端会在控制台状态中显示当前语音识别 Provider。

前端语音切分参数:

1. 麦克风输入会先用简单 RMS 能量阈值判断是否开始收音
2. 检测到说话后, 静音超过 `1.5s` 会截断并提交给后端 ASR
3. 单次语音最长保留 `30s`, 超过后会强制截断提交
4. 单次有效语音至少需要约 `480ms`, 用于过滤很短的环境噪声

延迟指标:

1. 后端 ASR 响应会返回识别总耗时、音频大小、Provider 尝试次数和成功 Provider
2. 命令执行响应会返回规则解析、Agent 规划、绘图执行和命令总耗时
3. 前端控制台会显示最近一次 ASR、规划、执行和端到端耗时
4. 后端会把命令延迟指标写入 `voice_command_logs.latency_json`, 方便后续做统计看板
5. Agent 规划会写入 `agent_planner_ms`, 同时保留旧 `llm_planner_ms` 兼容历史日志和前端
6. `GET /api/metrics/latency` 会返回最近语音命令的平均值、P50、P75、P95 和最大耗时
7. `backend\evaluate_asr_samples.py` 可按音频清单批量评测后端 ASR Provider, 输出 CER、成功率和延迟统计

ASR 样本评测脚手架详见 [docs/evaluation/asr-benchmark.md](docs/evaluation/asr-benchmark.md)。

复杂任务规划:

1. 后端先使用本地规则解析器处理常见指令
2. 当规则解析不足且启用 Agent 时, 进入 Drawing Agent Planner
3. LangGraph 会编排 classify、build SceneGraph、repair、validate、repair_with_model 和 compile
4. Agent 先生成 SceneGraph v2, 再由编译器转换成受控 `CommandPlan`
5. 模型输出校验失败时, 后端会带着校验错误尝试一次模型修复
6. 后端会校验对象类型、操作类型、对象数量和风险等级, 校验通过后才交给绘图引擎执行
7. 多主体场景或全局改造指令在规则层会先返回追问, 避免把复杂描述误执行成单个对象
8. Agent 规划失败时回退到规则解析结果, 不阻断基础绘图路径
9. 当前已落地本地客厅场景、流程图、信息图、海报、UI 草图、组织结构图和甘特图 Agent 模板, 后续会扩展到泳道图和更开放的领域路由

Drawing Agent 架构详见 [docs/agent-architecture.md](docs/agent-architecture.md)。

渲染策略路由:

1. 结构精确类图形默认走程序生成, 包括甘特图、泳道图、流程图、UML 图、ER 图、系统架构图、组织结构图、普通小房子、草地、太阳、树、简单场景组合、海报草稿版式和手抄报草稿版式
2. 这类图会优先输出结构化 JSON、SceneGraph、SVG 对象或后续 Mermaid / HTML 渲染结果, 保证文字清晰、关系线稳定、位置可控并可继续语音编辑
3. 艺术表现类图形默认走生图模型, 包括水墨画、二次元动漫人物、写实插画、概念场景图、复杂艺术海报、商业视觉图、儿童插画、国风插画和科幻场景
4. “精修图片”“丰富当前画面”“风格转换”会走图生图精修, 使用当前画布截图和提示词一起生成覆盖式图片层
5. 规则层已加入 `render_strategy` 分类, 防止“复杂艺术海报”被本地海报模板误抢, 也防止“泳道图/UML/ER”误走生图模型

文字转图片:

1. “生成一张人物肖像画”会生成 `generate_image_asset` 计划
2. 后端执行前会把该计划解析为 `image` 绘图对象
3. 默认 `placeholder` Provider 只生成可渲染占位图, 用于验证画布链路
4. 配置 `AI_PAINTING_IMAGE_PROVIDER=http` 和 `AI_PAINTING_TEXT_IMAGE_URL` 后, 后端会调用外部文字转图片服务
5. 配置 `AI_PAINTING_IMAGE_PROVIDER=openai_compatible` 后, 后端会优先调用中转站 `{AI_PAINTING_TEXT_IMAGE_BASE_URL}/images/generations`
6. 如果中转站失败且配置了 `AI_PAINTING_OPENAI_API_KEY` 或 `OPENAI_API_KEY`, 后端会备用调用 OpenAI 官方 `/images/generations`
7. HTTP 服务可以返回图片二进制, 也可以返回包含 `image_data_url`、`data_url`、`url`、`image_url` 或 `b64_json` 的 JSON
8. 生成图片作为普通画布对象保存, 可以继续用语音移动、缩放、撤销和删除

图生图精修:

1. “精修我的图片”“丰富当前画面”“把当前作品风格化”会生成 `polish_image_asset` 计划
2. 前端会把当前 SVG 画布转成 PNG data URL, 和用户提示词一起提交到后端
3. 后端使用 `AI_PAINTING_IMAGE_EDIT_PROVIDER` 选择 Provider
4. 配置 `openai_compatible` 后, 后端会优先调用中转站 `{AI_PAINTING_IMAGE_EDIT_BASE_URL}/images/edits`
5. 如果中转站失败且配置了 `AI_PAINTING_OPENAI_API_KEY` 或 `OPENAI_API_KEY`, 后端会备用调用 OpenAI 官方 `/images/edits`
6. 官方 OpenAI 图片接口默认使用 `AI_PAINTING_OPENAI_IMAGE_SIZE=auto`, 避免把中转站可用但官方不支持的 `1024x768` 直接传给官方接口
7. 返回图片会作为覆盖整张画布的 `image` 对象加入作品, 原始矢量对象仍保留在下层
8. 用户可以用“撤销”移除精修图, 回到可编辑源画布

## 项目结构

```txt
.
├── backend
│   ├── app
│   │   ├── agent
│   │   ├── asr.py
│   │   ├── command_parser.py
│   │   ├── database.py
│   │   ├── drawing_engine.py
│   │   ├── image_generation.py
│   │   ├── main.py
│   │   ├── repositories.py
│   │   └── schemas.py
│   ├── local_asr_qwen3.py
│   ├── Dockerfile
│   ├── evaluate_asr_samples.py
│   ├── requirements-local-asr.txt
│   ├── requirements.txt
│   └── tests
├── frontend
│   ├── src
│   │   ├── drawing
│   │   ├── hooks
│   │   ├── utils
│   │   ├── App.tsx
│   │   ├── api.ts
│   │   ├── main.tsx
│   │   └── types.ts
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── docs
│   ├── archive
│   ├── evaluation
│   ├── status
│   └── superpowers
├── .env.example
├── README.md
├── ROADMAP.md
├── docker-compose.yml
├── 快速启动.bat
├── 设计文档.md
└── 需求文档.md
```

## 常见问题

### 浏览器提示不支持语音识别

当前语音识别优先使用后端 ASR。未配置 `MIMO_API_KEY`、本地 ASR 也不可用时, 前端会降级到 Web Speech API。部分浏览器不支持 Web Speech API, 或需要 HTTPS、浏览器权限、系统麦克风权限。

### 页面打开后没有开始监听

浏览器可能要求用户先完成麦克风授权, 也可能限制页面自动启动录音或语音识别。这属于浏览器安全限制, 不是绘图功能缺失。配置小米或本地 ASR 时, 浏览器仍需要麦克风权限来采集音频。

### 为什么没有鼠标绘图工具栏

本项目目标是纯语音控制绘图。当前前端只展示画布、语音状态、识别文本、执行状态和操作历史。顶部 icon 按钮只用于监听控制和导出, 不提供鼠标拖拽或键盘快捷绘图入口。

### PNG 导出在哪里完成

后端负责解析导出指令并记录日志, 前端负责把当前 SVG 画布转换为 PNG 并触发下载。这样可以避免后端引入额外图像渲染依赖。

### 为什么复杂指令执行更快

后端会把多步骤语音指令作为一个计划执行。计划执行时只清理一次 redo 栈, 并在所有步骤成功后统一提交 SQLite 事务。如果任一步失败, 会回滚整次计划, 避免画布进入半完成状态。

### 清空画布为什么要二次确认

“清空画布”会删除当前作品的全部对象, 后端会先返回确认提示并记录待确认日志。继续说“确认清空”才会真正执行清空, 同时写入操作历史和语音日志；之后仍可用“撤销”恢复对象, 用“恢复”再次清空。
