# AI Painting

AI Painting 是一款纯语音控制的绘图工具原型。用户在应用内不通过鼠标或键盘绘图, 而是通过中文语音指令创建画布、绘制图形、修改样式、撤销恢复、保存作品和导出图片。

## 功能特性

- 语音识别文本到绘图操作的解析闭环
- 支持创建画布、绘制基础图形、修改最近对象样式、移动对象、撤销和恢复
- 支持“画一个房子, 红色屋顶, 蓝色门, 两扇窗户”这类复杂指令拆解
- 支持“画三颗黄色星星, 从左到右变小”这类批量绘制指令
- 支持“把所有蓝色图形改成绿色, 然后整体向上移动一点”这类批量编辑指令
- 支持最近对象缩放, 例如“把它放大一倍”
- 支持对象命名、图层元数据和语义标签, 例如“画一个黄色圆形, 命名为太阳, 放到前景层”
- 支持按语义标签批量编辑, 例如“把房子的窗户都变大”
- 支持多边形、路径和贝塞尔曲线, 例如“画一个绿色五边形”“画一条弯曲小路”
- 提供复杂语音指令评测集, 区分规则已支持用例和后续规划器用例
- 支持低置信度追问, 多主体场景不会被规则解析器误执行为半成品
- 支持小米 MiMo ASR、本地 ASR、Web Speech API 三层语音识别降级
- 支持小米 MiMo-v2.5-Pro 作为复杂绘图指令规划兜底
- 支持执行计划来源、解释文本、ScenePlan 步骤展示和小米 MiMo TTS 语音反馈
- 语音输入需要手动点击麦克风开始, 页面加载后不会自动录音
- 使用 SVG 渲染画布对象
- 使用 SQLite 保存作品、绘图对象、操作历史、作品版本和语音指令日志
- 绘图对象已支持 `layer_id`、`group_id`、`semantic_tags` 和 `transform` 元数据
- 前端工作台不提供鼠标拖拽绘图或键盘快捷绘图入口

## 产品路线图

长期目标和产品级扩展计划见 [ROADMAP.md](ROADMAP.md)。

## 技术栈

- Python 3.12.10
- FastAPI
- SQLite
- pytest
- React
- TypeScript
- Vite
- Web Audio API
- Web Speech API
- Xiaomi MiMo ASR
- Xiaomi MiMo-v2.5-Pro
- Xiaomi MiMo TTS
- Iconify

## 环境要求

- Windows 11
- PowerShell 7
- Python 3.12.10
- Node.js 和 npm
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

## 本地开发

快速启动前后端:

```powershell
.\快速启动.bat
```

脚本固定使用后端 `8080` 和前端 `5173`, 并打开前端地址。如果端口被占用, 对应服务会启动失败, 需要先关闭占用端口的进程。

启动后端:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080 --reload
```

启动前端:

```powershell
npm run dev --prefix frontend
```

默认访问地址:

```txt
http://127.0.0.1:5173
```

默认后端地址:

```txt
http://127.0.0.1:8080
```

## 构建命令

```powershell
npm run build --prefix frontend
```

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

当前项目不要求必须配置 `.env` 文件。

可选环境变量:

```powershell
$env:AI_PAINTING_DB="E:\CodeHome\AI Painting\backend\data\ai_painting.sqlite3"
$env:VITE_API_BASE_URL="http://127.0.0.1:8080"
$env:MIMO_API_KEY="<你的 Xiaomi MiMo API Key>"
$env:AI_PAINTING_ASR_PROVIDERS="xiaomi,local"
$env:AI_PAINTING_ASR_LANGUAGE="zh"
$env:AI_PAINTING_LOCAL_ASR_URL="http://127.0.0.1:9001/asr"
$env:AI_PAINTING_ENABLE_LLM_PLANNER="true"
$env:AI_PAINTING_MIMO_LLM_MODEL="mimo-v2.5-pro"
$env:AI_PAINTING_MIMO_TTS_MODEL="mimo-v2-tts"
$env:AI_PAINTING_MIMO_TTS_VOICE="default_zh"
$env:AI_PAINTING_MIMO_TTS_STYLE="自然 清晰"
```

说明:

- `AI_PAINTING_DB`: 后端 SQLite 数据库路径, 未设置时默认使用 `backend\data\ai_painting.sqlite3`
- `VITE_API_BASE_URL`: 前端请求后端 API 的地址, 未设置时默认使用 `http://127.0.0.1:8080`
- `MIMO_API_KEY`: 小米 MiMo API Key, 配置后后端会优先调用 `mimo-v2.5-asr`
- `AI_PAINTING_ASR_PROVIDERS`: 后端 ASR Provider 顺序, 默认是 `xiaomi,local`
- `AI_PAINTING_ASR_LANGUAGE`: 后端 ASR 语种, 默认是 `zh`, 小米接口也支持 `auto` 和 `en`
- `AI_PAINTING_LOCAL_ASR_URL`: 本地 ASR HTTP 服务地址, 作为小米 ASR 后的第一备用方案
- `AI_PAINTING_LOCAL_ASR_COMMAND`: 本地 ASR 命令模板, 作为本地 HTTP 服务的替代方案, 命令需要把识别文本输出到 stdout
- `AI_PAINTING_ENABLE_LLM_PLANNER`: 是否启用小米 MiMo 复杂指令规划, 可选值为 `true` 或 `false`
- `AI_PAINTING_MIMO_LLM_MODEL`: 复杂指令规划模型, 默认是 `mimo-v2.5-pro`
- `AI_PAINTING_MIMO_TTS_MODEL`: 小米语音合成模型, 默认是 `mimo-v2-tts`
- `AI_PAINTING_MIMO_TTS_VOICE`: 小米语音合成音色, 默认是 `default_zh`
- `AI_PAINTING_MIMO_TTS_STYLE`: 小米语音合成风格, 默认可不设置

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

命令模板只建议在可信本机开发环境使用。可用占位符包括 `{audio}`、`{language}`、`{workdir}`。

语音识别优先级:

1. 后端小米 MiMo ASR
2. 后端本地 ASR
3. 前端 Web Speech API

默认情况下, 如果 `.env` 中配置了 `MIMO_API_KEY` 且 `AI_PAINTING_ASR_PROVIDERS` 为 `xiaomi,local`, 应用会优先使用小米 ASR。前端会在控制台状态中显示当前语音识别 Provider。

复杂任务规划:

1. 后端先使用本地规则解析器处理常见指令
2. 当规则解析置信度低, 或复杂连接词导致规则解析不足时, 调用小米 MiMo-v2.5-Pro 生成受控 JSON 操作计划
3. 后端会校验操作类型和对象类型, 校验通过后才交给绘图引擎执行
4. 多主体场景或全局改造指令在规则层会先返回追问, 避免把复杂描述误执行成单个对象
5. MiMo 规划失败时回退到规则解析结果, 不阻断基础绘图路径

## 项目结构

```txt
.
├── backend
│   ├── app
│   │   ├── asr.py
│   │   ├── command_parser.py
│   │   ├── database.py
│   │   ├── drawing_engine.py
│   │   ├── main.py
│   │   ├── repositories.py
│   │   └── schemas.py
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
│   └── package.json
├── docs
│   ├── evaluation
│   └── superpowers
├── README.md
├── ROADMAP.md
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
