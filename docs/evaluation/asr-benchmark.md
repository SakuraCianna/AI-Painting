# ASR 样本评测脚手架

> 状态: 已提供仓库脚手架, 尚未内置真实音频样本

## 目标

本脚手架用于量化小米 MiMo ASR、本地 Qwen3-ASR 和其他本地 ASR Provider 的稳定性。它不会替代真实验收, 只负责把“音频 -> 转写 -> 字错误率 -> 延迟”流程标准化。

当前输出指标:

- 样本总数
- 成功数和失败数
- 完全匹配数
- 平均 CER
- P75/P95 CER
- 平均延迟
- P75/P95 延迟
- Provider 命中分布
- readiness gate: 默认要求成功率不低于 95%, 平均 CER 不高于 5%, P75 延迟不超过 1500ms

## 样本清单

参考文件:

```txt
docs\evaluation\asr-samples.example.json
```

字段说明:

- `id`: 样本 ID
- `audio_path`: 音频文件路径, 相对路径按清单文件所在目录解析
- `expected_text`: 期望转写文本
- `language`: 语种, 默认 `zh`
- `notes`: 可选说明

当前支持 `wav`、`mp3` 音频。仓库不提交真实录音, 真实样本建议放在本机未跟踪目录或专用数据仓库。

## 运行方式

评测小米 ASR:

```powershell
$env:AI_PAINTING_ASR_PROVIDERS="xiaomi"
.\.venv\Scripts\python.exe backend\evaluate_asr_samples.py docs\evaluation\asr-samples.example.json --output reports\asr-xiaomi.json
```

评测本地 ASR:

```powershell
$env:AI_PAINTING_ASR_PROVIDERS="local"
$env:AI_PAINTING_LOCAL_ASR_URL="http://127.0.0.1:9001/asr"
.\.venv\Scripts\python.exe backend\evaluate_asr_samples.py docs\evaluation\asr-samples.example.json --output reports\asr-local.json
```

临时覆盖 Provider 顺序:

```powershell
.\.venv\Scripts\python.exe backend\evaluate_asr_samples.py docs\evaluation\asr-samples.example.json --providers "xiaomi,local"
```

## 输出说明

输出 JSON 包含:

- `provider_status`: 当前后端可用 ASR Provider
- `summary`: 汇总指标和 `readiness_gate`
- `results`: 每条样本的转写文本、延迟、Provider、尝试记录和 CER

## 已验证

- manifest 加载
- 相对路径解析
- 文本规范化
- CER 计算
- 汇总统计
- readiness gate 判定

## 未验证

- 小米 ASR 真实账号调用
- Qwen3-ASR 本地模型真实转写
- 噪声、方言、远场麦克风和长句样本表现
