import { useState } from "react";
import { useTranslation } from "@/i18n/useTranslation";

interface CoachPanelProps {
  suggestion: string | null;
  reasoning?: string;
}

export function CoachPanel({ suggestion, reasoning }: CoachPanelProps) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="coach-panel">
      <div className="coach-header">
        <span>{t("overlay.coach_title")}</span>
        <button
          className="coach-toggle"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? "▼" : "▲"}
        </button>
      </div>
      {!collapsed && (
        <div className="coach-body">
          {suggestion ? (
            <>
              <div className="coach-bubble">{suggestion}</div>
              {reasoning && (
                <div className="coach-bubble" style={{ opacity: 0.7 }}>
                  {reasoning}
                </div>
              )}
            </>
          ) : (
            <p className="loading-text">{t("coach.no_suggestion")}</p>
          )}
        </div>
      )}
    </div>
  );
}
