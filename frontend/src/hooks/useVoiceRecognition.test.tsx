import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAsrStreamSocket, fetchAsrProviders, transcribeAudio } from "../api";
import { useVoiceRecognition } from "./useVoiceRecognition";

const apiMocks = vi.hoisted(() => ({
  createAsrStreamSocket: vi.fn(),
  fetchAsrProviders: vi.fn(),
  transcribeAudio: vi.fn(),
}));

vi.mock("../api", () => apiMocks);

class FakeSpeechRecognition {
  lang = "";
  continuous = false;
  interimResults = false;
  maxAlternatives = 1;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string; message: string }) => void) | null = null;
  onresult: ((event: {
    resultIndex: number;
    results: ArrayLike<{ isFinal: boolean; 0: { transcript: string; confidence: number } }>;
  }) => void) | null = null;

  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());
}

function speechEvent(transcript: string, isFinal = true) {
  return {
    resultIndex: 0,
    results: [
      {
        isFinal,
        length: 1,
        0: { transcript, confidence: 0.9 },
        item: () => ({ transcript, confidence: 0.9 }),
      },
    ],
  };
}

function audioEvent(samples: Float32Array) {
  return {
    inputBuffer: {
      getChannelData: () => samples,
    },
    outputBuffer: {
      getChannelData: () => new Float32Array(samples.length),
    },
  } as unknown as AudioProcessingEvent;
}

class FakeWebSocket {
  readyState = 0;
  sent: Array<string | ArrayBuffer | Blob | ArrayBufferView> = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn(() => {
    this.readyState = 3;
    this.onclose?.();
  });

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  send(data: string | ArrayBuffer | Blob | ArrayBufferView) {
    this.sent.push(data);
  }

  receive(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe("useVoiceRecognition", () => {
  let recognitionInstance: FakeSpeechRecognition | null;

  beforeEach(() => {
    recognitionInstance = null;
    apiMocks.createAsrStreamSocket.mockReset();
    apiMocks.fetchAsrProviders.mockReset();
    apiMocks.transcribeAudio.mockReset();
    vi.stubGlobal(
      "SpeechRecognition",
      class extends FakeSpeechRecognition {
        constructor() {
          super();
          recognitionInstance = this;
        }
      }
    );
  });

  it("streams backend audio over WebSocket and handles the final transcript", async () => {
    let now = 0;
    let processor: ScriptProcessorNode | null = null;
    const onFinalTranscript = vi.fn();
    const socket = new FakeWebSocket();

    vi.spyOn(window.performance, "now").mockImplementation(() => now);
    vi.stubGlobal(
      "AudioContext",
      class {
        sampleRate = 16000;
        destination = {};
        close = vi.fn().mockResolvedValue(undefined);

        createMediaStreamSource() {
          return { connect: vi.fn(), disconnect: vi.fn() };
        }

        createScriptProcessor() {
          processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null } as unknown as ScriptProcessorNode;
          return processor;
        }
      }
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
    vi.mocked(fetchAsrProviders).mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      provider_capabilities: {
        xiaomi: {
          mode: "segment",
          streaming_supported: false,
          interim_results_supported: false,
          websocket_transport_supported: true,
          partial_transcript_supported: false,
          segment_submission: true,
          silence_stop_ms: 1500,
          description: "流式上传后整段识别",
        },
      },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    vi.mocked(createAsrStreamSocket).mockReturnValue(socket as unknown as WebSocket);
    vi.mocked(transcribeAudio).mockResolvedValue({
      text: "不应该走 REST",
      provider: "xiaomi",
      provider_label: "小米 MiMo ASR",
      attempts: [],
      metrics: {
        total_ms: 1000,
        audio_bytes: 3200,
        attempt_count: 1,
        successful_provider: "xiaomi",
        fallback_count: 0,
      },
    });

    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(createAsrStreamSocket).toHaveBeenCalledTimes(1));
    act(() => {
      socket.open();
    });
    expect(socket.sent[0]).toBe(JSON.stringify({ type: "start", language: "zh", sample_rate: 16000 }));

    act(() => {
      now = 0;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 600;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 2201;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0, 0, 0])));
    });

    expect(socket.sent.some((item) => item instanceof ArrayBuffer)).toBe(true);
    expect(socket.sent).toContain(JSON.stringify({ type: "finalize" }));
    expect(transcribeAudio).not.toHaveBeenCalled();

    act(() => {
      socket.receive({
        type: "final",
        text: "画一个蓝色圆形",
        provider: "xiaomi",
        provider_label: "小米 MiMo ASR",
        metrics: {
          total_ms: 520,
          audio_bytes: 4096,
          attempt_count: 1,
          successful_provider: "xiaomi",
          fallback_count: 0,
        },
      });
    });

    await waitFor(() =>
      expect(onFinalTranscript).toHaveBeenCalledWith(
        "画一个蓝色圆形",
        expect.objectContaining({ total_ms: 520, successful_provider: "xiaomi" })
      )
    );
    expect(result.current.lastFinalTranscript).toBe("画一个蓝色圆形");
  });

  it("falls back to REST transcription when the ASR stream finalization fails", async () => {
    let now = 0;
    let processor: ScriptProcessorNode | null = null;
    const onFinalTranscript = vi.fn();
    const socket = new FakeWebSocket();

    vi.spyOn(window.performance, "now").mockImplementation(() => now);
    vi.stubGlobal(
      "AudioContext",
      class {
        sampleRate = 16000;
        destination = {};
        close = vi.fn().mockResolvedValue(undefined);

        createMediaStreamSource() {
          return { connect: vi.fn(), disconnect: vi.fn() };
        }

        createScriptProcessor() {
          processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null } as unknown as ScriptProcessorNode;
          return processor;
        }
      }
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
    vi.mocked(fetchAsrProviders).mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      provider_capabilities: {
        xiaomi: {
          mode: "segment",
          streaming_supported: false,
          interim_results_supported: false,
          websocket_transport_supported: true,
          partial_transcript_supported: false,
          segment_submission: true,
          silence_stop_ms: 1500,
          description: "流式上传后整段识别",
        },
      },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    vi.mocked(createAsrStreamSocket).mockReturnValue(socket as unknown as WebSocket);
    vi.mocked(transcribeAudio).mockResolvedValue({
      text: "REST 兜底识别",
      provider: "xiaomi",
      provider_label: "小米 MiMo ASR",
      attempts: [],
      metrics: {
        total_ms: 900,
        audio_bytes: 3200,
        attempt_count: 1,
        successful_provider: "xiaomi",
        fallback_count: 0,
      },
    });

    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(createAsrStreamSocket).toHaveBeenCalledTimes(1));
    act(() => {
      socket.open();
      now = 0;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 600;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 2201;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0, 0, 0])));
    });
    expect(socket.sent).toContain(JSON.stringify({ type: "finalize" }));

    act(() => {
      socket.receive({ type: "error", code: "providers_unavailable", message: "流式识别失败" });
    });

    await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(onFinalTranscript).toHaveBeenCalledWith(
        "REST 兜底识别",
        expect.objectContaining({ total_ms: 900, successful_provider: "xiaomi" })
      )
    );
    expect(result.current.lastFinalTranscript).toBe("REST 兜底识别");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads the backend provider label on mount", async () => {
    vi.mocked(fetchAsrProviders).mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      provider_capabilities: {
        xiaomi: {
          mode: "segment",
          streaming_supported: false,
          interim_results_supported: false,
          segment_submission: true,
          silence_stop_ms: 1500,
          description: "静音截停后整段上传转写",
        },
        web_speech: {
          mode: "browser_interim",
          streaming_supported: true,
          interim_results_supported: true,
          segment_submission: false,
          silence_stop_ms: null,
          description: "浏览器实时 interim 文本",
        },
      },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    const onFinalTranscript = vi.fn();

    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await waitFor(() => expect(result.current.providerLabel).toBe("小米 MiMo ASR"));
    await waitFor(() => expect(result.current.providerCapability?.mode).toBe("segment"));
    expect(result.current.providerCapability?.streaming_supported).toBe(false);
    expect(result.current.providerCapability?.silence_stop_ms).toBe(1500);
    expect(result.current.isSupported).toBe(true);
  });

  it("falls back to Web Speech API and emits final transcripts", async () => {
    vi.mocked(fetchAsrProviders).mockResolvedValue({
      providers: [],
      provider_labels: { web_speech: "Web Speech API" },
      primary_provider: null,
      fallback_provider: "web_speech",
    });
    const onFinalTranscript = vi.fn();
    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await act(async () => {
      result.current.start();
    });

    await waitFor(() => expect(result.current.provider).toBe("web_speech"));
    act(() => {
      recognitionInstance?.onresult?.(speechEvent("画一个圆"));
    });

    await waitFor(() => expect(onFinalTranscript).toHaveBeenCalledWith("画一个圆", null));
    expect(result.current.lastFinalTranscript).toBe("画一个圆");
    expect(result.current.interimTranscript).toBe("");
  });

  it("shows an unsupported error when neither backend nor Web Speech is available", async () => {
    vi.unstubAllGlobals();
    apiMocks.fetchAsrProviders.mockResolvedValue({
      providers: [],
      provider_labels: {},
      primary_provider: null,
      fallback_provider: "web_speech",
    });
    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript: vi.fn() }));

    await act(async () => {
      result.current.start();
    });

    await waitFor(() => expect(result.current.isSupported).toBe(false));
    expect(result.current.error).toContain("不支持内置语音识别");
  });

  it("records backend audio, cuts after 1.5 seconds of silence and uploads WAV audio", async () => {
    let now = 0;
    let processor: ScriptProcessorNode | null = null;
    const stopTrack = vi.fn();
    const close = vi.fn().mockResolvedValue(undefined);
    const onFinalTranscript = vi.fn();

    vi.spyOn(window.performance, "now").mockImplementation(() => now);
    vi.stubGlobal(
      "AudioContext",
      class {
        sampleRate = 16000;
        destination = {};
        close = close;

        createMediaStreamSource() {
          return { connect: vi.fn(), disconnect: vi.fn() };
        }

        createScriptProcessor() {
          processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null } as unknown as ScriptProcessorNode;
          return processor;
        }
      }
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: stopTrack }],
        }),
      },
    });
    apiMocks.fetchAsrProviders.mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    vi.mocked(transcribeAudio).mockResolvedValue({
      text: "画一个蓝色圆形",
      provider: "xiaomi",
      provider_label: "小米 MiMo ASR",
      attempts: [],
      metrics: {
        total_ms: 800,
        audio_bytes: 3200,
        attempt_count: 1,
        successful_provider: "xiaomi",
        fallback_count: 0,
      },
    });
    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.provider).toBe("backend"));

    act(() => {
      now = 0;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 600;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 2201;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0, 0, 0])));
    });

    await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
    expect(vi.mocked(transcribeAudio).mock.calls[0][0]).toMatch(/^data:audio\/wav;base64,/);
    await waitFor(() =>
      expect(onFinalTranscript).toHaveBeenCalledWith(
        "画一个蓝色圆形",
        expect.objectContaining({ successful_provider: "xiaomi", attempt_count: 1 })
      )
    );
    expect(result.current.lastFinalTranscript).toBe("画一个蓝色圆形");

    act(() => {
      result.current.stop();
    });
    expect(stopTrack).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("does not cut long speech at 30 seconds before the 1.5 second silence window", async () => {
    let now = 0;
    let processor: ScriptProcessorNode | null = null;
    const onFinalTranscript = vi.fn();

    vi.spyOn(window.performance, "now").mockImplementation(() => now);
    vi.stubGlobal(
      "AudioContext",
      class {
        sampleRate = 16000;
        destination = {};
        close = vi.fn().mockResolvedValue(undefined);

        createMediaStreamSource() {
          return { connect: vi.fn(), disconnect: vi.fn() };
        }

        createScriptProcessor() {
          processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null } as unknown as ScriptProcessorNode;
          return processor;
        }
      }
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
    apiMocks.fetchAsrProviders.mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    vi.mocked(transcribeAudio).mockResolvedValue({
      text: "画一个很复杂的长指令",
      provider: "xiaomi",
      provider_label: "小米 MiMo ASR",
      attempts: [],
      metrics: {
        total_ms: 1200,
        audio_bytes: 4800,
        attempt_count: 1,
        successful_provider: "xiaomi",
        fallback_count: 0,
      },
    });
    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.provider).toBe("backend"));

    act(() => {
      now = 0;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
      now = 30600;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09, 0.07])));
    });

    expect(transcribeAudio).not.toHaveBeenCalled();

    act(() => {
      now = 32201;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0, 0, 0])));
    });

    await waitFor(() => expect(transcribeAudio).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onFinalTranscript).toHaveBeenCalledWith("画一个很复杂的长指令", expect.any(Object)));
  });

  it("falls back to Web Speech when backend transcription upload fails", async () => {
    let now = 0;
    let processor: ScriptProcessorNode | null = null;
    vi.spyOn(window.performance, "now").mockImplementation(() => now);
    vi.stubGlobal(
      "AudioContext",
      class {
        sampleRate = 16000;
        destination = {};
        close = vi.fn().mockResolvedValue(undefined);

        createMediaStreamSource() {
          return { connect: vi.fn(), disconnect: vi.fn() };
        }

        createScriptProcessor() {
          processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null } as unknown as ScriptProcessorNode;
          return processor;
        }
      }
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });
    apiMocks.fetchAsrProviders.mockResolvedValue({
      providers: ["local"],
      provider_labels: { local: "本地 ASR", web_speech: "Web Speech API" },
      primary_provider: "local",
      fallback_provider: "web_speech",
    });
    vi.mocked(transcribeAudio).mockRejectedValue(new Error("上传失败"));
    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript: vi.fn() }));

    await act(async () => {
      result.current.start();
    });
    await waitFor(() => expect(result.current.provider).toBe("backend"));
    act(() => {
      now = 0;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09])));
      now = 700;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0.08, 0.09])));
      now = 2301;
      processor?.onaudioprocess?.(audioEvent(new Float32Array([0, 0])));
    });

    await waitFor(() => expect(result.current.provider).toBe("web_speech"));
    expect(result.current.providerLabel).toBe("Web Speech API");
    expect(recognitionInstance?.start).toHaveBeenCalledTimes(1);
  });
});
