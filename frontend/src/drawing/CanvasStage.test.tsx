import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CanvasStage } from "./CanvasStage";
import type { Artwork, DrawingObject } from "../types";

function drawingObject(partial: Partial<DrawingObject> & Pick<DrawingObject, "id" | "type" | "geometry">): DrawingObject {
  return {
    name: partial.id,
    layer_id: "middle",
    group_id: null,
    semantic_tags: [],
    transform: {},
    style: { fill: "#e8f0fe", stroke: "#111827", strokeWidth: 3, opacity: 0.8 },
    z_index: 0,
    ...partial,
  };
}

function artwork(objects: DrawingObject[]): Artwork {
  return {
    id: "artwork-1",
    title: "测试作品",
    width: 640,
    height: 480,
    background: "#f8fafc",
    objects,
    created_at: "2026-06-13T00:00:00Z",
    updated_at: "2026-06-13T00:00:00Z",
  };
}

describe("CanvasStage", () => {
  it("renders a default empty canvas when artwork is not ready", () => {
    const { container } = render(<CanvasStage artwork={null} />);

    const svg = container.querySelector("svg");
    const background = container.querySelector("rect");

    expect(svg).toHaveAttribute("viewBox", "0 0 1024 768");
    expect(background).toHaveAttribute("fill", "#ffffff");
  });

  it("renders every supported editable object type with stable SVG primitives", () => {
    const objects = [
      drawingObject({ id: "circle-1", type: "circle", geometry: { cx: "100", cy: 120, radius: 30 } }),
      drawingObject({ id: "rect-1", type: "rect", geometry: { x: 10, y: 20, width: 90, height: 50, radius: 6 } }),
      drawingObject({ id: "ellipse-1", type: "ellipse", geometry: { cx: 260, cy: 80, rx: 40, ry: 20 } }),
      drawingObject({ id: "triangle-1", type: "triangle", geometry: { x: 320, y: 140, size: 80 } }),
      drawingObject({ id: "line-1", type: "line", geometry: { x1: 20, y1: 220, x2: 200, y2: 220 } }),
      drawingObject({ id: "arrow-1", type: "arrow", geometry: { x1: 220, y1: 220, x2: 360, y2: 220 } }),
      drawingObject({ id: "star-1", type: "star", geometry: { cx: 430, cy: 110, outerRadius: 40, innerRadius: 18, points: 6 } }),
      drawingObject({
        id: "polygon-1",
        type: "polygon",
        geometry: { points: [{ x: 460, y: 220 }, { x: "520", y: 230 }, { x: 500, y: 280 }] },
      }),
      drawingObject({
        id: "path-1",
        type: "path",
        geometry: { commands: [{ cmd: "M", x: 100, y: 320 }, { cmd: "Q", x1: 180, y1: 260, x: 260, y: 320 }, { cmd: "Z" }] },
      }),
      drawingObject({
        id: "bezier-1",
        type: "bezier",
        geometry: { commands: [{ cmd: "M", x: 300, y: 320 }, { cmd: "C", x1: 340, y1: 260, x2: 420, y2: 380, x: 460, y: 320 }] },
      }),
      drawingObject({ id: "image-1", type: "image", geometry: { src: "data:image/png;base64,abc", x: 10, y: 330, width: 120, height: 90 } }),
      drawingObject({
        id: "text-1",
        type: "text",
        geometry: { content: "语音标题", x: 520, y: 360, fontSize: "32" },
        style: { fill: "transparent" },
      }),
    ];

    const { container, getByText } = render(<CanvasStage artwork={artwork(objects)} />);

    expect(container.querySelector("svg")).toHaveAttribute("viewBox", "0 0 640 480");
    expect(container.querySelectorAll("circle")).toHaveLength(1);
    expect(container.querySelectorAll("rect")).toHaveLength(2);
    expect(container.querySelectorAll("ellipse")).toHaveLength(1);
    expect(container.querySelectorAll("polygon")).toHaveLength(3);
    expect(container.querySelectorAll("line")).toHaveLength(2);
    expect(container.querySelectorAll("path")).toHaveLength(3);
    expect(container.querySelectorAll("image")).toHaveLength(1);
    expect(getByText("语音标题")).toHaveAttribute("fill", "#111827");
    expect(container.querySelector("line[marker-end]")).toHaveAttribute("marker-end", "url(#arrow-head)");
    expect(container.querySelector("image")).toHaveAttribute("preserveAspectRatio", "xMidYMid slice");
  });

  it("orders objects by canvas layer and z index with runtime metadata", () => {
    const objects = [
      drawingObject({ id: "label", type: "text", layer_id: "foreground", z_index: 1, geometry: { content: "前景文字", x: 100, y: 80 } }),
      drawingObject({ id: "sky", type: "rect", layer_id: "background", z_index: 0, geometry: { x: 0, y: 0, width: 640, height: 160 } }),
      drawingObject({ id: "tree", type: "rect", layer_id: "middle", z_index: 5, geometry: { x: 260, y: 180, width: 80, height: 160 } }),
    ];

    const { container } = render(<CanvasStage artwork={artwork(objects)} />);
    const svg = container.querySelector("svg");
    const renderedIds = Array.from(container.querySelectorAll("[data-object-id]")).map((node) => node.getAttribute("data-object-id"));

    expect(svg).toHaveAttribute("data-renderer", "svg");
    expect(svg).toHaveAttribute("data-object-count", "3");
    expect(svg).toHaveAttribute("data-supports-semantic-editing", "true");
    expect(renderedIds).toEqual(["sky", "tree", "label"]);
  });
});
