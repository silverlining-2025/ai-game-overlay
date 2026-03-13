import { useTranslation } from "@/i18n/useTranslation";

interface StatusBarProps {
  connected: boolean;
  fps?: number;
  captureMs?: number;
  processingMs?: number;
}

export function StatusBar({
  connected,
  fps,
  captureMs,
  processingMs,
}: StatusBarProps) {
  const { t } = useTranslation();

  const statusClass = connected ? "connected" : "disconnected";
  const statusText = connected
    ? t("status.connected")
    : t("status.disconnected");

  return (
    <div className="status-bar">
      <span className={`status-dot ${statusClass}`} />
      <span>{statusText}</span>
      {fps != null && <span>{t("perf.fps", { value: fps.toFixed(1) })}</span>}
      {captureMs != null && (
        <span>{t("perf.capture_ms", { value: captureMs.toFixed(0) })}</span>
      )}
      {processingMs != null && (
        <span>{t("perf.processing_ms", { value: processingMs.toFixed(0) })}</span>
      )}
    </div>
  );
}
