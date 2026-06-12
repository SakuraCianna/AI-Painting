import type {
  Artwork,
  AsrProvidersResponse,
  AsrTranscriptionResponse,
  CommandExecutionResponse,
  LatencyMetricsSummary,
  TtsSynthesisResponse
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8080";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function createArtwork(): Promise<Artwork> {
  return requestJson<Artwork>("/api/artworks", {
    method: "POST",
    body: JSON.stringify({
      title: "语音绘图作品",
      width: 1024,
      height: 768,
      background: "#ffffff"
    })
  });
}

export function fetchArtwork(artworkId: string): Promise<Artwork> {
  return requestJson<Artwork>(`/api/artworks/${artworkId}`);
}

export function submitVoiceCommand(artworkId: string, text: string, canvasImageDataUrl?: string): Promise<CommandExecutionResponse> {
  return requestJson<CommandExecutionResponse>(`/api/artworks/${artworkId}/commands`, {
    method: "POST",
    body: JSON.stringify({
      text,
      ...(canvasImageDataUrl ? { canvas_image_data_url: canvasImageDataUrl } : {})
    })
  });
}

export function fetchAsrProviders(): Promise<AsrProvidersResponse> {
  return requestJson<AsrProvidersResponse>("/api/asr/providers");
}

export function transcribeAudio(audioDataUrl: string, language = "zh"): Promise<AsrTranscriptionResponse> {
  return requestJson<AsrTranscriptionResponse>("/api/asr/transcribe", {
    method: "POST",
    body: JSON.stringify({
      audio_data_url: audioDataUrl,
      language
    })
  });
}

export function synthesizeSpeech(text: string): Promise<TtsSynthesisResponse> {
  return requestJson<TtsSynthesisResponse>("/api/tts/synthesize", {
    method: "POST",
    body: JSON.stringify({ text })
  });
}

export function fetchLatencyMetrics(artworkId?: string): Promise<LatencyMetricsSummary> {
  const query = artworkId ? `?artwork_id=${encodeURIComponent(artworkId)}` : "";
  return requestJson<LatencyMetricsSummary>(`/api/metrics/latency${query}`);
}

export function undoArtwork(artworkId: string): Promise<{ message: string; artwork: Artwork }> {
  return requestJson<{ message: string; artwork: Artwork }>(`/api/artworks/${artworkId}/undo`, {
    method: "POST"
  });
}

export function redoArtwork(artworkId: string): Promise<{ message: string; artwork: Artwork }> {
  return requestJson<{ message: string; artwork: Artwork }>(`/api/artworks/${artworkId}/redo`, {
    method: "POST"
  });
}
