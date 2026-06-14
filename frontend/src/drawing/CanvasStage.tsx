import { memo, useMemo } from "react";
import type { Artwork, DrawingObject } from "../types";
import { getOrderedCanvasObjects, SVG_CANVAS_RUNTIME } from "./canvasRuntime";

interface CanvasStageProps {
  artwork: Artwork | null;
}

function numeric(value: unknown, fallback: number): number {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    return Number(value);
  }
  return fallback;
}

function starPoints(cx: number, cy: number, outerRadius: number, innerRadius: number, points: number): string {
  const result: string[] = [];
  for (let index = 0; index < points * 2; index += 1) {
    const radius = index % 2 === 0 ? outerRadius : innerRadius;
    const angle = -Math.PI / 2 + (index * Math.PI) / points;
    result.push(`${cx + Math.cos(angle) * radius},${cy + Math.sin(angle) * radius}`);
  }
  return result.join(" ");
}

function trianglePoints(x: number, y: number, size: number): string {
  const height = Math.round(size * 0.86);
  return `${x},${y - height / 2} ${x - size / 2},${y + height / 2} ${x + size / 2},${y + height / 2}`;
}

function pointList(value: unknown, fallback: string): string {
  if (!Array.isArray(value)) {
    return fallback;
  }
  return value
    .map((point) => {
      if (!point || typeof point !== "object") {
        return null;
      }
      const source = point as Record<string, number | string>;
      return `${numeric(source.x, 0)},${numeric(source.y, 0)}`;
    })
    .filter(Boolean)
    .join(" ");
}

function commandValue(command: Record<string, number | string>, key: string): string {
  return String(numeric(command[key], 0));
}

function pathData(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  if (!Array.isArray(value)) {
    return fallback;
  }
  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return "";
      }
      const command = item as Record<string, number | string>;
      const cmd = String(command.cmd ?? "").toUpperCase();
      if (cmd === "M" || cmd === "L") {
        return `${cmd} ${commandValue(command, "x")} ${commandValue(command, "y")}`;
      }
      if (cmd === "C") {
        return `C ${commandValue(command, "x1")} ${commandValue(command, "y1")} ${commandValue(command, "x2")} ${commandValue(command, "y2")} ${commandValue(command, "x")} ${commandValue(command, "y")}`;
      }
      if (cmd === "Q") {
        return `Q ${commandValue(command, "x1")} ${commandValue(command, "y1")} ${commandValue(command, "x")} ${commandValue(command, "y")}`;
      }
      if (cmd === "Z") {
        return "Z";
      }
      return "";
    })
    .filter(Boolean)
    .join(" ");
}

function renderObject(object: DrawingObject) {
  const fill = object.style.fill ?? "transparent";
  const stroke = object.style.stroke ?? "#111827";
  const strokeWidth = object.style.strokeWidth ?? 2;
  const opacity = object.style.opacity ?? 1;
  const objectAttrs = { "data-object-id": object.id, "data-layer-id": object.layer_id };
  const common = { fill, stroke, strokeWidth, opacity, ...objectAttrs };

  if (object.type === "circle") {
    return (
      <circle
        key={object.id}
        cx={numeric(object.geometry.cx, 512)}
        cy={numeric(object.geometry.cy, 384)}
        r={numeric(object.geometry.radius, 80)}
        {...common}
      />
    );
  }

  if (object.type === "rect") {
    return (
      <rect
        key={object.id}
        x={numeric(object.geometry.x, 360)}
        y={numeric(object.geometry.y, 300)}
        width={numeric(object.geometry.width, 220)}
        height={numeric(object.geometry.height, 140)}
        rx={numeric(object.geometry.radius, 8)}
        {...common}
      />
    );
  }

  if (object.type === "ellipse") {
    return (
      <ellipse
        key={object.id}
        cx={numeric(object.geometry.cx, 512)}
        cy={numeric(object.geometry.cy, 384)}
        rx={numeric(object.geometry.rx, 140)}
        ry={numeric(object.geometry.ry, 80)}
        {...common}
      />
    );
  }

  if (object.type === "triangle") {
    return (
      <polygon
        key={object.id}
        points={trianglePoints(numeric(object.geometry.x, 512), numeric(object.geometry.y, 384), numeric(object.geometry.size, 180))}
        {...common}
      />
    );
  }

  if (object.type === "line" || object.type === "arrow") {
    return (
      <line
        key={object.id}
        x1={numeric(object.geometry.x1, 380)}
        y1={numeric(object.geometry.y1, 464)}
        x2={numeric(object.geometry.x2, 644)}
        y2={numeric(object.geometry.y2, 304)}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        opacity={opacity}
        markerEnd={object.type === "arrow" ? "url(#arrow-head)" : undefined}
        strokeLinecap="round"
        {...objectAttrs}
      />
    );
  }

  if (object.type === "star") {
    return (
      <polygon
        key={object.id}
        points={starPoints(
          numeric(object.geometry.cx, 512),
          numeric(object.geometry.cy, 384),
          numeric(object.geometry.outerRadius, 80),
          numeric(object.geometry.innerRadius, 36),
          numeric(object.geometry.points, 5)
        )}
        {...common}
      />
    );
  }

  if (object.type === "polygon") {
    return (
      <polygon
        key={object.id}
        points={pointList(object.geometry.points, "512,284 607,353 571,465 453,465 417,353")}
        {...common}
      />
    );
  }

  if (object.type === "path" || object.type === "bezier") {
    return (
      <path
        key={object.id}
        d={pathData(object.geometry.commands ?? object.geometry.d, "M 332 424 C 432 254 597 534 692 344")}
        fill={object.type === "bezier" ? "none" : fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        opacity={opacity}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    );
  }

  if (object.type === "image") {
    const href = typeof object.geometry.src === "string" ? object.geometry.src : "";
    return (
      <image
        key={object.id}
        href={href}
        x={numeric(object.geometry.x, 256)}
        y={numeric(object.geometry.y, 128)}
        width={numeric(object.geometry.width, 512)}
        height={numeric(object.geometry.height, 512)}
        opacity={opacity}
        preserveAspectRatio={String(object.geometry.preserveAspectRatio ?? "xMidYMid slice")}
        {...objectAttrs}
      />
    );
  }

  return (
    <text
      key={object.id}
      x={numeric(object.geometry.x, 512)}
      y={numeric(object.geometry.y, 384)}
      fill={fill === "transparent" ? "#111827" : fill}
      fontSize={numeric(object.geometry.fontSize, 48)}
      textAnchor="middle"
      dominantBaseline="middle"
      opacity={opacity}
      {...objectAttrs}
    >
      {String(object.geometry.content ?? "语音文字")}
    </text>
  );
}

export const CanvasStage = memo(function CanvasStage({ artwork }: CanvasStageProps) {
  const width = artwork?.width ?? 1024;
  const height = artwork?.height ?? 768;
  const background = artwork?.background ?? "#ffffff";
  const orderedObjects = useMemo(() => getOrderedCanvasObjects(artwork?.objects ?? []), [artwork?.objects]);
  const renderedObjects = useMemo(() => orderedObjects.map(renderObject), [orderedObjects]);

  return (
    <div className="canvas-shell" aria-label="语音绘图画布">
      <svg
        id="voice-canvas-svg"
        className="drawing-canvas"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={artwork?.title ?? "语音绘图作品"}
        data-renderer={SVG_CANVAS_RUNTIME.renderer}
        data-object-count={orderedObjects.length}
        data-supports-semantic-editing={String(SVG_CANVAS_RUNTIME.supportsSemanticEditing)}
      >
        <defs>
          <marker id="arrow-head" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
            <path d="M2,2 L10,6 L2,10 Z" fill="#111827" />
          </marker>
        </defs>
        <rect x="0" y="0" width={width} height={height} fill={background} />
        {renderedObjects}
      </svg>
    </div>
  );
});
