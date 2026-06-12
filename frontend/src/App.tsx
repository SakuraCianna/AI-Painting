import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createArtwork, submitVoiceCommand } from "./api";
import { CanvasStage } from "./drawing/CanvasStage";
import { useVoiceRecognition } from "./hooks/useVoiceRecognition";
import "./styles.css";
import type { Artwork, CommandPlan } from "./types";
import { exportSvgAsPng } from "./utils/exportPng";

interface TimelineItem {
  id: string;
  transcript: string;
  message: string;
  plan: CommandPlan | null;
}

const OPERATION_LABELS: Record<string, string> = {
  create_canvas: "更新画布",
  add_object: "添加对象",
  set_style: "修改样式",
  set_style_many: "批量改色",
  move_object: "移动对象",
  move_many: "批量移动",
  scale_object: "缩放对象",
  delete_object: "删除对象",
  save_artwork: "保存作品",
  export_artwork: "导出作品",
  undo: "撤销",
  redo: "恢复"
};

function getOperationLabel(operationType: string): string {
  return OPERATION_LABELS[operationType] ?? operationType;
}

function getPlanSummary(plan: CommandPlan | null): string {
  if (!plan) {
    return "未生成计划";
  }
  if (plan.clarification_question) {
    return plan.clarification_question;
  }
  return plan.operations.map((operation) => getOperationLabel(operation.operation_type)).join(" -> ");
}

export default function App() {
  const [artwork, setArtwork] = useState<Artwork | null>(null);
  const [statusMessage, setStatusMessage] = useState("正在准备语音画布");
  const [isBusy, setIsBusy] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [latestPlan, setLatestPlan] = useState<CommandPlan | null>(null);
  const hasCreatedArtworkRef = useRef(false);

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

  const handleFinalTranscript = useCallback(
    async (text: string) => {
      if (!artwork || isBusy) {
        return;
      }

      setIsBusy(true);
      setStatusMessage("正在解析语音指令");
      try {
        const response = await submitVoiceCommand(artwork.id, text);
        setLatestPlan(response.plan);
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
            plan: response.plan
          },
          ...items
        ].slice(0, 12));
        setStatusMessage(response.message);
        if ("speechSynthesis" in window) {
          const utterance = new SpeechSynthesisUtterance(response.message);
          utterance.lang = "zh-CN";
          window.speechSynthesis.cancel();
          window.speechSynthesis.speak(utterance);
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : "语音指令执行失败";
        setLatestPlan(null);
        setTimeline((items) => [
          {
            id: crypto.randomUUID(),
            transcript: text,
            message,
            plan: null
          },
          ...items
        ].slice(0, 12));
        setStatusMessage(message);
      } finally {
        setIsBusy(false);
      }
    },
    [artwork, isBusy]
  );

  const voice = useVoiceRecognition({ onFinalTranscript: handleFinalTranscript });
  const liveTranscript = voice.interimTranscript || voice.lastFinalTranscript;
  const objectCountText = useMemo(() => `${artwork?.objects.length ?? 0} 个对象`, [artwork?.objects.length]);
  const planConfidenceText = latestPlan ? `${Math.round(latestPlan.confidence * 100)}%` : "暂无";
  const listeningLabel = voice.isListening ? "正在聆听" : "待机";

  return (
    <main className="workspace">
      <section className="stage-panel">
        <header className="topbar" aria-live="polite">
          <div className="product-lockup">
            <div className="app-mark" aria-hidden="true">
              <span />
            </div>
            <div>
              <p className="eyebrow">Voice Canvas</p>
              <h1>{artwork?.title ?? "语音绘图作品"}</h1>
            </div>
          </div>
          <div className="status-cluster">
            <span className={voice.isListening ? "status-pill listening" : "status-pill"}>{listeningLabel}</span>
            <span className="status-pill">{objectCountText}</span>
          </div>
        </header>

        <CanvasStage artwork={artwork} />
      </section>

      <aside className="side-panel" aria-live="polite">
        <div className="panel-heading">
          <p className="eyebrow">Workspace</p>
          <h2>语音控制台</h2>
        </div>

        <div className="voice-card status-card">
          <p className="panel-label">当前状态</p>
          <strong>{voice.isSupported ? statusMessage : "当前浏览器不支持内置语音识别"}</strong>
          {voice.error ? <span className="error-text">{voice.error}</span> : null}
        </div>

        <div className="voice-card transcript-card">
          <p className="panel-label">识别文本</p>
          <p className="transcript">{liveTranscript || "等待语音输入"}</p>
        </div>

        <div className="voice-card plan-card">
          <p className="panel-label">执行计划</p>
          {latestPlan ? (
            <>
              <div className="plan-meta">
                <span>{latestPlan.operations.length} 个步骤</span>
                <span>置信度 {planConfidenceText}</span>
              </div>
              <ol className="plan-list">
                {latestPlan.operations.map((operation, index) => (
                  <li key={`${operation.operation_type}-${index}`}>{getOperationLabel(operation.operation_type)}</li>
                ))}
              </ol>
            </>
          ) : (
            <p className="empty-text">等待指令计划</p>
          )}
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
                <small>{getPlanSummary(item.plan)}</small>
              </article>
            ))
          )}
        </div>
      </aside>
    </main>
  );
}
