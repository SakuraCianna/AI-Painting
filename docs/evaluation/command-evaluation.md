# 复杂命令评测集

> 状态: 已建立 52 条中文语音指令 reference seed, 尚未内置真实 ASR Provider 采集结果

## 文件

```txt
docs\evaluation\complex_voice_commands.json
docs\evaluation\complex_voice_command_asr_transcripts.json
```

## 覆盖范围

- 规则解析指令, 例如画布、房子、星星、路径、人物肖像、图片生成和图生图精修
- Drawing Agent 模板, 例如客厅、流程图、系统架构图、ER 图、信息图、海报、UI 草图、组织结构图、甘特图和泳道图
- 需要追问的复杂规划指令, 例如全局夜晚风格转换并保持局部形状
- ASR 转写文本种子, 用于后续对比小米、本地模型和 Web Speech API 的真实转写差异

## 自动化校验

后端测试会校验:

- 命令评测集数量保持在 50 到 100 条
- `rules`、`agent` 和 `planner_expected` 三类用例都存在
- 用例 ID 不重复
- ASR 转写伴随文件覆盖全部命令用例
- 规则层用例解析出的操作类型、对象类型、语义标签、目标区域和调整动作符合预期
- Agent 层用例通过本地 Drawing Agent 模板生成预期操作序列

运行方式:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m pytest backend\tests\test_command_evaluation.py -q
```

## 后续真实 ASR 采集

`complex_voice_command_asr_transcripts.json` 当前 `metadata.status` 是 `reference_seed`, 只表示仓库内的参考转写文本。真实采集时可以追加同一 `case_id` 的 `xiaomi`、`local` 或 `web_speech` 转写记录, 并把 `metadata.status` 更新为 `real_samples`。
