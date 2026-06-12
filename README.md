# AI Painting

AI Painting 是一款纯语音控制的绘图工具原型。用户在应用内不通过鼠标或键盘绘图, 而是通过中文语音指令创建画布、绘制图形、修改样式、撤销恢复、保存作品和导出图片。

## 功能特性

- 语音识别文本到绘图操作的解析闭环
- 支持创建画布、绘制基础图形、修改最近对象样式、移动对象、撤销和恢复
- 支持“画一个房子, 红色屋顶, 蓝色门, 两扇窗户”这类复杂指令拆解
- 支持“画三颗黄色星星, 从左到右变小”这类批量绘制指令
- 支持“把所有蓝色图形改成绿色, 然后整体向上移动一点”这类批量编辑指令
- 支持最近对象缩放, 例如“把它放大一倍”
- 支持执行计划展示和浏览器语音合成反馈
- 使用 SVG 渲染画布对象
- 使用 SQLite 保存作品、绘图对象、操作历史、作品版本和语音指令日志
- 前端工作台不提供鼠标拖拽绘图或键盘快捷绘图入口

## 技术栈

- Python 3.12.10
- FastAPI
- SQLite
- pytest
- React
- TypeScript
- Vite
- Web Speech API
- Iconify

## 环境要求

- Windows 11
- PowerShell 7
- Python 3.12.10
- Node.js 和 npm
- 支持 Web Speech API 的浏览器, 例如 Chromium 内核浏览器

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

启动后端:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

启动前端:

```powershell
npm run dev --prefix frontend
```

默认访问地址:

```txt
http://127.0.0.1:5173
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
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
```

说明:

- `AI_PAINTING_DB`: 后端 SQLite 数据库路径, 未设置时默认使用 `backend\data\ai_painting.sqlite3`
- `VITE_API_BASE_URL`: 前端请求后端 API 的地址, 未设置时默认使用 `http://127.0.0.1:8000`

## 项目结构

```txt
.
├── backend
│   ├── app
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
│   └── superpowers
├── README.md
├── 快速启动.bat
├── 设计文档.md
└── 需求文档.md
```

## 常见问题

### 浏览器提示不支持语音识别

当前原型使用浏览器 Web Speech API。部分浏览器不支持该能力, 或需要 HTTPS、浏览器权限、系统麦克风权限。后续可以接入后端 ASR 服务作为替代方案。

### 页面打开后没有开始监听

浏览器可能要求用户先完成麦克风授权, 也可能限制页面自动启动语音识别。这属于浏览器安全限制, 不是绘图功能缺失。

### 为什么没有鼠标绘图工具栏

本项目目标是纯语音控制绘图。当前前端只展示画布、语音状态、识别文本、执行状态和操作历史。顶部 icon 按钮只用于监听控制和导出, 不提供鼠标拖拽或键盘快捷绘图入口。

### PNG 导出在哪里完成

后端负责解析导出指令并记录日志, 前端负责把当前 SVG 画布转换为 PNG 并触发下载。这样可以避免后端引入额外图像渲染依赖。

### 为什么复杂指令执行更快

后端会把多步骤语音指令作为一个计划执行。计划执行时只清理一次 redo 栈, 并在所有步骤成功后统一提交 SQLite 事务。如果任一步失败, 会回滚整次计划, 避免画布进入半完成状态。
