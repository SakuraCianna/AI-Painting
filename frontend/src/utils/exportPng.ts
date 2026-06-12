export async function exportSvgAsPng(svgId: string, filename: string): Promise<void> {
  const svg = document.getElementById(svgId);
  if (!(svg instanceof SVGSVGElement)) {
    throw new Error("没有找到可导出的画布");
  }

  const viewBox = svg.viewBox.baseVal;
  const serialized = new XMLSerializer().serializeToString(svg);
  const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  await new Promise<void>((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = viewBox.width || svg.clientWidth;
      canvas.height = viewBox.height || svg.clientHeight;
      const context = canvas.getContext("2d");
      if (!context) {
        URL.revokeObjectURL(url);
        reject(new Error("浏览器无法创建 PNG 导出上下文"));
        return;
      }
      context.drawImage(image, 0, 0);
      URL.revokeObjectURL(url);
      const link = document.createElement("a");
      link.href = canvas.toDataURL("image/png");
      link.download = filename;
      link.click();
      resolve();
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("PNG 导出失败"));
    };
    image.src = url;
  });
}
