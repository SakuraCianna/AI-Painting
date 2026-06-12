# 发现与决策

## 需求
- 用户希望项目逐步扩展到产品级和商业可用程度。
- 核心约束仍然是用户不能使用鼠标或键盘, 只能通过语音完成绘图创作。
- 长期路线图需要同时考虑指令理解准确性、容错性、语音到绘图响应延迟、复杂指令拆解与执行能力。

## 研究发现
- Figma AI 的公开帮助文档强调 AI 应该帮助用户更快开始、查找团队资产、替换内容、增加交互、重命名图层、处理文本、生成和编辑图片, 同时明确提示 AI 输出可能错误, 需要用户判断。
- Canva AI 2.0 的公开页面强调把 AI 设计变成可编辑布局、在编辑器里生成元素、通过提示生成模板、保持风格一致。这说明商业设计工具的核心不是只给一张成品图, 而是把生成结果放回可编辑工作流。
- OpenAI Images API 官方文档显示图像生成可以通过 Images API 或 Responses API 调用, 并支持流式图像生成与图像输入编辑。这适合作为后续“语音生成背景/素材图层”的候选能力。
- tldraw SDK 官方文档强调生产级无限画布需要高性能画布、持久化、撤销恢复、跨标签页同步、自定义形状、选择变换、多人协作、可访问性、布局组合和数据管理。这些能力可以作为 AI Painting 画布底座长期目标参考。
- OpenAI Realtime 文档强调实时转写适合需要流式音频和实时 transcript delta 的场景, 并且低延迟与准确性之间需要根据真实音频、目标语言、口音和领域词表测试后权衡。这对后续语音绘图延迟优化很关键。
- MDN SpeechRecognition 文档显示 Web Speech API 的 SpeechRecognition 不是 Baseline, 一些主流浏览器不可用, 某些浏览器还会把音频发送到服务端识别。因此它适合做最终兜底, 不适合作为商业可用默认 ASR。
- Mermaid 说明文本化定义可以生成和修改复杂图表, 这对“语音画流程图、架构图、关系图”有启发: 可以让 LLM 先生成中间图表 DSL, 再渲染为结构化画布对象。
- Excalidraw 的开源仓库强调无限画布、手绘风格、图片支持、形状库、多语言、PNG/SVG/剪贴板导出、开放 JSON 格式、箭头绑定、撤销恢复、缩放平移、PWA、实时协作和本地优先。这些可以作为白板类产品基线能力。

## 技术决策
| 决策 | 理由 |
|------|------|
| 保持矢量绘图为主路径 | 可编辑、可撤销、低延迟, 更符合纯语音工具定位 |
| 生图能力作为图片图层和素材生成 | 适合复杂视觉和风格化背景, 但不适合替代结构化绘图对象 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 复杂图形目前只能由基础形状硬拆 | 需要扩展 group、path、layer、transform、semantic_tag 等对象模型 |

## 资源
- Figma AI Help: https://help.figma.com/hc/en-us/articles/23870272542231-Use-AI-tools-in-Figma-Design
- Canva AI: https://www.canva.com/canva-ai/
- OpenAI Image Generation: https://developers.openai.com/api/docs/guides/image-generation
- tldraw SDK: https://tldraw.dev/
- OpenAI Realtime and Audio: https://developers.openai.com/api/docs/guides/realtime
- MDN SpeechRecognition: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
- Mermaid: https://mermaid.js.org/
- Excalidraw GitHub: https://github.com/excalidraw/excalidraw

## 视觉/浏览器发现
- 待补充。

---
*每执行2次查看/浏览器/搜索操作后更新此文件*
*防止视觉信息丢失*
