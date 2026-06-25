import type { Artwork } from "../types";

function createAbortError(): DOMException {
  return new DOMException("操作已取消", "AbortError");
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw createAbortError();
  }
}

function downloadBlob(blob: Blob, filename: string, signal?: AbortSignal): void {
  throwIfAborted(signal);
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  try {
    throwIfAborted(signal);
    link.href = url;
    link.download = filename;
    link.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function svgToPngDataUrl(svgId: string, signal?: AbortSignal): Promise<string> {
  throwIfAborted(signal);
  const svg = document.getElementById(svgId);
  if (!(svg instanceof SVGSVGElement)) {
    throw new Error("没有找到可导出的画布");
  }

  const viewBox = svg.viewBox.baseVal;
  const serialized = new XMLSerializer().serializeToString(svg);
  const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  return new Promise<string>((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      signal?.removeEventListener("abort", abortExport);
      URL.revokeObjectURL(url);
    };
    const rejectOnce = (error: Error | DOMException) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      reject(error);
    };
    const resolveOnce = (dataUrl: string) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(dataUrl);
    };
    const abortExport = () => rejectOnce(createAbortError());

    if (signal?.aborted) {
      abortExport();
      return;
    }
    signal?.addEventListener("abort", abortExport, { once: true });

    const image = new Image();
    image.onload = () => {
      if (signal?.aborted) {
        abortExport();
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = viewBox.width || svg.clientWidth;
      canvas.height = viewBox.height || svg.clientHeight;
      const context = canvas.getContext("2d");
      if (!context) {
        rejectOnce(new Error("浏览器无法创建 PNG 导出上下文"));
        return;
      }
      context.drawImage(image, 0, 0);
      resolveOnce(canvas.toDataURL("image/png"));
    };
    image.onerror = () => {
      rejectOnce(new Error("PNG 导出失败"));
    };
    image.src = url;
  });
}

export async function exportSvgAsPng(svgId: string, filename: string, signal?: AbortSignal): Promise<void> {
  const dataUrl = await svgToPngDataUrl(svgId, signal);
  throwIfAborted(signal);
  const link = document.createElement("a");
  link.href = dataUrl;
  link.download = filename;
  link.click();
}

export function exportSvgFile(svgId: string, filename: string, signal?: AbortSignal): void {
  throwIfAborted(signal);
  const svg = document.getElementById(svgId);
  if (!(svg instanceof SVGSVGElement)) {
    throw new Error("没有找到可导出的画布");
  }

  const serialized = new XMLSerializer().serializeToString(svg);
  downloadBlob(new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }), filename, signal);
}

export function exportArtworkJson(artwork: Artwork, filename: string, signal?: AbortSignal): void {
  throwIfAborted(signal);
  const serialized = JSON.stringify(artwork, null, 2);
  downloadBlob(new Blob([serialized], { type: "application/json;charset=utf-8" }), filename, signal);
}
