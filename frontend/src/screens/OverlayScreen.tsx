import { useEffect, useRef, useState, useCallback } from "react";
import type { AppConfig, CompanionReaction } from "../types";
import CharacterAvatar, { detectDetailedMood } from "../components/CharacterAvatar";
import "./OverlayScreen.css";

interface Props {
  config: AppConfig;
}

export default function OverlayScreen({ config }: Props) {
  const [reaction, setReaction] = useState<CompanionReaction | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [displayText, setDisplayText] = useState("백엔드 연결 중...");
  const [showBubble, setShowBubble] = useState(true);
  const [connected, setConnected] = useState(false);
  const [, setHistory] = useState<CompanionReaction[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [detailedMood, setDetailedMood] = useState("chill");
  const bubbleTimer = useRef<number | null>(null);
  const typewriterRef = useRef<number | null>(null);

  // Drag support — move the entire Tauri window
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Don't drag if clicking a button
    if ((e.target as HTMLElement).closest('.ctrl-btn')) return;
    isDragging.current = true;
    dragStart.current = { x: e.screenX, y: e.screenY };
  }, []);

  useEffect(() => {
    const handleMouseMove = async (e: MouseEvent) => {
      if (!isDragging.current) return;
      const dx = e.screenX - dragStart.current.x;
      const dy = e.screenY - dragStart.current.y;
      dragStart.current = { x: e.screenX, y: e.screenY };
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window");
        const win = getCurrentWindow();
        const pos = await win.outerPosition();
        await win.setPosition(new (await import("@tauri-apps/api/dpi")).PhysicalPosition(
          pos.x + dx, pos.y + dy
        ));
      } catch {
        // Not in Tauri
      }
    };
    const handleMouseUp = () => { isDragging.current = false; };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  // Connect to Python backend SSE stream with auto-reconnect
  useEffect(() => {
    let evtSource: EventSource | null = null;
    let reconnectTimer: number | null = null;

    function connect() {
      evtSource = new EventSource("http://localhost:8080/stream");

      evtSource.onopen = () => {
        setConnected(true);
        setDisplayText("연결됨! 화면 분석 시작...");
      };

      evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "thinking") {
          setIsThinking(true);
          setShowBubble(true);
        } else if (data.type === "status") {
          setDisplayText(data.text);
          setShowBubble(true);
        } else if (data.type === "response") {
        const r: CompanionReaction = {
          text: data.text,
          face: data.face,
          mood: detectMood(data.text),
          cycle: data.cycle,
          elapsedMs: data.elapsed_ms,
          costEstimate: data.cost_estimate || "?",
        };
        setReaction(r);
        setIsThinking(false);
        setShowBubble(true);
        setDetailedMood(detectDetailedMood(r.text));
        setIsSpeaking(true);

        // Add to history
        setHistory((prev) => [r, ...prev].slice(0, 5));

        // Typewriter effect — mark speaking done when finished
        typewriteText(r.text, () => setIsSpeaking(false));

        // Auto-hide bubble after 8 seconds
        if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
        bubbleTimer.current = window.setTimeout(() => {
          setShowBubble(false);
        }, 8000);
      } else if (data.type === "error") {
        setIsThinking(false);
        setDisplayText(data.text);
        setShowBubble(true);
      }
    };

      evtSource.onerror = () => {
        setConnected(false);
        setIsThinking(false);
        evtSource?.close();
        // Auto-reconnect after 2s
        reconnectTimer = window.setTimeout(connect, 2000);
      };
    }

    // Initial connect with small delay to let backend start
    reconnectTimer = window.setTimeout(connect, 1500);

    return () => {
      evtSource?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
      if (typewriterRef.current) clearInterval(typewriterRef.current);
    };
  }, []);

  function typewriteText(text: string, onDone?: () => void) {
    if (typewriterRef.current) clearInterval(typewriterRef.current);
    let i = 0;
    setDisplayText("");
    typewriterRef.current = window.setInterval(() => {
      if (i < text.length) {
        i++;
        setDisplayText(text.substring(0, i));
      } else {
        if (typewriterRef.current) clearInterval(typewriterRef.current);
        if (onDone) onDone();
      }
    }, 22);
  }

  function detectMood(text: string): CompanionReaction["mood"] {
    const keywords: Record<string, string[]> = {
      excited: ["대박", "미쳤", "개쩔", "레전", "헐", "ㄷㄷ", "!!"],
      curious: ["뭐", "왜", "어떻게", "신기", "?"],
      worried: ["조심", "위험", "HP", "피", "죽", "도망"],
      amused: ["ㅋㅋ", "ㅎㅎ", "웃"],
    };
    for (const [mood, kws] of Object.entries(keywords)) {
      if (kws.some((k) => text.includes(k))) {
        return mood as CompanionReaction["mood"];
      }
    }
    return "chill";
  }

  const positionClass = `overlay-${config.position}`;

  const handleStop = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("stop_companion");
    } catch {
      window.close();
    }
  };

  const handleQuit = async () => {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("quit_app");
    } catch {
      window.close();
    }
  };

  return (
    <div className={`overlay-root ${positionClass}`}>
      <div
        className={`companion-widget ${showBubble ? "expanded" : ""} ${isThinking ? "thinking" : ""}`}
        onMouseDown={handleMouseDown}
        style={{ cursor: "grab" }}
      >
        {/* Control buttons — always visible */}
        <div className="overlay-controls">
          <button type="button" className="ctrl-btn" onClick={handleStop} title="설정으로 돌아가기">
            ⚙
          </button>
          <button type="button" className="ctrl-btn ctrl-quit" onClick={handleQuit} title="종료">
            ✕
          </button>
        </div>

        <div className="avatar-container" onClick={() => setShowBubble(!showBubble)}>
          <CharacterAvatar
            character={config.character}
            mood={isThinking ? "thinking" : detailedMood as any}
            isSpeaking={isSpeaking}
          />
        </div>

        {showBubble && (
          <div className="speech-bubble">
            {isThinking ? (
              <div className="thinking-text">생각 중...</div>
            ) : (
              <div className="speech-text">
                {displayText}
                {displayText.length < (reaction?.text.length || 0) && (
                  <span className="cursor" />
                )}
              </div>
            )}
            {reaction && !isThinking && (
              <div className="bubble-meta">
                #{reaction.cycle} | {reaction.elapsedMs}ms |{" "}
                <span className="cost">${reaction.costEstimate}</span>
              </div>
            )}
          </div>
        )}
        <div className={`connection-dot ${connected ? "connected" : ""}`} />
      </div>
    </div>
  );
}
