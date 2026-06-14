import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  createArtwork,
  fetchArtwork,
  redoArtwork,
  submitVoiceCommand,
  synthesizeSpeech,
  transcribeAudio,
  undoArtwork,
} from "./api";

const fetchMock = vi.fn();

function mockJsonResponse(body: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
    text: vi.fn().mockResolvedValue(typeof body === "string" ? body : JSON.stringify(body)),
  } as unknown as Response;
}

describe("api", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("creates an artwork with the default voice canvas payload", async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ id: "artwork-1" }));

    await expect(createArtwork()).resolves.toEqual({ id: "artwork-1" });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8084/api/artworks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "语音绘图作品",
          width: 1024,
          height: 768,
          background: "#ffffff",
        }),
      })
    );
  });

  it("submits voice commands with an optional canvas snapshot", async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse({ message: "ok" }));

    await submitVoiceCommand("artwork-1", "精修我的图片", "data:image/png;base64,abc");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8084/api/artworks/artwork-1/commands",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          text: "精修我的图片",
          canvas_image_data_url: "data:image/png;base64,abc",
        }),
      })
    );
  });

  it("calls read-only and action endpoints with the expected paths", async () => {
    fetchMock.mockResolvedValue(mockJsonResponse({ ok: true }));

    await fetchArtwork("artwork-1");
    await transcribeAudio("data:audio/wav;base64,abc", "zh");
    await synthesizeSpeech("已完成");
    await undoArtwork("artwork-1");
    await redoArtwork("artwork-1");

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "http://127.0.0.1:8084/api/artworks/artwork-1",
      "http://127.0.0.1:8084/api/asr/transcribe",
      "http://127.0.0.1:8084/api/tts/synthesize",
      "http://127.0.0.1:8084/api/artworks/artwork-1/undo",
      "http://127.0.0.1:8084/api/artworks/artwork-1/redo",
    ]);
  });

  it("throws backend error text when the response is not ok", async () => {
    fetchMock.mockResolvedValueOnce(mockJsonResponse("backend failed", false, 500));

    await expect(fetchArtwork("missing")).rejects.toThrow("backend failed");
  });
});
