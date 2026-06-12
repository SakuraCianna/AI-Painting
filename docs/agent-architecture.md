# Drawing Agent 架构设计

> 当前长期目标: 将 AI Painting 从“规则解析 + LLM 兜底”升级为“Drawing Agent + SceneGraph v2 + 工具执行器”的纯语音绘图系统。

## 1. 目标

Drawing Agent 负责把用户语音转写后的自然语言拆成可验证、可执行、可撤销的绘图计划。它不是绕过现有绘图引擎, 而是把现有能力包装成工具, 让复杂指令可以跨领域扩展。

核心目标:

- 保持简单指令的低延迟规则路径
- 用 Agent 接管复杂场景、跨对象编辑和多领域绘图
- 让模型先输出 SceneGraph v2, 再由编译器生成 `CommandPlan`
- 所有最终状态变更仍通过 `drawing_engine`、SQLite 历史和语音日志
- 复杂计划必须可校验、可回退、可追问

## 2. 当前架构

```txt
用户语音
↓
ASR
↓
规则解析器
↓
Drawing Agent Planner
├─ Intent / Domain Routing
├─ SceneGraph v2 生成
├─ Pydantic 校验
├─ SceneGraph Compiler
└─ Tool / Operation Router
↓
CommandPlan
↓
drawing_engine
↓
SVG 画布 / 图片对象 / 导出 / TTS 反馈
```

## 3. 为什么不是直接让模型输出底层操作

直接让模型输出 `add_object`、`move_many` 这类底层操作会让复杂场景变得不稳定。模型容易遗漏对象、坐标越界、语义标签不一致, 或把高风险操作直接执行。

新架构让模型优先输出 SceneGraph:

- `objects`: 场景对象, 例如沙发、茶几、窗户、灯
- `relations`: 空间关系, 例如茶几在沙发前方
- `style`: 颜色、描边、透明度
- `domain`: 当前绘图领域, 例如 `interior_vector_scene`
- `risk_level`: 风险等级
- `requires_confirmation`: 是否需要用户确认

之后由编译器把 SceneGraph 转为项目已有的 `CommandPlan`。这样模型负责语义, 编译器负责工程约束。

## 4. 已落地模块

- `backend/app/agent/scene_graph.py`: SceneGraph v2 Pydantic schema
- `backend/app/agent/compiler.py`: SceneGraph 到 `CommandPlan` 的编译器
- `backend/app/agent/planner.py`: Drawing Agent Planner, 包含本地模板、MiMo SceneGraph 规划和可选 LangGraph runtime
- `backend/app/main.py`: 已切换到 Drawing Agent, 不再引用旧 `llm_planner.py`
- `docs/evaluation/complex_voice_commands.json`: 新增 `agent` tier 复杂用例

## 5. LangGraph 角色

`langgraph` 已作为后端依赖加入。当前第一阶段以轻量方式接入:

- 如果本地安装了 `langgraph`, Agent 编译节点会通过 `StateGraph` 执行
- 如果不可用, 自动回退到同步编译路径
- 简单规则路径不依赖 LangGraph, 保证基础绘图速度和稳定性

后续会把 Agent 拆为更完整的 LangGraph 节点:

1. `classify_intent`
2. `build_scene_graph`
3. `validate_scene_graph`
4. `repair_scene_graph`
5. `compile_operations`
6. `ask_confirmation`
7. `execute_tools`

## 6. 输出速度策略

- 简单命令继续走规则解析, 不调用模型
- 已知复杂模板先用本地 Agent 模板, 例如客厅场景
- 只有规则无法稳定拆解且启用 Agent 时才调用 MiMo
- Agent 输出限制对象数量和操作数量
- 规划、执行和端到端耗时继续写入 `voice_command_logs.latency_json`

## 7. 输出质量策略

- SceneGraph 使用 Pydantic schema 校验
- 编译器只允许项目支持的对象类型和操作类型
- 复杂计划必须带语义标签、分组和图层
- 高风险操作必须走确认链
- 计划失败时回退规则结果, 不阻断基础绘图
- 复杂评测集分为 `rules`、`agent` 和 `planner_expected`

## 8. 下一阶段

- 增加 50 到 100 条复杂语音评测集
- 扩展领域工具: 室内、人物、流程图、信息图、海报、UI 草图
- 增加 SceneGraph repair 节点
- 增加组级移动、缩放、撤销和局部重绘
- 引入 Mermaid / PlantUML 执行器
- 引入 Canvas 或 OffscreenCanvas 作为滤镜、笔刷和大图导出增强层
