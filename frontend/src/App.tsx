import { useCallback, useEffect, useMemo, useState } from "react";
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

function getPlanSummary(plan: CommandPlan | null): string {
  if (!plan) {
    return "未生成计划";
  }
  if (plan.clarification_question) {
    return plan.clarification_question;
  }
  return plan.operations.map((operation) => operation.operation_type).join(" -> ");
}

export default function App() {
  const [artwork, setArtwork] = useState<Artwork | null>(null);
  const [statusMessage, setStatusMessage] = useState("正在准备语音画布");
  const [isBusy, setIsBusy] = useState(false);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);

  useEffect(() => {
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
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : "语音指令执行失败";
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

  return (
    <main className="workspace">
      <section className="stage-panel">
        <header className="topbar" aria-live="polite">
          <div>
            <p className="eyebrow">AI Painting</p>
            <h1>{artwork?.title ?? "语音绘图作品"}</h1>
          </div>
          <div className="status-cluster">
            <span className={voice.isListening ? "status-pill listening" : "status-pill"}>{voice.isListening ? "监听中" : "未监听"}</span>
            <span className="status-pill">{objectCountText}</span>
          </div>
        </header>

        <CanvasStage artwork={artwork} />
      </section>

      <aside className="side-panel" aria-live="polite">
        <div className="voice-card">
          <p className="panel-label">当前状态</p>
          <strong>{voice.isSupported ? statusMessage : "当前浏览器不支持内置语音识别"}</strong>
          {voice.error ? <span className="error-text">{voice.error}</span> : null}
        </div>

        <div className="voice-card transcript-card">
          <p className="panel-label">识别文本</p>
          <p className="transcript">{liveTranscript || "等待语音输入"}</p>
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
