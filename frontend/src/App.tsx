import { Icon } from "@iconify/react";
import categoryRounded from "@iconify-icons/material-symbols/category-rounded";
import downloadRounded from "@iconify-icons/material-symbols/download-rounded";
import graphicEqRounded from "@iconify-icons/material-symbols/graphic-eq-rounded";
import micRounded from "@iconify-icons/material-symbols/mic-rounded";
import pauseCircleRounded from "@iconify-icons/material-symbols/pause-circle-rounded";
import radioButtonUnchecked from "@iconify-icons/material-symbols/radio-button-unchecked";
import refreshRounded from "@iconify-icons/material-symbols/refresh-rounded";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createArtwork, submitVoiceCommand, synthesizeSpeech } from "./api";
import { CanvasStage } from "./drawing/CanvasStage";
import { useVoiceRecognition } from "./hooks/useVoiceRecognition";
import "./styles.css";
import type { Artwork, AsrTranscriptionMetrics, CommandExecutionMetrics, CommandPlan } from "./types";
import { exportSvgAsPng } from "./utils/exportPng";

interface TimelineItem {
  id: string;
  transcript: string;
  message: string;
  plan: CommandPlan | null;
  commandMetrics: CommandExecutionMetrics | null;
  asrMetrics: AsrTranscriptionMetrics | null;
}

const OPERATION_LABELS: Record<string, string> = {
  create_canvas: "更新画布",
  add_object: "添加对象",
  set_style: "修改样式",
  set_style_many: "批量改色",
  set_metadata: "更新对象信息",
  set_metadata_many: "批量更新对象信息",
  move_object: "移动对象",
  move_many: "批量移动",
  scale_object: "缩放对象",
  scale_many: "批量缩放",
  delete_object: "删除对象",
  clear_canvas: "清空画布",
  save_artwork: "保存作品",
  export_artwork: "导出作品",
  undo: "撤销",
  redo: "恢复"
};

const PLANNER_SOURCE_LABELS: Record<string, string> = {
  rules: "规则解析",
  mimo: "MiMo 规划",
  rules_fallback: "规则兜底"
};

function getOperationLabel(operationType: string): string {
  return OPERATION_LABELS[operationType] ?? operationType;
}

function getPlannerSourceLabel(source: string | undefined): string {
  if (!source) {
    return "本地解析";
  }
  return PLANNER_SOURCE_LABELS[source] ?? source;
}

function getPlanSummary(plan: CommandPlan | null): string {
  if (!plan) {
    return "未生成计划";
  }
  if (plan.explanation) {
    return plan.explanation;
  }
  if (plan.clarification_question) {
    return plan.clarification_question;
  }
  if (plan.scene_plan?.summary) {
    return plan.scene_plan.summary;
  }
  return plan.operations.map((operation) => getOperationLabel(operation.operation_type)).join(" -> ");
}

function formatLatency(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "暂无";
  }
  if (value >= 1000) {
    return `${(value / 1000).toFixed(2)} s`;
  }
  return `${Math.round(value)} ms`;
}

function getEndToEndLatency(commandMetrics: CommandExecutionMetrics | null, asrMetrics: AsrTranscriptionMetrics | null): number | null {
  const commandMs = commandMetrics?.total_ms;
  const asrMs = asrMetrics?.total_ms;
  if (commandMs === null || commandMs === undefined) {
    return null;
  }
  return commandMs + (asrMs ?? 0);
}

export default function App() {
  const [artwork, setArtwork] = useState<Artwork | null>(null);
  const [statusMessage, setStatusMessage] = useState("正在准备语音画布");
  const [isBusy, setIsBusy] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [latestPlan, setLatestPlan] = useState<CommandPlan | null>(null);
  const [latestCommandMetrics, setLatestCommandMetrics] = useState<CommandExecutionMetrics | null>(null);
  const [latestAsrMetrics, setLatestAsrMetrics] = useState<AsrTranscriptionMetrics | null>(null);
  const hasCreatedArtworkRef = useRef(false);
  const feedbackAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (hasCreatedArtworkRef.current) {
      return;
    }
    hasCreatedArtworkRef.current = true;
    createArtwork()
      .then((created) => {
        setArtwork(created);
        setStatusMessage("语音画布已准备");
      })
      .catch((error: unknown) => {
        setStatusMessage(error instanceof Error ? error.message : "创建画布失败");
      });
  }, []);

  const playFeedback = useCallback(async (message: string) => {
    try {
      const speech = await synthesizeSpeech(message);
      feedbackAudioRef.current?.pause();
      const audio = new Audio(speech.audio_data_url);
      feedbackAudioRef.current = audio;
      await audio.play();
    } catch {
      feedbackAudioRef.current = null;
    }
  }, []);

  const handleFinalTranscript = useCallback(
    async (text: string, asrMetrics: AsrTranscriptionMetrics | null) => {
      if (!artwork || isBusy) {
        return;
      }

      setIsBusy(true);
      setStatusMessage("正在解析语音指令");
      setLatestAsrMetrics(asrMetrics);
      try {
        const response = await submitVoiceCommand(artwork.id, text);
        setLatestPlan(response.plan);
        setLatestCommandMetrics(response.metrics);
        if (response.artwork) {
          setArtwork(response.artwork);
        }
        const containsExport = response.plan.operations.some((operation) => operation.operation_type === "export_artwork");
        if (containsExport) {
          await exportSvgAsPng("voice-canvas-svg", `${response.artwork?.title ?? artwork.title}.png`);
        }
        setTimeline((items) => [
          {
            id: crypto.randomUUID(),
            transcript: text,
            message: response.message,
            plan: response.plan,
            commandMetrics: response.metrics,
            asrMetrics
          },
          ...items
        ].slice(0, 12));
        setStatusMessage(response.message);
        void playFeedback(response.message);
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : "语音指令执行失败";
        setLatestPlan(null);
        setLatestCommandMetrics(null);
        setTimeline((items) => [
          {
            id: crypto.randomUUID(),
            transcript: text,
            message,
            plan: null,
            commandMetrics: null,
            asrMetrics
          },
          ...items
        ].slice(0, 12));
        setStatusMessage(message);
        void playFeedback(message);
      } finally {
        setIsBusy(false);
      }
    },
    [artwork, isBusy, playFeedback]
  );

  const voice = useVoiceRecognition({ onFinalTranscript: handleFinalTranscript });
  const handleManualExport = useCallback(async () => {
    if (!artwork) {
      return;
    }
    await exportSvgAsPng("voice-canvas-svg", `${artwork.title}.png`);
    setStatusMessage("已导出 PNG");
  }, [artwork]);
  const liveTranscript = voice.interimTranscript || voice.lastFinalTranscript;
  const objectCountText = useMemo(() => `${artwork?.objects.length ?? 0} 个对象`, [artwork?.objects.length]);
  const planConfidenceText = latestPlan ? `${Math.round(latestPlan.confidence * 100)}%` : "暂无";
  const listeningLabel = voice.isListening ? voice.providerLabel : `待机: ${voice.providerLabel}`;
  const endToEndLatency = getEndToEndLatency(latestCommandMetrics, latestAsrMetrics);

  return (
    <main className="workspace">
      <section className="stage-panel">
        <CanvasStage artwork={artwork} />
      </section>

      <aside className="side-panel" aria-live="polite">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Workspace</p>
            <h2>控制台</h2>
          </div>
          <div className="toolbar" aria-label="语音画布工具">
            <button
              aria-label="开始监听"
              className="icon-button"
              data-tooltip="开始监听"
              disabled={!voice.isSupported || voice.isListening}
              onClick={voice.start}
              title="开始监听"
              type="button"
            >
              <Icon icon={micRounded} width={20} height={20} />
            </button>
            <button
              aria-label="暂停监听"
              className="icon-button"
              data-tooltip="暂停监听"
              disabled={!voice.isListening}
              onClick={voice.stop}
              title="暂停监听"
              type="button"
            >
              <Icon icon={pauseCircleRounded} width={20} height={20} />
            </button>
            <button
              aria-label="重新监听"
              className="icon-button"
              data-tooltip="重新监听"
              disabled={!voice.isSupported}
              onClick={() => {
                voice.stop();
                window.setTimeout(() => voice.start(), 160);
              }}
              title="重新监听"
              type="button"
            >
              <Icon icon={refreshRounded} width={20} height={20} />
            </button>
            <button
              aria-label="导出 PNG"
              className="icon-button"
              data-tooltip="导出 PNG"
              disabled={!artwork}
              onClick={handleManualExport}
              title="导出 PNG"
              type="button"
            >
              <Icon icon={downloadRounded} width={20} height={20} />
            </button>
          </div>
        </div>

        <div className="side-status-row">
          <span className={voice.isListening ? "status-pill listening" : "status-pill"}>
            <Icon icon={voice.isListening ? graphicEqRounded : radioButtonUnchecked} width={16} height={16} />
            {listeningLabel}
          </span>
          <span className="status-pill">
            <Icon icon={categoryRounded} width={16} height={16} />
            {objectCountText}
          </span>
        </div>

        <div className="voice-card status-card">
          <p className="panel-label">当前状态</p>
          <strong>{voice.isSupported ? statusMessage : "当前没有可用的语音识别"}</strong>
          {voice.error ? <span className="error-text">{voice.error}</span> : null}
        </div>

        <div className="voice-card transcript-card">
          <p className="panel-label">识别文本</p>
          <p className="transcript">{liveTranscript || "等待语音输入"}</p>
        </div>

        <div className={latestPlan?.requires_confirmation ? "voice-card plan-card needs-confirmation" : "voice-card plan-card"}>
          <p className="panel-label">执行计划</p>
          {latestPlan ? (
            <>
              <div className="plan-meta">
                <span>{latestPlan.operations.length} 个步骤</span>
                <span>置信度 {planConfidenceText}</span>
                <span>{getPlannerSourceLabel(latestPlan.planner_source)}</span>
                {latestPlan.requires_confirmation ? <span className="warning-chip">需确认</span> : null}
              </div>
              <p className="plan-summary">{getPlanSummary(latestPlan)}</p>
              {latestPlan.scene_plan?.steps.length ? (
                <ol className="scene-step-list">
                  {latestPlan.scene_plan.steps.slice(0, 4).map((step) => (
                    <li key={step.step_id}>
                      <strong>{step.title}</strong>
                      <span>{step.intent}</span>
                    </li>
                  ))}
                </ol>
              ) : latestPlan.operations.length ? (
                <ol className="plan-list">
                  {latestPlan.operations.map((operation, index) => (
                    <li key={`${operation.operation_type}-${index}`}>{getOperationLabel(operation.operation_type)}</li>
                  ))}
                </ol>
              ) : (
                <p className="empty-text">暂无可执行步骤</p>
              )}
              {latestPlan.requires_confirmation && latestPlan.clarification_question && latestPlan.clarification_question !== getPlanSummary(latestPlan) ? (
                <p className="clarification-note">{latestPlan.clarification_question}</p>
              ) : null}
            </>
          ) : (
            <p className="empty-text">等待指令计划</p>
          )}
        </div>

        <div className="voice-card metrics-card">
          <p className="panel-label">延迟指标</p>
          <div className="metrics-grid">
            <span>
              <small>ASR</small>
              <strong>{formatLatency(latestAsrMetrics?.total_ms)}</strong>
            </span>
            <span>
              <small>规划</small>
              <strong>{formatLatency(latestCommandMetrics?.planner_total_ms)}</strong>
            </span>
            <span>
              <small>执行</small>
              <strong>{formatLatency(latestCommandMetrics?.execute_ms)}</strong>
            </span>
            <span>
              <small>端到端</small>
              <strong>{formatLatency(endToEndLatency)}</strong>
            </span>
          </div>
          <p className="metrics-note">
            {latestCommandMetrics?.fallback_used
              ? "MiMo 规划失败，已使用规则兜底"
              : latestCommandMetrics?.llm_succeeded
                ? "MiMo 规划已命中"
                : latestCommandMetrics
                  ? "规则解析已命中"
                  : "等待一次完整语音指令"}
          </p>
        </div>

        <div className="timeline">
          <p className="panel-label">操作历史</p>
          {timeline.length === 0 ? (
            <p className="empty-text">暂无操作</p>
          ) : (
            timeline.map((item) => (
              <article className="timeline-item" key={item.id}>
                <strong>{item.transcript}</strong>
                <span>{item.message}</span>
                <small>
                  {getPlanSummary(item.plan)} · 规划 {formatLatency(item.commandMetrics?.planner_total_ms)} · 总计{" "}
                  {formatLatency(getEndToEndLatency(item.commandMetrics, item.asrMetrics))}
                </small>
              </article>
            ))
          )}
        </div>
      </aside>
    </main>
  );
}
