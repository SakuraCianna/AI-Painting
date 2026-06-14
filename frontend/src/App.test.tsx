import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Artwork, AsrTranscriptionMetrics, CommandExecutionMetrics, CommandExecutionResponse, CommandPlan } from "./types";

const apiMocks = vi.hoisted(() => ({
  createArtwork: vi.fn(),
  submitVoiceCommand: vi.fn(),
  synthesizeSpeech: vi.fn(),
}));

const exportMocks = vi.hoisted(() => ({
  exportArtworkJson: vi.fn(),
  exportSvgAsPng: vi.fn(),
  exportSvgFile: vi.fn(),
  svgToPngDataUrl: vi.fn(),
}));

const voiceRuntime = vi.hoisted(() => ({
  onFinalTranscript: null as null | ((text: string, metrics: AsrTranscriptionMetrics | null) => void | Promise<void>),
  start: vi.fn(),
  stop: vi.fn(),
  state: {
    isSupported: true,
    isListening: false,
    interimTranscript: "",
    lastFinalTranscript: "",
    error: null as string | null,
    provider: "backend" as const,
    providerLabel: "小米 MiMo ASR",
    lastAsrMetrics: null as AsrTranscriptionMetrics | null,
  },
}));

vi.mock("./api", () => apiMocks);
vi.mock("./utils/exportPng", () => exportMocks);
vi.mock("./hooks/useVoiceRecognition", () => ({
  useVoiceRecognition: (options: { onFinalTranscript: (text: string, metrics: AsrTranscriptionMetrics | null) => void | Promise<void> }) => {
    voiceRuntime.onFinalTranscript = options.onFinalTranscript;
    return {
      ...voiceRuntime.state,
      start: voiceRuntime.start,
      stop: voiceRuntime.stop,
    };
  },
}));

function makeArtwork(objects: Artwork["objects"] = []): Artwork {
  return {
    id: "artwork-1",
    title: "语音绘图作品",
    width: 1024,
    height: 768,
    background: "#ffffff",
    objects,
    created_at: "2026-06-13T00:00:00Z",
    updated_at: "2026-06-13T00:00:00Z",
  };
}

function makeArtworkWithTitle(title: string, objects: Artwork["objects"] = []): Artwork {
  return {
    ...makeArtwork(objects),
    title,
  };
}

function makePlan(overrides: Partial<CommandPlan> = {}): CommandPlan {
  return {
    raw_text: "画一个蓝色圆形",
    normalized_text: "画一个蓝色圆形",
    operations: [{ operation_type: "add_object", payload: {} }],
    scene_plan: null,
    confidence: 0.9,
    requires_confirmation: false,
    clarification_question: null,
    risk_level: "low",
    explanation: "添加一个蓝色圆形",
    planner_source: "rules",
    ...overrides,
  };
}

function makeMetrics(overrides: Partial<CommandExecutionMetrics> = {}): CommandExecutionMetrics {
  return {
    rule_parse_ms: 1,
    llm_planner_ms: null,
    agent_planner_ms: null,
    planner_total_ms: 2,
    execute_ms: 3,
    total_ms: 5,
    llm_attempted: false,
    llm_succeeded: false,
    agent_attempted: false,
    agent_succeeded: false,
    fallback_used: false,
    planner_source: "rules",
    ...overrides,
  };
}

describe("App", () => {
  let audioPlay: ReturnType<typeof vi.fn>;
  let randomId = 0;

  beforeEach(() => {
    randomId = 0;
    voiceRuntime.onFinalTranscript = null;
    voiceRuntime.start.mockReset();
    voiceRuntime.stop.mockReset();
    voiceRuntime.state = {
      isSupported: true,
      isListening: false,
      interimTranscript: "",
      lastFinalTranscript: "",
      error: null,
      provider: "backend",
      providerLabel: "小米 MiMo ASR",
      lastAsrMetrics: null,
    };
    apiMocks.createArtwork.mockResolvedValue(makeArtwork());
    apiMocks.submitVoiceCommand.mockReset();
    apiMocks.synthesizeSpeech.mockResolvedValue({ audio_data_url: "data:audio/wav;base64,AAAA" });
    exportMocks.exportArtworkJson.mockReset();
    exportMocks.exportSvgFile.mockReset();
    exportMocks.exportSvgAsPng.mockReset();
    exportMocks.exportSvgAsPng.mockResolvedValue(undefined);
    exportMocks.svgToPngDataUrl.mockReset();
    exportMocks.svgToPngDataUrl.mockResolvedValue("data:image/png;base64,canvas");
    audioPlay = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal(
      "Audio",
      class AudioStub {
        pause = vi.fn();
        play = audioPlay;
        constructor(public src: string) {}
      }
    );
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => `timeline-${(randomId += 1)}`),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates the initial artwork and exposes voice controls without mouse drawing tools", async () => {
    render(<App />);

    expect(await screen.findByText("语音画布已准备")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始监听" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "导出 PNG" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "开始监听" }));

    expect(voiceRuntime.start).toHaveBeenCalledTimes(1);
    expect(apiMocks.createArtwork).toHaveBeenCalledTimes(1);
  });

  it("shows only the four current latency metrics in the console", async () => {
    render(<App />);

    expect(await screen.findByText("语音画布已准备")).toBeInTheDocument();
    expect(screen.getByText("ASR")).toBeInTheDocument();
    expect(screen.getByText("规划")).toBeInTheDocument();
    expect(screen.getByText("执行")).toBeInTheDocument();
    expect(screen.getByText("端到端")).toBeInTheDocument();
    expect(screen.queryByText("历史 P75")).not.toBeInTheDocument();
    expect(screen.queryByText("历史 P95")).not.toBeInTheDocument();
  });

  it("submits a final voice transcript, updates the canvas and records timeline feedback", async () => {
    const response: CommandExecutionResponse = {
      message: "已添加蓝色圆形",
      plan: makePlan(),
      artwork: makeArtwork([
        {
          id: "circle-1",
          type: "circle",
          name: "蓝色圆形",
          layer_id: "middle",
          group_id: null,
          semantic_tags: ["shape.circle"],
          transform: {},
          geometry: { cx: 512, cy: 384, radius: 80 },
          style: { fill: "#2563eb", stroke: "#111827", strokeWidth: 2 },
          z_index: 0,
        },
      ]),
      metrics: makeMetrics(),
    };
    apiMocks.submitVoiceCommand.mockResolvedValue(response);
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("画一个蓝色圆形", {
        total_ms: 1200,
        audio_bytes: 2048,
        attempt_count: 1,
        successful_provider: "xiaomi",
        fallback_count: 0,
      });
    });

    await waitFor(() => expect(apiMocks.submitVoiceCommand).toHaveBeenCalledWith("artwork-1", "画一个蓝色圆形", undefined));
    await waitFor(() => expect(screen.getAllByText("已添加蓝色圆形").length).toBeGreaterThan(0));
    expect(screen.getByText("添加一个蓝色圆形")).toBeInTheDocument();
    expect(screen.getByText("画一个蓝色圆形")).toBeInTheDocument();
    expect(screen.getByText("1 个对象")).toBeInTheDocument();
    expect(apiMocks.synthesizeSpeech).toHaveBeenCalledWith("已添加蓝色圆形");
    expect(audioPlay).toHaveBeenCalledTimes(1);
  });

  it("shows the structured Drawing Agent fallback reason in the metrics note", async () => {
    apiMocks.submitVoiceCommand.mockResolvedValue({
      message: "我还没有听懂这条绘图指令，可以换一种说法吗？",
      plan: makePlan({ planner_source: "rules_fallback", operations: [] }),
      artwork: makeArtwork(),
      metrics: makeMetrics({
        fallback_used: true,
        fallback_reason: "agent_planner_error",
        fallback_error_type: "DrawingAgentError",
        planner_source: "rules_fallback",
      }),
    });
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("画一个复杂森林场景然后加层次", null);
    });

    expect(await screen.findByText("Agent 规划异常: DrawingAgentError，已使用规则兜底")).toBeInTheDocument();
  });

  it("completes a voice-only acceptance workflow without toolbar export clicks", async () => {
    const houseObjects: Artwork["objects"] = [
      {
        id: "house-body",
        type: "rect",
        name: "房子主体",
        layer_id: "middle",
        group_id: "house",
        semantic_tags: ["house.body"],
        transform: {},
        geometry: { x: 360, y: 330, width: 300, height: 220 },
        style: { fill: "#f3f4f6", stroke: "#111827", strokeWidth: 2 },
        z_index: 0,
      },
      {
        id: "house-door",
        type: "rect",
        name: "门",
        layer_id: "middle",
        group_id: "house",
        semantic_tags: ["house.door"],
        transform: {},
        geometry: { x: 470, y: 440, width: 80, height: 110 },
        style: { fill: "#2563eb", stroke: "#111827", strokeWidth: 2 },
        z_index: 1,
      },
    ];
    const editedHouseObjects: Artwork["objects"] = [
      houseObjects[0],
      {
        ...houseObjects[1],
        style: { fill: "#16a34a", stroke: "#111827", strokeWidth: 2 },
      },
    ];
    apiMocks.submitVoiceCommand
      .mockResolvedValueOnce({
        message: "已画好房子",
        plan: makePlan({ raw_text: "画一个房子 红色屋顶 蓝色门 两扇窗户", operations: [{ operation_type: "add_object", payload: {} }] }),
        artwork: makeArtwork(houseObjects),
        metrics: makeMetrics(),
      })
      .mockResolvedValueOnce({
        message: "已把门改成绿色",
        plan: makePlan({ raw_text: "把门改成绿色", operations: [{ operation_type: "set_style_many", payload: {} }] }),
        artwork: makeArtwork(editedHouseObjects),
        metrics: makeMetrics(),
      })
      .mockResolvedValueOnce({
        message: "已撤销上一步",
        plan: makePlan({ raw_text: "撤销", operations: [{ operation_type: "undo", payload: {} }] }),
        artwork: makeArtwork(houseObjects),
        metrics: makeMetrics(),
      })
      .mockResolvedValueOnce({
        message: "已恢复上一步",
        plan: makePlan({ raw_text: "恢复", operations: [{ operation_type: "redo", payload: {} }] }),
        artwork: makeArtwork(editedHouseObjects),
        metrics: makeMetrics(),
      })
      .mockResolvedValueOnce({
        message: "已保存作品版本",
        plan: makePlan({ raw_text: "保存作品 名字叫语音验收", operations: [{ operation_type: "save_artwork", payload: {} }] }),
        artwork: makeArtworkWithTitle("语音验收", editedHouseObjects),
        metrics: makeMetrics(),
      })
      .mockResolvedValueOnce({
        message: "已准备导出",
        plan: makePlan({ raw_text: "导出 PNG", operations: [{ operation_type: "export_artwork", payload: { format: "png" } }] }),
        artwork: makeArtworkWithTitle("语音验收", editedHouseObjects),
        metrics: makeMetrics(),
      });
    render(<App />);
    await screen.findByText("语音画布已准备");

    for (const transcript of ["画一个房子 红色屋顶 蓝色门 两扇窗户", "把门改成绿色", "撤销", "恢复", "保存作品 名字叫语音验收", "导出 PNG"]) {
      await act(async () => {
        await voiceRuntime.onFinalTranscript?.(transcript, null);
      });
    }

    expect(apiMocks.submitVoiceCommand).toHaveBeenCalledTimes(6);
    expect(exportMocks.exportSvgAsPng).toHaveBeenCalledTimes(1);
    expect(exportMocks.exportSvgAsPng).toHaveBeenCalledWith("voice-canvas-svg", "语音验收.png");
    expect(screen.getByText("导出 PNG")).toBeInTheDocument();
    expect(screen.getAllByText("已准备导出").length).toBeGreaterThan(0);
  });

  it("keeps voice command execution single-flight and reports ignored overlapping input", async () => {
    let resolveCommand: (response: CommandExecutionResponse) => void = () => undefined;
    const pendingCommand = new Promise<CommandExecutionResponse>((resolve) => {
      resolveCommand = resolve;
    });
    apiMocks.submitVoiceCommand.mockReturnValue(pendingCommand);
    render(<App />);
    await screen.findByText("语音画布已准备");

    let firstTranscriptPromise: void | Promise<void>;
    await act(async () => {
      firstTranscriptPromise = voiceRuntime.onFinalTranscript?.("画一个蓝色圆形", null);
    });
    await waitFor(() => expect(apiMocks.submitVoiceCommand).toHaveBeenCalledTimes(1));

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("把它改成绿色", null);
    });

    expect(apiMocks.submitVoiceCommand).toHaveBeenCalledTimes(1);
    expect(screen.getByText("正在执行上一条语音指令，请稍后再说")).toBeInTheDocument();

    resolveCommand({
      message: "已添加蓝色圆形",
      plan: makePlan(),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });
    await act(async () => {
      await firstTranscriptPromise;
    });
  });

  it("shows an image generation state while an artistic image command is pending", async () => {
    let resolveCommand: (response: CommandExecutionResponse) => void = () => undefined;
    const pendingCommand = new Promise<CommandExecutionResponse>((resolve) => {
      resolveCommand = resolve;
    });
    apiMocks.submitVoiceCommand.mockReturnValue(pendingCommand);
    render(<App />);
    await screen.findByText("语音画布已准备");

    let finalTranscriptPromise: void | Promise<void>;
    await act(async () => {
      finalTranscriptPromise = voiceRuntime.onFinalTranscript?.("画一幅中国山水水墨画", null);
    });

    expect(await screen.findByText("正在生成图片")).toBeInTheDocument();
    resolveCommand({
      message: "已生成图片",
      plan: makePlan({
        raw_text: "画一幅中国山水水墨画",
        normalized_text: "画一幅中国山水水墨画",
        operations: [{ operation_type: "generate_image_asset", payload: {} }],
        explanation: "准备生成图片素材并作为可编辑图片对象加入画布",
      }),
      artwork: makeArtwork([
        {
          id: "image-1",
          type: "image",
          name: "中国山水水墨画",
          layer_id: "middle",
          group_id: null,
          semantic_tags: ["generated.image", "image"],
          transform: {},
          geometry: { x: 0, y: 0, width: 1024, height: 768, src: "data:image/png;base64,AAAA" },
          style: { opacity: 1 },
          z_index: 0,
        },
      ]),
      metrics: makeMetrics(),
    });
    await act(async () => {
      await finalTranscriptPromise;
    });

    await waitFor(() => expect(screen.getAllByText("已生成图片").length).toBeGreaterThan(0));
  });

  it("attaches the current canvas image when the user asks to polish the picture", async () => {
    apiMocks.submitVoiceCommand.mockResolvedValue({
      message: "已精修图片",
      plan: makePlan({ raw_text: "精修我的图片", normalized_text: "精修我的图片", operations: [{ operation_type: "polish_image_asset", payload: {} }] }),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("精修我的图片", null);
    });

    await waitFor(() =>
      expect(apiMocks.submitVoiceCommand).toHaveBeenCalledWith("artwork-1", "精修我的图片", "data:image/png;base64,canvas")
    );
    expect(exportMocks.svgToPngDataUrl).toHaveBeenCalledWith("voice-canvas-svg");
    await waitFor(() => expect(screen.getAllByText("已精修图片").length).toBeGreaterThan(0));
  });

  it("attaches the current canvas image when polishing a generated image region", async () => {
    apiMocks.submitVoiceCommand.mockResolvedValue({
      message: "已精修人物眼睛",
      plan: makePlan({
        raw_text: "把人物肖像的眼睛精修一下",
        normalized_text: "把人物肖像的眼睛精修一下",
        operations: [{ operation_type: "polish_image_asset", payload: { target_region: "眼睛" } }],
      }),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("把人物肖像的眼睛精修一下", null);
    });

    await waitFor(() =>
      expect(apiMocks.submitVoiceCommand).toHaveBeenCalledWith("artwork-1", "把人物肖像的眼睛精修一下", "data:image/png;base64,canvas")
    );
  });

  it("runs PNG export from command results and from the toolbar", async () => {
    apiMocks.submitVoiceCommand.mockResolvedValue({
      message: "已准备导出",
      plan: makePlan({ operations: [{ operation_type: "export_artwork", payload: {} }] }),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("导出作品", null);
    });
    await waitFor(() => expect(exportMocks.exportSvgAsPng).toHaveBeenCalledWith("voice-canvas-svg", "语音绘图作品.png"));

    fireEvent.click(screen.getAllByRole("button", { name: "导出 PNG" })[0]);
    await waitFor(() => expect(exportMocks.exportSvgAsPng).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("已导出 PNG")).toBeInTheDocument();
  });

  it("runs SVG and project JSON export from voice command results", async () => {
    apiMocks.submitVoiceCommand.mockResolvedValueOnce({
      message: "已准备导出 SVG",
      plan: makePlan({ operations: [{ operation_type: "export_artwork", payload: { format: "svg" } }] }),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("导出 SVG", null);
    });
    await waitFor(() => expect(exportMocks.exportSvgFile).toHaveBeenCalledWith("voice-canvas-svg", "语音绘图作品.svg"));

    apiMocks.submitVoiceCommand.mockResolvedValueOnce({
      message: "已准备导出项目 JSON",
      plan: makePlan({ operations: [{ operation_type: "export_artwork", payload: { format: "json" } }] }),
      artwork: makeArtwork(),
      metrics: makeMetrics(),
    });

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("导出项目 JSON", null);
    });
    await waitFor(() => expect(exportMocks.exportArtworkJson).toHaveBeenCalledWith(makeArtwork(), "语音绘图作品.json"));
    expect(exportMocks.exportSvgAsPng).not.toHaveBeenCalled();
  });

  it("records failed command execution and speaks the failure message", async () => {
    apiMocks.submitVoiceCommand.mockRejectedValue(new Error("后端执行失败"));
    render(<App />);
    await screen.findByText("语音画布已准备");

    await act(async () => {
      await voiceRuntime.onFinalTranscript?.("画一个不存在的东西", null);
    });

    await waitFor(() => expect(screen.getAllByText("后端执行失败").length).toBeGreaterThan(0));
    expect(apiMocks.synthesizeSpeech).toHaveBeenCalledWith("后端执行失败");
  });
});
