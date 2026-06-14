import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAsrProviders, transcribeAudio } from "../api";
import { useVoiceRecognition } from "./useVoiceRecognition";

const apiMocks = vi.hoisted(() => ({
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

describe("useVoiceRecognition", () => {
  let recognitionInstance: FakeSpeechRecognition | null;

  beforeEach(() => {
    recognitionInstance = null;
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

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads the backend provider label on mount", async () => {
    vi.mocked(fetchAsrProviders).mockResolvedValue({
      providers: ["xiaomi"],
      provider_labels: { xiaomi: "小米 MiMo ASR", web_speech: "Web Speech API" },
      primary_provider: "xiaomi",
      fallback_provider: "web_speech",
    });
    const onFinalTranscript = vi.fn();

    const { result } = renderHook(() => useVoiceRecognition({ onFinalTranscript }));

    await waitFor(() => expect(result.current.providerLabel).toBe("小米 MiMo ASR"));
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
