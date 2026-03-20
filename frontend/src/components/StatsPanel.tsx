import { useEffect, useState } from "react";
import { useTranslation } from "../i18n/useTranslation";
import "./StatsPanel.css";

export interface SessionStats {
  sessionStart: number;
  reactionCount: { burst: number; react: number; chat: number };
  apiCalls: number;
  totalCost: number;
  feedbackUp: number;
  feedbackDown: number;
  events: Record<string, number>;
}

interface Props {
  visible: boolean;
  stats: SessionStats;
}

function formatDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}시간 ${m}분`;
  if (m > 0) return `${m}분 ${s}초`;
  return `${s}초`;
}

export default function StatsPanel({ visible, stats }: Props) {
  const { t } = useTranslation();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!visible) return;
    const tick = () => setElapsed(Date.now() - stats.sessionStart);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [visible, stats.sessionStart]);

  if (!visible) return null;

  const totalReactions = stats.reactionCount.burst + stats.reactionCount.react + stats.reactionCount.chat;
  const eventEntries = Object.entries(stats.events).filter(([, v]) => v > 0);

  return (
    <div className="stats-panel">
      <div className="stats-header">{t("stats.title")}</div>

      <div className="stats-row">
        <span className="stats-label">{t("stats.time")}</span>
        <span className="stats-value">{formatDuration(elapsed)}</span>
      </div>

      <div className="stats-row">
        <span className="stats-label">{t("stats.reactions")}</span>
        <span className="stats-value">{totalReactions}</span>
      </div>

      {totalReactions > 0 && (
        <div className="stats-sub">
          {stats.reactionCount.burst > 0 && <span>{t("stats.burst")}: {stats.reactionCount.burst}</span>}
          {stats.reactionCount.react > 0 && <span>{t("stats.react")}: {stats.reactionCount.react}</span>}
          {stats.reactionCount.chat > 0 && <span>{t("stats.chat")}: {stats.reactionCount.chat}</span>}
        </div>
      )}

      <div className="stats-row">
        <span className="stats-label">{t("stats.api_calls")}</span>
        <span className="stats-value">{stats.apiCalls}</span>
      </div>

      <div className="stats-row">
        <span className="stats-label">{t("stats.cost")}</span>
        <span className="stats-value stats-cost">${stats.totalCost.toFixed(4)}</span>
      </div>

      <div className="stats-row">
        <span className="stats-label">{t("stats.feedback")}</span>
        <span className="stats-value">
          <span className="stats-up" title={t("stats.up")}>{stats.feedbackUp}</span>
          {" / "}
          <span className="stats-down" title={t("stats.down")}>{stats.feedbackDown}</span>
        </span>
      </div>

      {eventEntries.length > 0 && (
        <>
          <div className="stats-divider" />
          <div className="stats-section-label">{t("stats.events")}</div>
          {eventEntries.map(([event, count]) => (
            <div className="stats-row stats-event-row" key={event}>
              <span className="stats-label">{event}</span>
              <span className="stats-value">{count}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
