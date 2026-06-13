import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { exportArtworkJson, exportSvgAsPng, exportSvgFile, svgToPngDataUrl } from "./exportPng";

class LoadingImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  set src(_: string) {
    window.setTimeout(() => this.onload?.(), 0);
  }
}

class FailingImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  set src(_: string) {
    window.setTimeout(() => this.onerror?.(), 0);
  }
}

function appendSvg() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("id", "voice-canvas-svg");
  svg.setAttribute("viewBox", "0 0 320 180");
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", "160");
  circle.setAttribute("cy", "90");
  circle.setAttribute("r", "40");
  svg.appendChild(circle);
  Object.defineProperty(svg, "viewBox", {
    configurable: true,
    value: { baseVal: { width: 320, height: 180 } },
  });
  document.body.appendChild(svg);
}

describe("exportPng", () => {
  const createObjectURL = vi.fn(() => "blob:voice-canvas");
  const revokeObjectURL = vi.fn();
  const drawImage = vi.fn();

  beforeEach(() => {
    document.body.innerHTML = "";
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    drawImage.mockClear();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    vi.stubGlobal("Image", LoadingImage);
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,exported");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("rejects when the SVG canvas cannot be found", async () => {
    await expect(svgToPngDataUrl("missing")).rejects.toThrow("没有找到可导出的画布");
  });

  it("serializes SVG into a PNG data URL and releases the blob URL", async () => {
    appendSvg();

    await expect(svgToPngDataUrl("voice-canvas-svg")).resolves.toBe("data:image/png;base64,exported");

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(drawImage).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:voice-canvas");
  });

  it("rejects when the browser cannot create a 2D canvas context", async () => {
    appendSvg();
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValueOnce(null);

    await expect(svgToPngDataUrl("voice-canvas-svg")).rejects.toThrow("浏览器无法创建 PNG 导出上下文");
  });

  it("rejects image loading failures", async () => {
    appendSvg();
    vi.stubGlobal("Image", FailingImage);

    await expect(svgToPngDataUrl("voice-canvas-svg")).rejects.toThrow("PNG 导出失败");
  });

  it("downloads the generated PNG with the requested filename", async () => {
    appendSvg();
    let clickedLink: HTMLAnchorElement | null = null;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function handleClick(this: HTMLAnchorElement) {
      clickedLink = this;
    });

    await exportSvgAsPng("voice-canvas-svg", "作品.png");

    expect(clickedLink).toHaveAttribute("href", "data:image/png;base64,exported");
    expect(clickedLink).toHaveAttribute("download", "作品.png");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("downloads serialized SVG with the requested filename", () => {
    appendSvg();
    const clickedLinks: HTMLAnchorElement[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function handleClick(this: HTMLAnchorElement) {
      clickedLinks.push(this);
    });

    exportSvgFile("voice-canvas-svg", "作品.svg");

    const downloadedLink = clickedLinks[0];
    expect(downloadedLink.download).toBe("作品.svg");
    expect(downloadedLink.href).toContain("blob:voice-canvas");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:voice-canvas");
  });

  it("downloads project JSON with artwork data", () => {
    const clickedLinks: HTMLAnchorElement[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function handleClick(this: HTMLAnchorElement) {
      clickedLinks.push(this);
    });

    exportArtworkJson(
      {
        id: "artwork-1",
        title: "作品",
        width: 320,
        height: 180,
        background: "#ffffff",
        objects: [],
        created_at: "2026-06-13T00:00:00Z",
        updated_at: "2026-06-13T00:00:00Z",
      },
      "作品.json"
    );

    const downloadedLink = clickedLinks[0];
    expect(downloadedLink.download).toBe("作品.json");
    expect(downloadedLink.href).toContain("blob:voice-canvas");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:voice-canvas");
  });
});
