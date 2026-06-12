# Windows 11 本地 Qwen3-ASR 备用方案

## 目标

AI Painting 的 ASR 优先级是:

1. 小米 MiMo ASR
2. 本地 ASR
3. Web Speech API

本方案把本地 ASR 落地为独立 HTTP 服务, 默认使用 Hugging Face 模型 `Qwen/Qwen3-ASR-0.6B`, 通过项目现有 `AI_PAINTING_LOCAL_ASR_URL` 接入主后端。

## 选型

优先选择 `Qwen/Qwen3-ASR-0.6B`:

- 官方 Qwen3-ASR 系列包含 `0.6B` 和 `1.7B`
- 官方说明支持 30 种语言和 22 种中文方言
- `0.6B` 是更适合本机备用的轻量版本
- 官方提供 `qwen-asr` Python 包, 支持 transformers 后端

资料:

- Hugging Face: https://huggingface.co/Qwen/Qwen3-ASR-0.6B
- 官方仓库: https://github.com/QwenLM/Qwen3-ASR
- 技术报告: https://arxiv.org/abs/2601.21337

## 已落地文件

- `backend/local_asr_qwen3.py`: 本地 Qwen3-ASR HTTP 服务
- `backend/requirements-local-asr.txt`: 可选本地 ASR 依赖
- `backend/app/asr.py`: 主后端已有本地 ASR HTTP Provider, 本次补充本地 Provider label 配置
- `快速启动.bat`: 支持通过环境变量启动本地 ASR 服务

## 安装

先安装主项目依赖:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

安装 Qwen3-ASR 可选依赖:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-local-asr.txt
```

如果希望预下载模型到仓库外或 `backend\models` 下:

```powershell
.\.venv\Scripts\python.exe -m pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-ASR-0.6B --local-dir backend\models\Qwen3-ASR-0.6B
```

`backend\models` 已加入 `.gitignore`, 不会提交大模型权重。

## 单独启动本地 ASR 服务

```powershell
$env:QWEN3_ASR_MODEL="Qwen/Qwen3-ASR-0.6B"
$env:QWEN3_ASR_DEVICE="auto"
$env:QWEN3_ASR_DTYPE="auto"
.\.venv\Scripts\python.exe -m uvicorn local_asr_qwen3:app --app-dir backend --host 127.0.0.1 --port 9001
```

如果已经把模型下载到本地目录:

```powershell
$env:QWEN3_ASR_MODEL="backend\models\Qwen3-ASR-0.6B"
```

健康检查:

```powershell
curl http://127.0.0.1:9001/health
```

## 接入主后端

```powershell
$env:AI_PAINTING_ASR_PROVIDERS="xiaomi,local"
$env:AI_PAINTING_LOCAL_ASR_URL="http://127.0.0.1:9001/asr"
$env:AI_PAINTING_LOCAL_ASR_LABEL="Qwen3-ASR 本地服务"
```

主后端仍然使用原接口:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8080
```

## 快速启动脚本

默认:

```powershell
.\快速启动.bat
```

启用本地 ASR 服务:

```powershell
$env:AI_PAINTING_START_LOCAL_ASR="1"
.\快速启动.bat
```

首次自动安装本地 ASR 可选依赖:

```powershell
$env:AI_PAINTING_START_LOCAL_ASR="1"
$env:AI_PAINTING_INSTALL_LOCAL_ASR="1"
.\快速启动.bat
```

## API 约定

本地服务提供:

- `GET /health`
- `POST /asr`

`POST /asr` 请求:

- `multipart/form-data`
- `file`: 音频文件
- `language`: 默认 `zh`

响应示例:

```json
{
  "text": "画一个蓝色圆形",
  "transcript": "画一个蓝色圆形",
  "provider": "qwen3-asr",
  "model": "Qwen/Qwen3-ASR-0.6B",
  "language": "Chinese",
  "latency_ms": 1234.56
}
```

## 已验证

- 本地服务可在不加载模型的 mock 模式下启动和响应 `/health`
- `/asr` mock 转写路径已通过自动化测试
- 主后端仍可通过 `AI_PAINTING_LOCAL_ASR_URL` 识别本地 ASR Provider
- `快速启动.bat` 已具备启动本地 ASR 服务的命令链
- 后端测试和前端构建通过

## 未验证

- 未在本机真实下载 `Qwen/Qwen3-ASR-0.6B` 权重
- 未验证 Windows 11 + 当前显卡/CPU 的真实推理速度和显存/内存占用
- 未用真实麦克风音频跑 Qwen3-ASR 端到端识别
- 未验证 CUDA、PyTorch、FlashAttention 或 vLLM 加速组合
- 未验证方言、噪声、长音频和连续多轮语音指令的准确率

## 本地命令模板安全边界

`AI_PAINTING_LOCAL_ASR_COMMAND` 只建议在可信本机开发环境使用。后端会校验 `language` 只包含字母、数字、下划线或连字符, 并且不会通过 shell 执行命令模板。

命令模板应直接调用可执行程序:

```powershell
$env:AI_PAINTING_LOCAL_ASR_COMMAND='python E:\tools\local_asr.py --audio "{audio}" --language "{language}"'
```

不要依赖重定向、管道、`&&` 等 shell 语法。

## 建议验收顺序

1. 安装 `backend\requirements-local-asr.txt`
2. 启动 `local_asr_qwen3:app`
3. 用一段 1 到 3 秒中文 wav 测试 `/asr`
4. 设置 `AI_PAINTING_LOCAL_ASR_URL`
5. 关闭或移除 `MIMO_API_KEY`, 确认主后端能降级到本地 ASR
6. 在前端点击麦克风, 说“画一个蓝色圆形”, 检查识别文本和绘图结果
