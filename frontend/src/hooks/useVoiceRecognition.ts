import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAsrProviders, transcribeAudio } from "../api";
import type { AsrTranscriptionMetrics } from "../types";

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
const SILENCE_MS = 1500;
const MIN_SPEECH_MS = 480;
const MAX_SPEECH_MS = 30000;

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

export function useVoiceRecognition({ onFinalTranscript }: UseVoiceRecognitionOptions) {
  const onFinalTranscriptRef = useRef(onFinalTranscript);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const shouldListenRef = useRef(false);
  const providerRef = useRef<VoiceProvider>("none");
  const isUploadingRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const captureChunksRef = useRef<Float32Array[]>([]);
  const recordingRef = useRef(false);
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
  const [lastAsrMetrics, setLastAsrMetrics] = useState<AsrTranscriptionMetrics | null>(null);

  useEffect(() => {
    onFinalTranscriptRef.current = onFinalTranscript;
  }, [onFinalTranscript]);

  const stopBackendAudio = useCallback(() => {
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
    isUploadingRef.current = false;
  }, []);

  const startWebSpeechFallback = useCallback(() => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      providerRef.current = "none";
      setProvider("none");
      setProviderLabel("无可用语音识别");
      setIsListening(false);
      setIsSupported(false);
      setError("当前浏览器不支持内置语音识别, 且后端 ASR 不可用");
      return;
    }

    const recognition = recognitionRef.current ?? new Recognition();
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
      setIsSupported(true);
      setError(null);
    };

    recognition.onend = () => {
      setIsListening(false);
      if (shouldListenRef.current && providerRef.current === "web_speech") {
        window.setTimeout(() => startWebSpeechFallback(), 350);
      }
    };

    recognition.onerror = (event) => {
      setError(event.message || event.error || "语音识别失败");
    };

    recognition.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result[0]?.transcript.trim() ?? "";
        if (!transcript) {
          continue;
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
    try {
      shouldListenRef.current = true;
      recognition.start();
    } catch {
      // 浏览器在已监听状态重复 start 会抛异常, 这里保持当前监听状态即可。
    }
  }, []);

  const finalizeBackendTranscript = useCallback(
    async (chunks: Float32Array[], inputSampleRate: number) => {
      if (isUploadingRef.current || chunks.length === 0) {
        return;
      }
      isUploadingRef.current = true;
      setInterimTranscript("正在识别...");
      try {
        const merged = mergeChunks(chunks);
        const samples = downsampleBuffer(merged, inputSampleRate, TARGET_SAMPLE_RATE);
        const wavBytes = encodeWav(samples, TARGET_SAMPLE_RATE);
        const audioDataUrl = `data:audio/wav;base64,${bytesToBase64(wavBytes)}`;
        const response = await transcribeAudio(audioDataUrl, "zh");
        const text = response.text.trim();
        if (!text) {
          throw new Error("ASR 没有返回文本");
        }
        setProviderLabel(response.provider_label);
        setLastAsrMetrics(response.metrics);
        setLastFinalTranscript(text);
        setInterimTranscript("");
        onFinalTranscriptRef.current(text, response.metrics);
      } catch (backendError) {
        setError(`后端 ASR 不可用, 已切换到 Web Speech API: ${getAudioErrorMessage(backendError)}`);
        stopBackendAudio();
        if (shouldListenRef.current) {
          startWebSpeechFallback();
        }
      } finally {
        isUploadingRef.current = false;
      }
    },
    [startWebSpeechFallback, stopBackendAudio]
  );

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

      if (rms > SPEECH_THRESHOLD) {
        if (!recordingRef.current) {
          recordingRef.current = true;
          captureChunksRef.current = [];
          speechStartedAtRef.current = now;
        }
        lastVoiceAtRef.current = now;
      }

      if (!recordingRef.current) {
        return;
      }

      captureChunksRef.current.push(new Float32Array(input));
      const speechDuration = now - speechStartedAtRef.current;
      const silenceDuration = now - lastVoiceAtRef.current;
      const shouldFinalize =
        (speechDuration > MIN_SPEECH_MS && silenceDuration > SILENCE_MS) || speechDuration > MAX_SPEECH_MS;

      if (shouldFinalize) {
        const chunks = captureChunksRef.current;
        captureChunksRef.current = [];
        recordingRef.current = false;
        void finalizeBackendTranscript(chunks, sampleRate);
      }
    },
    [finalizeBackendTranscript]
  );

  const startBackendAudio = useCallback(
    async (label: string) => {
      const AudioContextClass = window.AudioContext ?? window.webkitAudioContext;
      if (!navigator.mediaDevices?.getUserMedia || !AudioContextClass) {
        setError("浏览器不支持麦克风录音, 已切换到 Web Speech API");
        startWebSpeechFallback();
        return;
      }

      try {
        stopBackendAudio();
        recognitionRef.current?.stop();
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
          },
        });
        if (!shouldListenRef.current) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        const audioContext = new AudioContextClass({ sampleRate: TARGET_SAMPLE_RATE });
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
        setIsSupported(true);
        setIsListening(true);
        setError(null);
      } catch (audioError) {
        setError(`后端 ASR 录音失败, 已切换到 Web Speech API: ${getAudioErrorMessage(audioError)}`);
        stopBackendAudio();
        startWebSpeechFallback();
      }
    },
    [handleAudioFrame, startWebSpeechFallback, stopBackendAudio]
  );

  const startPreferredRecognition = useCallback(async () => {
    shouldListenRef.current = true;
    setError(null);
    try {
      const status = await fetchAsrProviders();
      const primaryProvider = status.primary_provider ?? status.providers[0];
      if (primaryProvider) {
        const label = status.provider_labels[primaryProvider] ?? "后端 ASR";
        await startBackendAudio(label);
        return;
      }
    } catch {
      setError("无法读取后端 ASR 配置, 已切换到 Web Speech API");
    }
    startWebSpeechFallback();
  }, [startBackendAudio, startWebSpeechFallback]);

  const start = useCallback(() => {
    shouldListenRef.current = true;
    void startPreferredRecognition();
  }, [startPreferredRecognition]);

  const stop = useCallback(() => {
    shouldListenRef.current = false;
    recognitionRef.current?.stop();
    stopBackendAudio();
    setIsListening(false);
  }, [stopBackendAudio]);

  useEffect(() => {
    fetchAsrProviders()
      .then((status) => {
        const primaryProvider = status.primary_provider ?? status.providers[0];
        if (primaryProvider) {
          setProviderLabel(status.provider_labels[primaryProvider] ?? "后端 ASR");
          setIsSupported(true);
          return;
        }
        const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
        setProviderLabel("Web Speech API");
        setIsSupported(Boolean(Recognition));
        if (!Recognition) {
          setError("当前没有可用的语音识别");
        }
      })
      .catch(() => {
        const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
        setProviderLabel("Web Speech API");
        setIsSupported(Boolean(Recognition));
      });
    return () => {
      shouldListenRef.current = false;
      recognitionRef.current?.stop();
      stopBackendAudio();
    };
  }, [stopBackendAudio]);

  return {
    isSupported,
    isListening,
    interimTranscript,
    lastFinalTranscript,
    error,
    provider,
    providerLabel,
    lastAsrMetrics,
    start,
    stop,
  };
}
