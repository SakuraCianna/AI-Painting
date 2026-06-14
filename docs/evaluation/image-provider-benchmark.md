# 图片 Provider 评测脚手架

> 状态: 已提供仓库脚手架, 尚未内置真实图片质量评测样本

## 目标

本脚手架用于把 GPT-image-2 中转站、OpenAI 官方备用 Provider 和占位 Provider 的调用稳定性标准化。它主要衡量:

- 请求是否成功
- 使用了哪个 Provider
- 返回的是 data URL 还是远程 URL
- 输出尺寸是否符合预期
- 单次请求延迟
- readiness gate 是否通过

它暂时不自动判断图片美观度、文本准确性、局部精修是否真的只改了指定区域。这些需要人工标注或后续接入视觉评测模型。

## 样本清单

参考文件:

```txt
docs\evaluation\image-provider-samples.example.json
```

字段说明:

- `id`: 样本 ID
- `task`: `text_to_image` 或 `image_edit`
- `prompt`: 图片生成或精修提示词
- `width`: 期望宽度
- `height`: 期望高度
- `input_image_data_url`: 图生图精修输入图, 仅 `image_edit` 需要
- `source_prompt`: 源图原始提示词, 可选
- `notes`: 可选说明

真实评测建议复制示例文件到 `reports` 或本机未跟踪目录, 不要把真实用户图片、密钥或敏感样本提交到仓库。

## 运行方式

评测当前 `.env` 中配置的 Provider:

```powershell
.\.venv\Scripts\python.exe backend\evaluate_image_provider.py docs\evaluation\image-provider-samples.example.json --output reports\image-provider.json
```

只评测占位 Provider:

```powershell
.\.venv\Scripts\python.exe backend\evaluate_image_provider.py docs\evaluation\image-provider-samples.example.json --text-provider placeholder --edit-provider placeholder --output reports\image-placeholder.json
```

评测中转站优先链路:

```powershell
$env:AI_PAINTING_IMAGE_PROVIDER="openai_compatible"
$env:AI_PAINTING_IMAGE_EDIT_PROVIDER="openai_compatible"
.\.venv\Scripts\python.exe backend\evaluate_image_provider.py docs\evaluation\image-provider-samples.example.json --output reports\image-gpt-image-2-proxy.json
```

## 输出说明

输出 JSON 包含:

- `provider_config`: 本次运行的图片 Provider 和模型配置摘要
- `summary`: 成功率、平均延迟、P50/P75/P95 延迟、Provider 命中分布、任务分布和 readiness gate
- `results`: 每条样本的状态、Provider、尺寸、source 类型、source 长度和错误信息

默认 readiness gate:

- 成功率不低于 90%
- P75 延迟不超过 30000ms

## 已验证

- manifest 加载和字段校验
- 文生图与图生图任务分类
- 成功率、Provider 分布、尺寸分布和延迟汇总
- readiness gate 判定
- 占位 Provider 可跑通完整报告

## 未验证

- GPT-image-2 中转站真实质量
- OpenAI 官方备用 Provider 真实质量
- 生成图片的美观度、文本清晰度和内容安全
- 图生图精修是否能稳定保留主体并只修改目标区域
- 长图、竖图、真实大画布截图和多轮追改的真实表现
