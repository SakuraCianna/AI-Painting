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
Render Strategy Router
↓
规则解析器
↓
Drawing Agent Planner
├─ Intent / Domain Routing
├─ SceneGraph v2 生成
├─ SceneGraph Repair
├─ SceneGraph Validation
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
- `backend/app/agent/validator.py`: SceneGraph repair 与约束校验
- `backend/app/agent/graph.py`: LangGraph 节点编排, 包含 classify、build、repair、validate、repair_with_model、compile
- `backend/app/agent/compiler.py`: SceneGraph 到 `CommandPlan` 的编译器
- `backend/app/agent/edit_planner.py`: 语义编辑计划器, 将“把沙发改成绿色并向右移动一点”“把屋顶下面的门改成绿色”“把靠近门的那棵树改成黄色”“把卡片里和标题同一行的按钮改成绿色”拆成 `set_style_many`、`move_many` 等受控操作
- `backend/app/repositories.py`: 对象查询 DSL 执行层, 支持排序选择、相对位置、靠近关系、遮挡关系、包含关系、同一行/同一列、层级前后、关系链组合、颜色温度、小物件筛选和组级扩展
- `backend/app/agent/model_client.py`: MiMo SceneGraph 生成与模型修复客户端
- `backend/app/agent/planner.py`: Drawing Agent Planner, 负责启用条件、本地模板、语义编辑模板、流程图模板、系统架构图模板、自定义实体和关系的 ER 图模板、自定义泳道和节点的泳道图模板、信息图模板、海报模板、UI 草图模板、自定义角色组织结构图模板、甘特图模板和 Graph 调度
- `backend/app/render_strategy.py`: 渲染策略分类器, 区分程序生成、生图模型和图生图精修
- `backend/app/image_generation.py`: 图片生成和图生图精修 Provider 适配层, 会把 `source_prompt`、`target_subject`、`target_region` 和 `adjustment` 写入精修结果元数据
- `backend/app/image_evaluation.py`: 图片 Provider 评测汇总和 readiness gate, 记录文生图/图生图成功率、延迟、Provider 分布和尺寸分布
- `backend/app/main.py`: 已切换到 Drawing Agent, 不再引用旧 `llm_planner.py`
- `docs/evaluation/complex_voice_commands.json`: 新增 `agent` tier 复杂用例

## 5. LangGraph 角色

`langgraph` 已作为后端依赖加入。当前已接入明确的 StateGraph 节点:

- `classify_intent`
- `build_scene_graph`
- `repair_scene_graph`
- `validate_scene_graph`
- `repair_with_model`
- `compile_plan`

如果运行环境不可用或 LangGraph 节点执行失败, 会自动回退到同步 repair、validate、compile 路径。
- 简单规则路径不依赖 LangGraph, 保证基础绘图速度和稳定性

当前阶段使用 LangGraph + Pydantic schema + 受控模型客户端落地 LangChain 风格的结构化输出链路。完整 `langchain` / `langchain-openai` 依赖尚未加入, 后续会在确认版本和中转站兼容性后再接入官方 structured output 封装。

后续会继续扩展:

1. 更细粒度的领域路由
2. Mermaid / PlantUML 结构图执行器
3. 海报、信息图和 UI 草图工具执行器
4. `ask_confirmation` 条件分支
5. `execute_tools` 工具路由

## 6. 输出速度策略

- 简单命令继续走规则解析, 不调用模型
- 结构精确类图形优先走程序生成, 艺术表现类图形优先走生图模型, 精修类指令优先走图生图, 其中“把右边那个人的眼睛调亮”这类图片内主体追改会作为图生图目标元数据处理
- 已知复杂模板先用本地 Agent 模板, 例如客厅场景、语音绘图流程图、系统架构图、用户订单 ER 图、图书馆借阅自定义 ER 图、自定义泳道和节点的泳道图、销售增长信息图、新品发布海报、产品 UI 草图、自定义角色的产品团队组织结构图和项目排期甘特图
- 已知语义编辑先用本地 Agent 编辑计划, 例如改沙发颜色并移动、改流程图节点颜色并加粗箭头、编辑屋顶下面的门、靠近门的树、挡住标题的图片、卡片里的文字、卡片里和标题同一行的按钮或暖色小物件
- 只有规则无法稳定拆解且启用 Agent 时才调用 MiMo
- 模型输出校验失败时, Graph 会先尝试一次模型修复, 再进入编译
- Agent 输出限制对象数量和操作数量
- 规划、执行和端到端耗时继续写入 `voice_command_logs.latency_json`, 新增 `agent_planner_ms` 并保留旧 `llm_planner_ms` 兼容字段

## 7. 输出质量策略

- SceneGraph 使用 Pydantic schema 校验
- Repair 节点会修复坐标越界、无效图层、无效关系和高风险确认标记
- Repair with model 节点会把校验错误和当前 SceneGraph 发回模型, 要求保留意图并修复为可编译结构
- 编译器只允许项目支持的对象类型和操作类型
- 复杂计划必须带语义标签、分组和图层
- 高风险操作必须走确认链
- 计划失败时回退规则结果, 不阻断基础绘图
- 复杂评测集分为 `rules`、`agent` 和 `planner_expected`

## 8. 下一阶段

- 用真实 ASR transcript 和图片 Provider 样本持续回归 100 条复杂语音评测集, 不再只看规则文本样本
- 扩展领域工具: 室内、人物、泳道图、看板图、UML、Mermaid / PlantUML 和海报版式
- 将当前本地流程图模板升级为 Mermaid / PlantUML 结构图执行器
- 强化模型驱动的 SceneGraph repair 节点, 让模型修复只在 schema 校验失败时触发
- 完善编组编辑, 例如取消编组、组内排序、组级局部重绘和命名历史
- 扩展更细的语义关系选择, 例如组内相邻对象、最近对象、路径附近对象和跨领域关系模板
- 引入 Canvas 或 OffscreenCanvas 作为滤镜、笔刷和大图导出增强层, 但继续保留 SVG 作为可编辑主图层
