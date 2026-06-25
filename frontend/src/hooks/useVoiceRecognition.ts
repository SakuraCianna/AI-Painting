import { useCallback, useEffect, useRef, useState } from "react";
import { createAsrStreamSocket, fetchAsrProviders, transcribeAudio } from "../api";
import type { AsrProviderCapability, AsrTranscriptionMetrics } from "../types";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternativeLike;
  [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    item(index: number): SpeechRecognitionResultLike;
    [index: number]: SpeechRecognitionResultLike;
  };
}

interface SpeechRecognitionErrorEventLike {
  readonly error: string;
  readonly message: string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
  stop: () => void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;
type AudioContextConstructor = new (contextOptions?: AudioContextOptions) => AudioContext;
type VoiceProvider = "backend" | "web_speech" | "none";

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
    webkitAudioContext?: AudioContextConstructor;
  }
}

interface UseVoiceRecognitionOptions {
  onFinalTranscript: (text: string, asrMetrics: AsrTranscriptionMetrics | null) => void;
}

const TARGET_SAMPLE_RATE = 16000;
const SPEECH_THRESHOLD = 0.045;
const SPEECH_START_CONFIRM_MS = 160;
const SPEECH_START_GRACE_MS = 260;
const SILENCE_MS = 1500;
const MIN_SPEECH_MS = 480;
const WEB_SPEECH_PROVIDER = "web_speech";

const DEFAULT_WEB_SPEECH_CAPABILITY: AsrProviderCapability = {
  mode: "browser_interim",
  streaming_supported: true,
  interim_results_supported: true,
  websocket_transport_supported: false,
  partial_transcript_supported: true,
  segment_submission: false,
  silence_stop_ms: null,
  description: "浏览器 SpeechRecognition 兜底路径, 可显示 interim 文本",
};

const DEFAULT_BACKEND_CAPABILITY: AsrProviderCapability = {
  mode: "segment",
  streaming_supported: false,
  interim_results_supported: false,
  websocket_transport_supported: false,
  partial_transcript_supported: false,
  segment_submission: true,
  silence_stop_ms: SILENCE_MS,
  description: "前端静音截停后把整段音频提交到后端 ASR",
};

function mergeChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function downsampleBuffer(input: Float32Array, inputRate: number, outputRate: number): Float32Array {
  if (inputRate === outputRate) {
    return input;
  }
  const ratio = inputRate / outputRate;
  const outputLength = Math.round(input.length / ratio);
  const output = new Float32Array(outputLength);
  let inputOffset = 0;
  for (let outputOffset = 0; outputOffset < outputLength; outputOffset += 1) {
    const nextInputOffset = Math.round((outputOffset + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let index = inputOffset; index < nextInputOffset && index < input.length; index += 1) {
      sum += input[index];
      count += 1;
    }
    output[outputOffset] = count > 0 ? sum / count : 0;
    inputOffset = nextInputOffset;
  }
  return output;
}

function writeString(view: DataView, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const bytesPerSample = 2;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * bytesPerSample, true);

  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += bytesPerSample;
  }
  return new Uint8Array(buffer);
}

function encodePcm16(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return buffer;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    const chunk = bytes.subarray(index, index + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return window.btoa(binary);
}

function getAudioErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "麦克风或后端 ASR 不可用";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function useVoiceRecognition({ onFinalTranscript }: UseVoiceRecognitionOptions) {
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldListenRef = useRef(false);
  const listenRunIdRef = useRef(0);
  const providerRef = useRef<VoiceProvider>("none");
  const providerCapabilitiesRef = useRef<Record<string, AsrProviderCapability>>({});
  const isUploadingRef = useRef(false);
  const restTranscriptionAbortRef = useRef<AbortController | null>(null);
  const streamSocketRef = useRef<WebSocket | null>(null);
  const streamReadyRef = useRef(false);
  const streamSentBytesRef = useRef(0);
  const pendingStreamFinalizeRef = useRef<{ chunks: Float32Array[]; inputSampleRate: number } | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const captureChunksRef = useRef<Float32Array[]>([]);
  const recordingRef = useRef(false);
  const speechCandidateStartedAtRef = useRef<number | null>(null);
  const speechCandidateLastVoiceAtRef = useRef(0);
  const speechCandidateVoiceFramesRef = useRef(0);
  const speechCandidateChunksRef = useRef<Float32Array[]>([]);
  const speechStartedAtRef = useRef(0);
  const lastVoiceAtRef = useRef(0);
  const sampleRateRef = useRef(TARGET_SAMPLE_RATE);
  const [isSupported, setIsSupported] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [lastFinalTranscript, setLastFinalTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<VoiceProvider>("none");
  const [providerLabel, setProviderLabel] = useState("小米 MiMo ASR");
  const [providerCapability, setProviderCapability] = useState<AsrProviderCapability | null>(null);
  const [lastAsrMetrics, setLastAsrMetrics] = useState<AsrTranscriptionMetrics | null>(null);

  useEffect(() => {
    onFinalTranscriptRef.current = onFinalTranscript;
  }, [onFinalTranscript]);

  const isActiveListenRun = useCallback((listenRunId: number) => {
    return shouldListenRef.current && listenRunIdRef.current === listenRunId;
  }, []);

  const closeAsrStream = useCallback(() => {
    const socket = streamSocketRef.current;
    streamSocketRef.current = null;
    streamReadyRef.current = false;
    streamSentBytesRef.current = 0;
    pendingStreamFinalizeRef.current = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
    }
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.close();
    }
  }, []);

  const stopWebSpeechRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }
    recognition.onstart = null;
    recognition.onend = null;
    recognition.onerror = null;
    recognition.onresult = null;
    recognitionRef.current = null;
    recognition.stop();
  }, []);

  const stopBackendAudio = useCallback(() => {
    restTranscriptionAbortRef.current?.abort();
    restTranscriptionAbortRef.current = null;
    processorRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    captureChunksRef.current = [];
    recordingRef.current = false;
    speechCandidateStartedAtRef.current = null;
    speechCandidateLastVoiceAtRef.current = 0;
    speechCandidateVoiceFramesRef.current = 0;
    speechCandidateChunksRef.current = [];
    isUploadingRef.current = false;
    closeAsrStream();
  }, [closeAsrStream]);

  const startWebSpeechFallback = useCallback((listenRunId: number) => {
    if (!isActiveListenRun(listenRunId)) {
      return;
    }
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      providerRef.current = "none";
      setProvider("none");
      setProviderLabel("无可用语音识别");
      setProviderCapability(null);
      setIsListening(false);
      setIsSupported(false);
      setError("当前浏览器不支持内置语音识别, 且后端 ASR 不可用");
      return;
    }

    stopWebSpeechRecognition();
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      if (recognitionRef.current !== recognition || !isActiveListenRun(listenRunId)) {
        return;
      }
      setIsListening(true);
      setIsSupported(true);
      setError(null);
    };

    recognition.onend = () => {
      if (recognitionRef.current !== recognition || !isActiveListenRun(listenRunId)) {
        return;
      }
      setIsListening(false);
      if (shouldListenRef.current && providerRef.current === "web_speech") {
        window.setTimeout(() => {
          if (recognitionRef.current === recognition && isActiveListenRun(listenRunId)) {
            startWebSpeechFallback(listenRunId);
          }
        }, 350);
      }
    };

    recognition.onerror = (event) => {
      if (recognitionRef.current !== recognition || !isActiveListenRun(listenRunId)) {
        return;
      }
      setError(event.message || event.error || "语音识别失败");
    };

    recognition.onresult = (event) => {
      if (recognitionRef.current !== recognition || !isActiveListenRun(listenRunId)) {
        return;
      }
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript.trim() ?? "";
        if (!transcript) {
          continue;
        }
        if (!isActiveListenRun(listenRunId)) {
          return;
        }
        if (result.isFinal) {
          setLastFinalTranscript(transcript);
          setInterimTranscript("");
          setLastAsrMetrics(null);
          onFinalTranscriptRef.current(transcript, null);
        } else {
          interim += transcript;
        }
      }
      if (interim) {
        setInterimTranscript(interim);
      }
    };

    recognitionRef.current = recognition;
    providerRef.current = "web_speech";
    setProvider("web_speech");
    setProviderLabel("Web Speech API");
    setProviderCapability(providerCapabilitiesRef.current[WEB_SPEECH_PROVIDER] ?? DEFAULT_WEB_SPEECH_CAPABILITY);
    try {
      recognition.start();
    } catch {
      // 浏览器在已监听状态重复 start 会抛异常, 这里保持当前监听状态即可。
    }
  }, [isActiveListenRun, stopWebSpeechRecognition]);

  const finalizeRestTranscript = useCallback(
    async (chunks: Float32Array[], inputSampleRate: number) => {
      if (isUploadingRef.current || chunks.length === 0) {
        return;
      }
      isUploadingRef.current = true;
      setInterimTranscript("正在识别...");
      const listenRunId = listenRunIdRef.current;
      restTranscriptionAbortRef.current?.abort();
      const transcriptionAbort = new AbortController();
      restTranscriptionAbortRef.current = transcriptionAbort;
      try {
        const merged = mergeChunks(chunks);
        const samples = downsampleBuffer(merged, inputSampleRate, TARGET_SAMPLE_RATE);
        const wavBytes = encodeWav(samples, TARGET_SAMPLE_RATE);
        const audioDataUrl = `data:audio/wav;base64,${bytesToBase64(wavBytes)}`;
        const response = await transcribeAudio(audioDataUrl, "zh", transcriptionAbort.signal);
        if (transcriptionAbort.signal.aborted || !isActiveListenRun(listenRunId)) {
          return;
        }
        const text = response.text.trim();
        if (!text) {
          throw new Error("ASR 没有返回文本");
        }
        setProviderLabel(response.provider_label);
        setProviderCapability(providerCapabilitiesRef.current[response.provider] ?? DEFAULT_BACKEND_CAPABILITY);
        setLastAsrMetrics(response.metrics);
        setLastFinalTranscript(text);
        setInterimTranscript("");
        onFinalTranscriptRef.current(text, response.metrics);
      } catch (backendError) {
        if (isAbortError(backendError) || transcriptionAbort.signal.aborted) {
          return;
        }
        if (!isActiveListenRun(listenRunId)) {
          return;
        }
        setError(`后端 ASR 不可用, 已切换到 Web Speech API: ${getAudioErrorMessage(backendError)}`);
        stopBackendAudio();
        if (shouldListenRef.current) {
          startWebSpeechFallback(listenRunId);
        }
      } finally {
        if (restTranscriptionAbortRef.current === transcriptionAbort) {
          restTranscriptionAbortRef.current = null;
          isUploadingRef.current = false;
        }
      }
    },
    [isActiveListenRun, startWebSpeechFallback, stopBackendAudio]
  );

  const handleAsrStreamFinal = useCallback((payload: Record<string, unknown>, listenRunId: number) => {
    if (!isActiveListenRun(listenRunId)) {
      return;
    }
    const text = typeof payload.text === "string" ? payload.text.trim() : "";
    if (!text) {
      setError("ASR 流式通道没有返回文本");
      return;
    }
    const provider = typeof payload.provider === "string" ? payload.provider : "backend";
    const providerLabelFromStream = typeof payload.provider_label === "string" ? payload.provider_label : providerLabel;
    const metrics = payload.metrics && typeof payload.metrics === "object" ? (payload.metrics as AsrTranscriptionMetrics) : null;
    pendingStreamFinalizeRef.current = null;
    streamSentBytesRef.current = 0;
    isUploadingRef.current = false;
    setProviderLabel(providerLabelFromStream);
    setProviderCapability(providerCapabilitiesRef.current[provider] ?? DEFAULT_BACKEND_CAPABILITY);
    setLastAsrMetrics(metrics);
    setLastFinalTranscript(text);
    setInterimTranscript("");
    onFinalTranscriptRef.current(text, metrics);
  }, [isActiveListenRun, providerLabel]);

  const handleAsrStreamMessage = useCallback(
    (event: MessageEvent, listenRunId: number) => {
      if (!isActiveListenRun(listenRunId)) {
        return;
      }
      let payload: unknown;
      try {
        payload = JSON.parse(String(event.data));
      } catch {
        setError("ASR 流式通道返回了无法解析的消息");
        return;
      }
      if (!payload || typeof payload !== "object") {
        return;
      }
      const typedPayload = payload as Record<string, unknown>;
      if (typedPayload.type === "final") {
        handleAsrStreamFinal(typedPayload, listenRunId);
        return;
      }
      if (typedPayload.type === "recognizing") {
        if (!isActiveListenRun(listenRunId)) {
          return;
        }
        setInterimTranscript("正在识别...");
        return;
      }
      if (typedPayload.type === "error") {
        const pending = pendingStreamFinalizeRef.current;
        pendingStreamFinalizeRef.current = null;
        streamSentBytesRef.current = 0;
        const message = typeof typedPayload.message === "string" ? typedPayload.message : "ASR 流式通道失败";
        setError(message);
        if (pending) {
          isUploadingRef.current = false;
          void finalizeRestTranscript(pending.chunks, pending.inputSampleRate);
        }
      }
    },
    [finalizeRestTranscript, handleAsrStreamFinal, isActiveListenRun]
  );

  const openAsrStream = useCallback(
    (sampleRate: number) => {
      try {
        const listenRunId = listenRunIdRef.current;
        const socket = createAsrStreamSocket();
        socket.binaryType = "arraybuffer";
        socket.onopen = () => {
          if (streamSocketRef.current !== socket || !isActiveListenRun(listenRunId)) {
            return;
          }
          streamReadyRef.current = true;
          socket.send(JSON.stringify({ type: "start", language: "zh", sample_rate: sampleRate }));
        };
        socket.onmessage = (event) => {
          if (streamSocketRef.current !== socket || !isActiveListenRun(listenRunId)) {
            return;
          }
          handleAsrStreamMessage(event, listenRunId);
        };
        socket.onerror = () => {
          if (streamSocketRef.current !== socket || !isActiveListenRun(listenRunId)) {
            return;
          }
          streamReadyRef.current = false;
          setError("ASR 流式通道不可用, 将回退到整段提交");
        };
        socket.onclose = () => {
          if (streamSocketRef.current !== socket) {
            return;
          }
          streamReadyRef.current = false;
          if (isActiveListenRun(listenRunId)) {
            streamSocketRef.current = null;
          }
        };
        streamSocketRef.current = socket;
      } catch {
        streamReadyRef.current = false;
        streamSocketRef.current = null;
      }
    },
    [handleAsrStreamMessage, isActiveListenRun]
  );

  const finalizeBackendTranscript = useCallback(
    async (chunks: Float32Array[], inputSampleRate: number) => {
      const socket = streamSocketRef.current;
      if (
        socket &&
        streamReadyRef.current &&
        streamSentBytesRef.current > 0 &&
        socket.readyState === WebSocket.OPEN &&
        !isUploadingRef.current
      ) {
        isUploadingRef.current = true;
        pendingStreamFinalizeRef.current = { chunks, inputSampleRate };
        setInterimTranscript("正在识别...");
        socket.send(JSON.stringify({ type: "finalize" }));
        return;
      }
      await finalizeRestTranscript(chunks, inputSampleRate);
    },
    [finalizeRestTranscript]
  );

  const sendAsrStreamFrame = useCallback((input: Float32Array, sampleRate: number) => {
    const socket = streamSocketRef.current;
    if (!socket || !streamReadyRef.current || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const samples = downsampleBuffer(input, sampleRate, TARGET_SAMPLE_RATE);
    const pcm = encodePcm16(samples);
    if (pcm.byteLength === 0) {
      return;
    }
    socket.send(pcm);
    streamSentBytesRef.current += pcm.byteLength;
  }, []);

  const handleAudioFrame = useCallback(
    (input: Float32Array, sampleRate: number) => {
      if (providerRef.current !== "backend" || !shouldListenRef.current || isUploadingRef.current) {
        return;
      }

      let sum = 0;
      for (const sample of input) {
        sum += sample * sample;
      }
      const rms = Math.sqrt(sum / input.length);
      const now = window.performance.now();
      const isVoiceFrame = rms > SPEECH_THRESHOLD;
      let currentFrameCaptured = false;

      if (isVoiceFrame) {
        if (!recordingRef.current) {
          if (speechCandidateStartedAtRef.current === null) {
            speechCandidateStartedAtRef.current = now;
            speechCandidateVoiceFramesRef.current = 0;
            speechCandidateChunksRef.current = [];
          }
          const candidateFrame = new Float32Array(input);
          speechCandidateChunksRef.current.push(candidateFrame);
          speechCandidateLastVoiceAtRef.current = now;
          speechCandidateVoiceFramesRef.current += 1;
          if (speechCandidateVoiceFramesRef.current < 2 || now - speechCandidateStartedAtRef.current < SPEECH_START_CONFIRM_MS) {
            return;
          }
          recordingRef.current = true;
          speechStartedAtRef.current = speechCandidateStartedAtRef.current;
          captureChunksRef.current = [...speechCandidateChunksRef.current];
          for (const chunk of speechCandidateChunksRef.current) {
            sendAsrStreamFrame(chunk, sampleRate);
          }
          speechCandidateStartedAtRef.current = null;
          speechCandidateLastVoiceAtRef.current = 0;
          speechCandidateVoiceFramesRef.current = 0;
          speechCandidateChunksRef.current = [];
          currentFrameCaptured = true;
        }
        lastVoiceAtRef.current = now;
      } else if (!recordingRef.current) {
        if (
          speechCandidateStartedAtRef.current !== null &&
          now - speechCandidateLastVoiceAtRef.current <= SPEECH_START_GRACE_MS
        ) {
          speechCandidateChunksRef.current.push(new Float32Array(input));
          return;
        }
        speechCandidateStartedAtRef.current = null;
        speechCandidateLastVoiceAtRef.current = 0;
        speechCandidateVoiceFramesRef.current = 0;
        speechCandidateChunksRef.current = [];
        return;
      }

      if (!recordingRef.current) {
        return;
      }

      if (!currentFrameCaptured) {
        captureChunksRef.current.push(new Float32Array(input));
        sendAsrStreamFrame(input, sampleRate);
      }
      const speechDuration = now - speechStartedAtRef.current;
      const silenceDuration = now - lastVoiceAtRef.current;
      const shouldFinalize = speechDuration > MIN_SPEECH_MS && silenceDuration > SILENCE_MS;

      if (shouldFinalize) {
        const chunks = captureChunksRef.current;
        captureChunksRef.current = [];
        recordingRef.current = false;
        void finalizeBackendTranscript(chunks, sampleRate);
      }
    },
    [finalizeBackendTranscript, sendAsrStreamFrame]
  );

  const startBackendAudio = useCallback(
    async (label: string, providerName: string, listenRunId: number) => {
      const AudioContextClass = window.AudioContext ?? window.webkitAudioContext;
      if (!navigator.mediaDevices?.getUserMedia || !AudioContextClass) {
        setError("浏览器不支持麦克风录音, 已切换到 Web Speech API");
        startWebSpeechFallback(listenRunId);
        return;
      }

      try {
        stopBackendAudio();
        stopWebSpeechRecognition();
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        if (!isActiveListenRun(listenRunId)) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        const capability = providerCapabilitiesRef.current[providerName] ?? DEFAULT_BACKEND_CAPABILITY;
        const audioContext = new AudioContextClass({ sampleRate: TARGET_SAMPLE_RATE });
        if (capability.websocket_transport_supported && typeof WebSocket !== "undefined") {
          openAsrStream(TARGET_SAMPLE_RATE);
        }
        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          event.outputBuffer.getChannelData(0).fill(0);
          sampleRateRef.current = audioContext.sampleRate;
          handleAudioFrame(event.inputBuffer.getChannelData(0), audioContext.sampleRate);
        };

        source.connect(processor);
        processor.connect(audioContext.destination);
        audioContextRef.current = audioContext;
        mediaStreamRef.current = stream;
        sourceRef.current = source;
        processorRef.current = processor;
        providerRef.current = "backend";
        setProvider("backend");
        setProviderLabel(label);
        setProviderCapability(capability);
        setIsSupported(true);
        setIsListening(true);
        setError(null);
      } catch (audioError) {
        if (!isActiveListenRun(listenRunId)) {
          return;
        }
        setError(`后端 ASR 录音失败, 已切换到 Web Speech API: ${getAudioErrorMessage(audioError)}`);
        stopBackendAudio();
        startWebSpeechFallback(listenRunId);
      }
    },
    [handleAudioFrame, isActiveListenRun, openAsrStream, startWebSpeechFallback, stopBackendAudio, stopWebSpeechRecognition]
  );

  const startPreferredRecognition = useCallback(async (listenRunId: number) => {
    setError(null);
    try {
      const status = await fetchAsrProviders();
      if (!isActiveListenRun(listenRunId)) {
        return;
      }
      providerCapabilitiesRef.current = status.provider_capabilities ?? {};
      const primaryProvider = status.primary_provider ?? status.providers[0];
      if (primaryProvider) {
        const label = status.provider_labels[primaryProvider] ?? "后端 ASR";
        await startBackendAudio(label, primaryProvider, listenRunId);
        return;
      }
    } catch {
      if (!isActiveListenRun(listenRunId)) {
        return;
      }
      setError("无法读取后端 ASR 配置, 已切换到 Web Speech API");
    }
    startWebSpeechFallback(listenRunId);
  }, [isActiveListenRun, startBackendAudio, startWebSpeechFallback]);

  const start = useCallback(() => {
    shouldListenRef.current = true;
    listenRunIdRef.current += 1;
    void startPreferredRecognition(listenRunIdRef.current);
  }, [startPreferredRecognition]);

  const stop = useCallback(() => {
    shouldListenRef.current = false;
    listenRunIdRef.current += 1;
    stopWebSpeechRecognition();
    stopBackendAudio();
    setIsListening(false);
  }, [stopBackendAudio, stopWebSpeechRecognition]);

  useEffect(() => {
    fetchAsrProviders()
      .then((status) => {
        providerCapabilitiesRef.current = status.provider_capabilities ?? {};
        const primaryProvider = status.primary_provider ?? status.providers[0];
        if (primaryProvider) {
          setProviderLabel(status.provider_labels[primaryProvider] ?? "后端 ASR");
          setProviderCapability(providerCapabilitiesRef.current[primaryProvider] ?? DEFAULT_BACKEND_CAPABILITY);
          setIsSupported(true);
          return;
        }
        const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
        setProviderLabel("Web Speech API");
        setProviderCapability(providerCapabilitiesRef.current[WEB_SPEECH_PROVIDER] ?? DEFAULT_WEB_SPEECH_CAPABILITY);
        setIsSupported(Boolean(Recognition));
        if (!Recognition) {
          setError("当前没有可用的语音识别");
        }
      })
      .catch(() => {
        const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
        setProviderLabel("Web Speech API");
        setProviderCapability(DEFAULT_WEB_SPEECH_CAPABILITY);
        setIsSupported(Boolean(Recognition));
      });
    return () => {
      shouldListenRef.current = false;
      listenRunIdRef.current += 1;
      stopWebSpeechRecognition();
      stopBackendAudio();
    };
  }, [stopBackendAudio, stopWebSpeechRecognition]);

  return {
    isSupported,
    isListening,
    interimTranscript,
    lastFinalTranscript,
    error,
    provider,
    providerLabel,
    providerCapability,
    lastAsrMetrics,
    start,
    stop,
  };
}
