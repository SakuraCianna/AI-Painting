import type { Artwork, DrawingObject } from "../types";

export type PlantUmlViewAction = "zoom_in" | "zoom_out" | "reset" | "focus";
type PlantUmlDiagramHint = "activity" | "class" | "component" | "er" | "gantt" | "org" | "sequence" | "swimlane";

export interface PlantUmlFocusBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlantUmlLayerView {
  objectId: string;
  mode: "zoom" | "focus";
  scale: number;
  focusLabel?: string;
  focusBox?: PlantUmlFocusBox;
}

export interface PlantUmlViewCommand {
  action: PlantUmlViewAction;
  targetLabel?: string;
  diagramHint?: PlantUmlDiagramHint;
}

export interface PlantUmlViewResult {
  action: PlantUmlViewAction;
  view: PlantUmlLayerView | null;
  objectId?: string;
  targetLabel?: string;
  message: string;
  focusFound: boolean;
}

interface PlantUmlFocusMatch {
  label: string;
  box: PlantUmlFocusBox;
}

const MAX_VIEW_SCALE = 2.6;
const ZOOM_STEP = 0.45;
const FOCUS_SCALE = 2.2;
const GENERIC_FOCUS_TARGETS = new Set(["图", "图表", "图层", "架构图", "系统架构图", "当前图", "这张图", "模块", "节点", "实体", "组件", "服务"]);
const DIAGRAM_REFERENCE_PATTERN =
  /(plantuml|图表|图层|系统架构|技术架构|应用架构|架构图|结构图|流程图|er图|er图|实体关系|时序图|序列图|调用链|类图|uml图|uml|组织结构|组织架构|团队架构|团队结构|甘特图|排期图|项目排期|进度计划|泳道图)/i;
const FOCUS_ELEMENT_PATTERN = /(模块|节点|实体|组件|服务|泳道|任务|角色|类)(?:$|[，。,.]|视图|区域|部分)/;
const NON_DIAGRAM_IMAGE_PATTERN = /(图片|图像|照片|画面|作品|头像|肖像|生成图)/;

function compactText(value: string): string {
  return value.replace(/\s+/g, "");
}

function cleanTargetLabel(value: string): string | null {
  const target = value
    .replace(/^(这张|当前|这个|该|图里|图表里|架构图里|系统架构图里|PlantUML里)/i, "")
    .replace(/(模块|节点|实体|组件|服务|区域|部分|图层|图表|架构图|系统架构图)$/i, "")
    .trim();
  if (!target || GENERIC_FOCUS_TARGETS.has(target)) {
    return null;
  }
  return target;
}

function getDiagramHint(text: string): PlantUmlDiagramHint | undefined {
  const lowerText = text.toLowerCase();
  if (/(系统架构|技术架构|应用架构|架构图|结构图)/.test(text)) {
    return "component";
  }
  if (/(er图|er图|实体关系)/i.test(lowerText)) {
    return "er";
  }
  if (/流程图/.test(text)) {
    return "activity";
  }
  if (/(时序图|序列图|调用链)/.test(text)) {
    return "sequence";
  }
  if (/(类图|uml图|uml)/i.test(lowerText)) {
    return "class";
  }
  if (/(组织结构|组织架构|团队架构|团队结构)/.test(text)) {
    return "org";
  }
  if (/(甘特图|排期图|项目排期|进度计划)/.test(text)) {
    return "gantt";
  }
  if (/泳道图/.test(text)) {
    return "swimlane";
  }
  return undefined;
}

function hasDiagramReference(text: string): boolean {
  return DIAGRAM_REFERENCE_PATTERN.test(text);
}

function hasFocusElementReference(text: string): boolean {
  return FOCUS_ELEMENT_PATTERN.test(text);
}

function extractFocusTarget(text: string): string | null {
  const hasExplicitDiagramReference = hasDiagramReference(text);
  const hasExplicitElementReference = hasFocusElementReference(text);
  const focusPatterns = [
    /(?:聚焦|定位到|查看|看一下|看看|放大到|拉近到)([\p{Script=Han}A-Za-z0-9_-]{1,32}?)(模块|节点|实体|组件|服务|泳道|任务|角色|类|区域|部分)?(?:$|[，。,.])/u,
    /(?:把|将)([\p{Script=Han}A-Za-z0-9_-]{1,32}?)(模块|节点|实体|组件|服务|泳道|任务|角色|类)(?:放大|聚焦|拉近|居中)(?:$|[，。,.])/u,
  ];
  for (const pattern of focusPatterns) {
    const match = text.match(pattern);
    const suffix = match?.[2] ?? "";
    if (!hasExplicitDiagramReference && !suffix && !hasExplicitElementReference) {
      continue;
    }
    const target = match?.[1] ? cleanTargetLabel(match[1]) : null;
    if (target) {
      return target;
    }
  }
  return null;
}

export function parsePlantUmlViewCommand(rawText: string): PlantUmlViewCommand | null {
  const text = compactText(rawText);
  if (!text) {
    return null;
  }

  const diagramHint = getDiagramHint(text);
  const focusTarget = extractFocusTarget(text);
  if (focusTarget) {
    return { action: "focus", targetLabel: focusTarget, diagramHint };
  }

  if (!hasDiagramReference(text)) {
    return null;
  }
  if (NON_DIAGRAM_IMAGE_PATTERN.test(text) && !diagramHint && !hasFocusElementReference(text)) {
    return null;
  }
  if (/(还原|重置|复位|看全|看完整|显示全图)/.test(text) && /(视图|图表|图层|架构图|结构图|plantuml)/i.test(text)) {
    return { action: "reset", diagramHint };
  }
  if (/(缩小|退远|拉远)/.test(text)) {
    return { action: "zoom_out", diagramHint };
  }
  if (/(放大|看大|拉近|靠近|扩大)/.test(text) && !/(改大|变大|调大)/.test(text)) {
    return { action: "zoom_in", diagramHint };
  }
  return null;
}

function geometryNumber(object: DrawingObject, key: string, fallback: number): number {
  const value = object.geometry[key];
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : fallback;
  }
  return fallback;
}

function plantUmlTitle(object: DrawingObject): string {
  if (typeof object.geometry.title === "string" && object.geometry.title.trim() !== "") {
    return object.geometry.title;
  }
  return object.name || "PlantUML 图层";
}

function matchesDiagramHint(object: DrawingObject, hint: PlantUmlDiagramHint): boolean {
  return object.geometry.diagramType === hint || object.semantic_tags.includes(`plantuml.${hint}`) || (hint === "component" && object.semantic_tags.includes("system_architecture"));
}

function objectHasMatchingLabel(object: DrawingObject, targetLabel: string | undefined): boolean {
  if (!targetLabel || typeof object.geometry.source !== "string") {
    return false;
  }
  const target = normalizeLabel(targetLabel);
  return extractPlantUmlLabels(object.geometry.source).some((label) => {
    const normalized = normalizeLabel(label);
    return normalized === target || normalized.includes(target) || target.includes(normalized);
  });
}

function findPlantUmlObject(artwork: Artwork | null, hint: PlantUmlDiagramHint | undefined, targetLabel?: string): DrawingObject | null {
  const objects = artwork?.objects.filter((object) => object.type === "plantuml") ?? [];
  if (objects.length === 0) {
    return null;
  }
  const hintedObjects = hint ? objects.filter((object) => matchesDiagramHint(object, hint)) : objects;
  const labelMatchedObject = hintedObjects.find((object) => objectHasMatchingLabel(object, targetLabel));
  if (labelMatchedObject) {
    return labelMatchedObject;
  }
  if (hint && hintedObjects.length > 0) {
    return hintedObjects[0];
  }
  return [...objects].sort((left, right) => right.z_index - left.z_index)[0];
}

function normalizeLabel(value: string): string {
  return compactText(value).toLowerCase();
}

function stripPlantUmlLabel(value: string): string {
  return value.replace(/\s+as\s+\S+$/i, "").replace(/[{}[\];]/g, "").trim();
}

export function extractPlantUmlLabels(source: string): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  const addLabel = (rawLabel: string | undefined) => {
    if (!rawLabel) {
      return;
    }
    const label = stripPlantUmlLabel(rawLabel);
    const normalized = normalizeLabel(label);
    if (!label || seen.has(normalized)) {
      return;
    }
    labels.push(label);
    seen.add(normalized);
  };

  for (const line of source.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("'") || /^(@|skinparam|title|start|stop|printscale|project\b)/i.test(trimmed)) {
      continue;
    }
    addLabel(trimmed.match(/^(?:component|database|queue|entity|class|interface|enum)\s+"([^"]+)"/i)?.[1]);
    addLabel(trimmed.match(/^(?:component|database|queue|entity|class|interface|enum)\s+([^"\s{#-][^{#]+?)(?:\s+as\s+\S+|\s*\{|$)/i)?.[1]);
    addLabel(trimmed.match(/^(?:actor|participant|boundary|control|database|queue|collections)\s+"([^"]+)"/i)?.[1]);
    addLabel(trimmed.match(/^(?:actor|participant|boundary|control|database|queue|collections)\s+([^":#-][^-:]+?)(?:\s+as\s+\S+)?$/i)?.[1]);
    addLabel(trimmed.match(/^:([^;]+);$/)?.[1]);
    addLabel(trimmed.match(/^\|([^|]+)\|$/)?.[1]);
    addLabel(trimmed.match(/^\[([^\]]+)\]/)?.[1]);
    addLabel(trimmed.match(/^\*+\s+(.+)$/)?.[1]);
  }
  return labels;
}

function estimateFocusBox(object: DrawingObject, targetLabel: string): PlantUmlFocusMatch | null {
  const source = typeof object.geometry.source === "string" ? object.geometry.source : "";
  const labels = extractPlantUmlLabels(source);
  const target = normalizeLabel(targetLabel);
  const index = labels.findIndex((label) => {
    const normalized = normalizeLabel(label);
    return normalized === target || normalized.includes(target) || target.includes(normalized);
  });
  if (index < 0) {
    return null;
  }

  const x = geometryNumber(object, "x", 48);
  const y = geometryNumber(object, "y", 48);
  const width = geometryNumber(object, "width", 928);
  const height = geometryNumber(object, "height", 672);
  const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(labels.length))));
  const rows = Math.max(1, Math.ceil(labels.length / columns));
  const cellWidth = width / columns;
  const cellHeight = height / rows;
  const column = index % columns;
  const row = Math.floor(index / columns);
  const boxWidth = Math.max(96, cellWidth * 0.72);
  const boxHeight = Math.max(64, cellHeight * 0.62);

  return {
    label: labels[index],
    box: {
      x: Number((x + column * cellWidth + (cellWidth - boxWidth) / 2).toFixed(2)),
      y: Number((y + row * cellHeight + (cellHeight - boxHeight) / 2).toFixed(2)),
      width: Number(boxWidth.toFixed(2)),
      height: Number(boxHeight.toFixed(2)),
    },
  };
}

function nextZoomScale(currentView: PlantUmlLayerView | null, objectId: string, direction: "in" | "out"): number {
  const baseScale = currentView?.objectId === objectId ? currentView.scale : 1;
  const nextScale = direction === "in" ? baseScale + ZOOM_STEP : baseScale - ZOOM_STEP;
  return Number(Math.min(MAX_VIEW_SCALE, Math.max(1, nextScale)).toFixed(2));
}

export function resolvePlantUmlVoiceView(rawText: string, artwork: Artwork | null, currentView: PlantUmlLayerView | null): PlantUmlViewResult | null {
  const command = parsePlantUmlViewCommand(rawText);
  if (!command) {
    return null;
  }

  const object = findPlantUmlObject(artwork, command.diagramHint, command.targetLabel);
  if (!object) {
    return {
      action: command.action,
      view: currentView,
      message: "当前画布没有可查看的 PlantUML 图层",
      focusFound: false,
      targetLabel: command.targetLabel,
    };
  }

  const title = plantUmlTitle(object);
  if (command.action === "reset") {
    return {
      action: command.action,
      view: null,
      objectId: object.id,
      message: `已还原${title}视图`,
      focusFound: false,
    };
  }

  if (command.action === "zoom_out") {
    const scale = nextZoomScale(currentView, object.id, "out");
    return {
      action: command.action,
      view: scale <= 1 ? null : { objectId: object.id, mode: "zoom", scale },
      objectId: object.id,
      message: scale <= 1 ? `已还原${title}视图` : `已缩小${title}视图`,
      focusFound: false,
    };
  }

  if (command.action === "focus" && command.targetLabel) {
    const focusMatch = estimateFocusBox(object, command.targetLabel);
    if (focusMatch) {
      return {
        action: command.action,
        view: {
          objectId: object.id,
          mode: "focus",
          scale: FOCUS_SCALE,
          focusLabel: focusMatch.label,
          focusBox: focusMatch.box,
        },
        objectId: object.id,
        targetLabel: focusMatch.label,
        message: `已聚焦${focusMatch.label}模块视图`,
        focusFound: true,
      };
    }
    return {
      action: command.action,
      view: { objectId: object.id, mode: "zoom", scale: Math.max(FOCUS_SCALE - ZOOM_STEP, 1.4) },
      objectId: object.id,
      targetLabel: command.targetLabel,
      message: `没有在${title}源码中找到“${command.targetLabel}”，已放大整张图便于查看`,
      focusFound: false,
    };
  }

  const scale = nextZoomScale(currentView, object.id, "in");
  return {
    action: command.action,
    view: { objectId: object.id, mode: "zoom", scale },
    objectId: object.id,
    message: `已放大${title}视图`,
    focusFound: false,
  };
}
