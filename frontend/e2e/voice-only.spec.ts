import { readFile } from "node:fs/promises";
import { expect, test, type Page, type Route } from "@playwright/test";

type DrawingObject = {
  id: string;
  type: string;
  name: string;
  layer_id: string;
  group_id: string | null;
  semantic_tags: string[];
  transform: Record<string, unknown>;
  geometry: Record<string, unknown>;
  style: Record<string, unknown>;
  z_index: number;
};

type Artwork = {
  id: string;
  title: string;
  width: number;
  height: number;
  background: string;
  objects: DrawingObject[];
  created_at: string;
  updated_at: string;
};

type Operation = {
  operation_type: string;
  payload: Record<string, unknown>;
};

type CommandResponse = {
  message: string;
  plan: {
    raw_text: string;
    normalized_text: string;
    operations: Operation[];
    scene_plan: null;
    confidence: number;
    requires_confirmation: boolean;
    clarification_question: null;
    risk_level: string;
    explanation: string;
    planner_source: string;
  };
  artwork: Artwork;
  metrics: {
    rule_parse_ms: number;
    llm_planner_ms: null;
    agent_planner_ms: null;
    planner_total_ms: number;
    execute_ms: number;
    total_ms: number;
    llm_attempted: boolean;
    llm_succeeded: boolean;
    agent_attempted: boolean;
    agent_succeeded: boolean;
    fallback_used: boolean;
    planner_source: string;
  };
};

type AsrProvidersResponse = {
  providers: string[];
  provider_labels: Record<string, string>;
  primary_provider: string | null;
  fallback_provider: string;
};

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "content-type",
  "content-type": "application/json"
};
const DEFAULT_ASR_PROVIDERS: AsrProvidersResponse = {
  providers: [],
  provider_labels: {},
  primary_provider: null,
  fallback_provider: "web_speech"
};

function makeArtwork(
  title = "语音绘图作品",
  objects: DrawingObject[] = [],
  overrides: Partial<Pick<Artwork, "width" | "height" | "background">> = {}
): Artwork {
  return {
    id: "artwork-e2e",
    title,
    width: overrides.width ?? 1024,
    height: overrides.height ?? 768,
    background: overrides.background ?? "#ffffff",
    objects,
    created_at: "2026-06-14T00:00:00Z",
    updated_at: "2026-06-14T00:00:00Z"
  };
}

function makeMetrics() {
  return {
    rule_parse_ms: 1,
    llm_planner_ms: null,
    agent_planner_ms: null,
    planner_total_ms: 2,
    execute_ms: 3,
    total_ms: 6,
    llm_attempted: false,
    llm_succeeded: false,
    agent_attempted: false,
    agent_succeeded: false,
    fallback_used: false,
    planner_source: "rules"
  };
}

function makeCommandResponse(text: string, message: string, operations: Operation[], artwork: Artwork): CommandResponse {
  return {
    message,
    plan: {
      raw_text: text,
      normalized_text: text,
      operations,
      scene_plan: null,
      confidence: 0.9,
      requires_confirmation: false,
      clarification_question: null,
      risk_level: "low",
      explanation: message,
      planner_source: "rules"
    },
    artwork,
    metrics: makeMetrics()
  };
}

function houseObjects(fill = "#2563eb"): DrawingObject[] {
  return [
    {
      id: "house-body",
      type: "rect",
      name: "房子主体",
      layer_id: "middle",
      group_id: "house",
      semantic_tags: ["house.body"],
      transform: {},
      geometry: { x: 360, y: 330, width: 300, height: 220, radius: 8 },
      style: { fill: "#f3f4f6", stroke: "#111827", strokeWidth: 2 },
      z_index: 0
    },
    {
      id: "house-door",
      type: "rect",
      name: "门",
      layer_id: "middle",
      group_id: "house",
      semantic_tags: ["house.door"],
      transform: {},
      geometry: { x: 470, y: 440, width: 80, height: 110, radius: 4 },
      style: { fill, stroke: "#111827", strokeWidth: 2 },
      z_index: 1
    }
  ];
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    headers: CORS_HEADERS,
    body: JSON.stringify(body)
  });
}

async function installFakeSpeechRecognition(page: Page) {
  await page.addInitScript(() => {
    const win = window as typeof window & {
      __aiPaintingRecognition?: {
        onstart: (() => void) | null;
        onend: (() => void) | null;
        onresult: ((event: unknown) => void) | null;
      };
      __aiPaintingEmitFinalTranscript?: (text: string) => void;
      SpeechRecognition?: new () => unknown;
      webkitSpeechRecognition?: new () => unknown;
    };

    class FakeSpeechRecognition {
      lang = "zh-CN";
      continuous = true;
      interimResults = true;
      maxAlternatives = 1;
      onstart: (() => void) | null = null;
      onend: (() => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      onresult: ((event: unknown) => void) | null = null;

      start() {
        win.__aiPaintingRecognition = this;
        this.onstart?.();
      }

      stop() {
        this.onend?.();
      }
    }

    win.SpeechRecognition = FakeSpeechRecognition as unknown as new () => unknown;
    win.webkitSpeechRecognition = FakeSpeechRecognition as unknown as new () => unknown;
    win.__aiPaintingEmitFinalTranscript = (text: string) => {
      const alternative = { transcript: text, confidence: 0.99 };
      const result = {
        0: alternative,
        isFinal: true,
        length: 1,
        item: () => alternative
      };
      const results = {
        0: result,
        length: 1,
        item: () => result
      };
      win.__aiPaintingRecognition?.onresult?.({ resultIndex: 0, results });
    };

    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true,
      value: () => Promise.resolve()
    });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", {
      configurable: true,
      value: () => undefined
    });
  });
}

async function installKeyboardShortcutGuard(page: Page) {
  await page.addInitScript(() => {
    const win = window as typeof window & { __aiPaintingKeyboardEvents?: string[] };
    win.__aiPaintingKeyboardEvents = [];
    window.addEventListener(
      "keydown",
      (event) => {
        win.__aiPaintingKeyboardEvents?.push([
          event.key,
          event.ctrlKey ? "ctrl" : "",
          event.metaKey ? "meta" : "",
          event.altKey ? "alt" : "",
          event.shiftKey ? "shift" : ""
        ].filter(Boolean).join("+"));
      },
      true
    );
  });
}

async function installDeniedMicrophone(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: () => Promise.reject(new DOMException("用户拒绝麦克风权限", "NotAllowedError"))
      }
    });
  });
}

async function installNoSpeechRecognition(page: Page) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: undefined
    });
  });
}

async function emitVoiceTranscript(page: Page, text: string) {
  await page.evaluate((transcript) => {
    const emit = (window as typeof window & { __aiPaintingEmitFinalTranscript?: (value: string) => void }).__aiPaintingEmitFinalTranscript;
    if (!emit) {
      throw new Error("Fake SpeechRecognition is not installed");
    }
    emit(transcript);
  }, text);
}

async function startListening(page: Page) {
  await page.goto("/");
  await expect(page.getByText("语音画布已准备")).toBeVisible();
  await expect(page.locator('textarea, input:not([type="hidden"]), [contenteditable="true"]')).toHaveCount(0);
  await page.getByRole("button", { name: "开始监听" }).click();
  await expect(page.getByText("Web Speech API").first()).toBeVisible();
}

async function getSvgPixel(page: Page, x: number, y: number): Promise<number[]> {
  return page.evaluate(
    ({ sampleX, sampleY }) =>
      new Promise<number[]>((resolve, reject) => {
        const svg = document.getElementById("voice-canvas-svg");
        if (!(svg instanceof SVGSVGElement)) {
          reject(new Error("没有找到可抽样的 SVG 画布"));
          return;
        }

        const viewBox = svg.viewBox.baseVal;
        const serialized = new XMLSerializer().serializeToString(svg);
        const url = URL.createObjectURL(new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }));
        const image = new Image();
        image.onload = () => {
          const canvas = document.createElement("canvas");
          canvas.width = viewBox.width || svg.clientWidth;
          canvas.height = viewBox.height || svg.clientHeight;
          const context = canvas.getContext("2d");
          if (!context) {
            URL.revokeObjectURL(url);
            reject(new Error("浏览器无法创建像素抽样上下文"));
            return;
          }
          context.drawImage(image, 0, 0);
          URL.revokeObjectURL(url);
          resolve(Array.from(context.getImageData(sampleX, sampleY, 1, 1).data));
        };
        image.onerror = () => {
          URL.revokeObjectURL(url);
          reject(new Error("SVG 像素抽样失败"));
        };
        image.src = url;
      }),
    { sampleX: x, sampleY: y }
  );
}

async function setupMockApi(
  page: Page,
  onCommand: (text: string) => CommandResponse | Promise<CommandResponse>,
  options: { asrProviders?: AsrProvidersResponse } = {}
) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: CORS_HEADERS });
      return;
    }

    if (url.pathname === "/api/asr/providers") {
      await fulfillJson(route, options.asrProviders ?? DEFAULT_ASR_PROVIDERS);
      return;
    }

    if (url.pathname === "/api/artworks" && request.method() === "POST") {
      await fulfillJson(route, makeArtwork());
      return;
    }

    if (url.pathname === "/api/metrics/latency") {
      await fulfillJson(route, {
        artwork_id: "artwork-e2e",
        limit: 200,
        sample_count: 0,
        success_count: 0,
        failed_count: 0,
        needs_confirmation_count: 0,
        canceled_count: 0,
        planner_sources: {},
        metrics: {},
        latest_created_at: null
      });
      return;
    }

    if (url.pathname === "/api/tts/synthesize" && request.method() === "POST") {
      await fulfillJson(route, {
        audio_data_url: "data:audio/wav;base64,AAAA",
        provider: "mock",
        provider_label: "Mock TTS",
        format: "wav"
      });
      return;
    }

    const commandMatch = url.pathname.match(/^\/api\/artworks\/[^/]+\/commands$/);
    if (commandMatch && request.method() === "POST") {
      const payload = request.postDataJSON() as { text: string };
      await fulfillJson(route, await onCommand(payload.text));
      return;
    }

    await fulfillJson(route, { detail: `未 mock 的接口: ${url.pathname}` }, 404);
  });
}

test("voice-only browser workflow creates, draws, edits, undo/redo, and exports PNG without keyboard drawing entry", async ({ page }, testInfo) => {
  await installKeyboardShortcutGuard(page);
  await installFakeSpeechRecognition(page);
  const landscapeCanvas = makeArtwork("横向白色画布", [], { width: 1280, height: 720 });
  const blueHouse = makeArtwork("横向白色画布", houseObjects("#2563eb"), { width: 1280, height: 720 });
  const greenHouse = makeArtwork("横向白色画布", houseObjects("#16a34a"), { width: 1280, height: 720 });
  const savedArtwork = makeArtwork("语音验收", houseObjects("#16a34a"), { width: 1280, height: 720 });
  const commandResponses = new Map<string, CommandResponse>([
    [
      "新建一张横向白色画布",
      makeCommandResponse(
        "新建一张横向白色画布",
        "已新建横向白色画布",
        [{ operation_type: "create_canvas", payload: { width: 1280, height: 720, background: "#ffffff" } }],
        landscapeCanvas
      )
    ],
    [
      "画一个房子 红色屋顶 蓝色门 两扇窗户",
      makeCommandResponse("画一个房子 红色屋顶 蓝色门 两扇窗户", "已画好房子", [{ operation_type: "add_object", payload: {} }], blueHouse)
    ],
    ["把门改成绿色", makeCommandResponse("把门改成绿色", "已把门改成绿色", [{ operation_type: "set_style_many", payload: {} }], greenHouse)],
    ["撤销", makeCommandResponse("撤销", "已撤销上一步", [{ operation_type: "undo", payload: {} }], blueHouse)],
    ["恢复", makeCommandResponse("恢复", "已恢复上一步", [{ operation_type: "redo", payload: {} }], greenHouse)],
    [
      "保存作品 名字叫语音验收",
      makeCommandResponse("保存作品 名字叫语音验收", "已保存作品版本", [{ operation_type: "save_artwork", payload: {} }], savedArtwork)
    ],
    [
      "导出 PNG",
      makeCommandResponse("导出 PNG", "已准备导出", [{ operation_type: "export_artwork", payload: { format: "png" } }], savedArtwork)
    ]
  ]);
  const submittedTranscripts: string[] = [];
  await setupMockApi(page, async (text) => {
    submittedTranscripts.push(text);
    const response = commandResponses.get(text);
    if (!response) {
      throw new Error(`未配置语音指令响应: ${text}`);
    }
    return response;
  });
  await startListening(page);

  await emitVoiceTranscript(page, "新建一张横向白色画布");
  await expect(page.getByText("已新建横向白色画布").first()).toBeVisible();
  await expect(page.locator("#voice-canvas-svg")).toHaveAttribute("viewBox", "0 0 1280 720");
  await expect(page.locator("#voice-canvas-svg")).toHaveAttribute("data-object-count", "0");

  for (const [transcript, message] of [
    ["画一个房子 红色屋顶 蓝色门 两扇窗户", "已画好房子"],
    ["把门改成绿色", "已把门改成绿色"],
    ["撤销", "已撤销上一步"],
    ["恢复", "已恢复上一步"],
    ["保存作品 名字叫语音验收", "已保存作品版本"]
  ] as const) {
    await emitVoiceTranscript(page, transcript);
    await expect(page.getByText(message).first()).toBeVisible();
  }
  await expect(page.locator("#voice-canvas-svg")).toHaveAttribute("data-object-count", "2");
  const doorPixel = await getSvgPixel(page, 510, 495);
  expect(doorPixel[0]).toBeLessThan(80);
  expect(doorPixel[1]).toBeGreaterThan(120);
  expect(doorPixel[2]).toBeLessThan(120);

  const downloadPromise = page.waitForEvent("download");
  await emitVoiceTranscript(page, "导出 PNG");
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("语音验收.png");
  expect(await download.failure()).toBeNull();
  const downloadedPath = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(downloadedPath);
  const pngBytes = await readFile(downloadedPath);
  expect(Array.from(pngBytes.subarray(0, 8))).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  expect(submittedTranscripts).toEqual([
    "新建一张横向白色画布",
    "画一个房子 红色屋顶 蓝色门 两扇窗户",
    "把门改成绿色",
    "撤销",
    "恢复",
    "保存作品 名字叫语音验收",
    "导出 PNG"
  ]);
  const keyboardEvents = await page.evaluate(() => (window as typeof window & { __aiPaintingKeyboardEvents?: string[] }).__aiPaintingKeyboardEvents ?? []);
  expect(keyboardEvents).toEqual([]);
});

test("voice commands export SVG and project JSON downloads with inspectable content", async ({ page }, testInfo) => {
  await installFakeSpeechRecognition(page);
  const drawnArtwork = makeArtwork("语音绘图作品", houseObjects("#2563eb"));
  const savedArtwork = makeArtwork("语音验收", houseObjects("#16a34a"));
  const commandResponses = new Map<string, CommandResponse>([
    [
      "画一个房子 红色屋顶 蓝色门 两扇窗户",
      makeCommandResponse("画一个房子 红色屋顶 蓝色门 两扇窗户", "已画好房子", [{ operation_type: "add_object", payload: {} }], drawnArtwork)
    ],
    [
      "保存作品 名字叫语音验收",
      makeCommandResponse("保存作品 名字叫语音验收", "已保存作品版本", [{ operation_type: "save_artwork", payload: {} }], savedArtwork)
    ],
    [
      "导出 SVG",
      makeCommandResponse("导出 SVG", "已准备导出 SVG", [{ operation_type: "export_artwork", payload: { format: "svg" } }], savedArtwork)
    ],
    [
      "导出项目 JSON",
      makeCommandResponse("导出项目 JSON", "已准备导出项目 JSON", [{ operation_type: "export_artwork", payload: { format: "json" } }], savedArtwork)
    ]
  ]);
  await setupMockApi(page, async (text) => {
    const response = commandResponses.get(text);
    if (!response) {
      throw new Error(`未配置语音指令响应: ${text}`);
    }
    return response;
  });
  await startListening(page);

  await emitVoiceTranscript(page, "画一个房子 红色屋顶 蓝色门 两扇窗户");
  await expect(page.getByText("已画好房子").first()).toBeVisible();
  await emitVoiceTranscript(page, "保存作品 名字叫语音验收");
  await expect(page.getByText("已保存作品版本").first()).toBeVisible();

  const svgDownloadPromise = page.waitForEvent("download");
  await emitVoiceTranscript(page, "导出 SVG");
  const svgDownload = await svgDownloadPromise;
  expect(svgDownload.suggestedFilename()).toBe("语音验收.svg");
  const svgPath = testInfo.outputPath("voice-export.svg");
  await svgDownload.saveAs(svgPath);
  const svgText = await readFile(svgPath, "utf8");
  expect(svgText).toContain("<svg");
  expect(svgText).toContain('data-object-id="house-door"');
  expect(svgText).toContain("#16a34a");

  const jsonDownloadPromise = page.waitForEvent("download");
  await emitVoiceTranscript(page, "导出项目 JSON");
  const jsonDownload = await jsonDownloadPromise;
  expect(jsonDownload.suggestedFilename()).toBe("语音验收.json");
  const jsonPath = testInfo.outputPath("voice-export.json");
  await jsonDownload.saveAs(jsonPath);
  const exportedArtwork = JSON.parse(await readFile(jsonPath, "utf8")) as Artwork;
  expect(exportedArtwork.title).toBe("语音验收");
  expect(exportedArtwork.objects.map((object) => object.id)).toEqual(["house-body", "house-door"]);
  expect(exportedArtwork.objects[1].style.fill).toBe("#16a34a");
});

test("overlapping final voice transcripts stay single-flight in a real browser", async ({ page }) => {
  await installFakeSpeechRecognition(page);
  let releaseFirstCommand: (() => void) | undefined;
  const firstCommandGate = new Promise<void>((resolve) => {
    releaseFirstCommand = resolve;
  });
  const submittedTranscripts: string[] = [];
  await setupMockApi(page, async (text) => {
    submittedTranscripts.push(text);
    if (text === "画一个蓝色圆形") {
      await firstCommandGate;
      return makeCommandResponse(text, "已添加蓝色圆形", [{ operation_type: "add_object", payload: {} }], makeArtwork());
    }
    return makeCommandResponse(text, "不应执行第二条重叠指令", [{ operation_type: "set_style_many", payload: {} }], makeArtwork());
  });
  await startListening(page);

  await emitVoiceTranscript(page, "画一个蓝色圆形");
  await expect.poll(() => submittedTranscripts.length).toBe(1);
  await expect(page.getByText("正在解析语音指令")).toBeVisible();

  await emitVoiceTranscript(page, "把它改成绿色");

  await expect(page.getByText("正在执行上一条语音指令，请稍后再说")).toBeVisible();
  await page.waitForTimeout(250);
  expect(submittedTranscripts).toEqual(["画一个蓝色圆形"]);

  releaseFirstCommand?.();
  await expect(page.getByText("已添加蓝色圆形").first()).toBeVisible();
});

test("microphone permission denial falls back to Web Speech and keeps voice execution available", async ({ page }) => {
  await installFakeSpeechRecognition(page);
  await installDeniedMicrophone(page);
  const submittedTranscripts: string[] = [];
  await setupMockApi(
    page,
    async (text) => {
      submittedTranscripts.push(text);
      return makeCommandResponse(text, "已添加蓝色圆形", [{ operation_type: "add_object", payload: {} }], makeArtwork());
    },
    {
      asrProviders: {
        providers: ["xiaomi"],
        provider_labels: { xiaomi: "小米 MiMo ASR" },
        primary_provider: "xiaomi",
        fallback_provider: "web_speech"
      }
    }
  );

  await page.goto("/");
  await expect(page.getByText("语音画布已准备")).toBeVisible();
  await expect(page.getByText("小米 MiMo ASR").first()).toBeVisible();
  await page.getByRole("button", { name: "开始监听" }).click();

  await expect(page.getByText("Web Speech API").first()).toBeVisible();
  await emitVoiceTranscript(page, "画一个蓝色圆形");

  await expect(page.getByText("已添加蓝色圆形").first()).toBeVisible();
  expect(submittedTranscripts).toEqual(["画一个蓝色圆形"]);
});

test("start listening is disabled when neither backend ASR nor browser speech recognition is available", async ({ page }) => {
  await installNoSpeechRecognition(page);
  await setupMockApi(page, async (text) =>
    makeCommandResponse(text, "不应执行无语音能力指令", [{ operation_type: "add_object", payload: {} }], makeArtwork())
  );

  await page.goto("/");

  await expect(page.getByText("当前没有可用的语音识别").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "开始监听" })).toBeDisabled();
});
