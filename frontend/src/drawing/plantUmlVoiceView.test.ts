import { describe, expect, it } from "vitest";
import { extractPlantUmlLabels, parsePlantUmlViewCommand, resolvePlantUmlVoiceView } from "./plantUmlVoiceView";
import type { Artwork, DrawingObject } from "../types";

const architectureSource = `@startuml
component "前端" as frontend
component "后端" as backend
component "支付服务" as payment
database "数据库" as database
frontend --> backend
backend --> payment
backend --> database
@enduml`;

function plantUmlObject(): DrawingObject {
  return {
    id: "plantuml-component",
    type: "plantuml",
    name: "系统架构图",
    layer_id: "middle",
    group_id: "plantuml-component",
    semantic_tags: ["plantuml", "plantuml.component", "system_architecture"],
    transform: {},
    geometry: {
      x: 48,
      y: 48,
      width: 928,
      height: 672,
      title: "系统架构图",
      diagramType: "component",
      source: architectureSource,
      src: "data:image/svg+xml;base64,PHN2Zy8+",
    },
    style: { opacity: 1 },
    z_index: 10,
  };
}

function artwork(objects: DrawingObject[]): Artwork {
  return {
    id: "artwork-1",
    title: "语音绘图作品",
    width: 1024,
    height: 768,
    background: "#ffffff",
    objects,
    created_at: "2026-06-13T00:00:00Z",
    updated_at: "2026-06-13T00:00:00Z",
  };
}

describe("plantUmlVoiceView", () => {
  it("parses voice-only PlantUML view commands without catching source edit commands", () => {
    expect(parsePlantUmlViewCommand("放大这张架构图")).toMatchObject({ action: "zoom_in", diagramHint: "component" });
    expect(parsePlantUmlViewCommand("聚焦支付模块")).toMatchObject({ action: "focus", targetLabel: "支付" });
    expect(parsePlantUmlViewCommand("还原图表视图")).toMatchObject({ action: "reset" });
    expect(parsePlantUmlViewCommand("把流程图里的ASR识别节点改成语音识别")).toBeNull();
    expect(parsePlantUmlViewCommand("放大图片")).toBeNull();
    expect(parsePlantUmlViewCommand("把这张图放大一点")).toBeNull();
    expect(parsePlantUmlViewCommand("还原图片")).toBeNull();
  });

  it("extracts focus labels from PlantUML source declarations", () => {
    expect(extractPlantUmlLabels(architectureSource)).toEqual(["前端", "后端", "支付服务", "数据库"]);
    expect(extractPlantUmlLabels("@startuml\nclass DrawingObject {\n  +geometry\n}\n@enduml")).toEqual(["DrawingObject"]);
  });

  it("resolves a payment module focus view for the active PlantUML layer", () => {
    const result = resolvePlantUmlVoiceView("聚焦支付模块", artwork([plantUmlObject()]), null);

    expect(result).toMatchObject({
      action: "focus",
      objectId: "plantuml-component",
      targetLabel: "支付服务",
      focusFound: true,
      message: "已聚焦支付服务模块视图",
    });
    expect(result?.view).toMatchObject({
      objectId: "plantuml-component",
      mode: "focus",
      scale: 2.2,
      focusLabel: "支付服务",
    });
    expect(result?.view?.focusBox?.width).toBeGreaterThan(0);
  });

  it("prefers the PlantUML layer whose source contains the requested focus label", () => {
    const unrelatedPlantUml = {
      ...plantUmlObject(),
      id: "plantuml-flowchart",
      name: "流程图",
      semantic_tags: ["plantuml", "plantuml.activity", "flowchart"],
      geometry: {
        ...plantUmlObject().geometry,
        diagramType: "activity",
        title: "流程图",
        source: "@startuml\n:开始;\n:结束;\n@enduml",
      },
      z_index: 99,
    };

    const result = resolvePlantUmlVoiceView("聚焦支付模块", artwork([unrelatedPlantUml, plantUmlObject()]), null);

    expect(result?.objectId).toBe("plantuml-component");
    expect(result?.focusFound).toBe(true);
  });
});
