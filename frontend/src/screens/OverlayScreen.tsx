import { useEffect, useRef, useState, useCallback, useReducer } from "react";
import type { AppConfig, CompanionReaction } from "../types";
import CharacterAvatar from "../components/CharacterAvatar";
import "./OverlayScreen.css";

// Module-level Tauri imports (avoid dynamic import in hot paths)
let tauriWindow: typeof import("@tauri-apps/api/window") | null = null;
let tauriDpi: typeof import("@tauri-apps/api/dpi") | null = null;
let tauriCore: typeof import("@tauri-apps/api/core") | null = null;

// Load Tauri APIs once at module level
(async () => {
  try {
    tauriWindow = await import("@tauri-apps/api/window");
    tauriDpi = await import("@tauri-apps/api/dpi");
    tauriCore = await import("@tauri-apps/api/core");
  } catch {
    // Not in Tauri environment
  }
})();

interface Props {
  config: AppConfig;
}

// Consolidated state with useReducer (avoids batching issues in native callbacks)
type OverlayState = {
  connected: boolean;
  isThinking: boolean;
  showBubble: boolean;
  isSpeaking: boolean;
  detailedMood: string;
  reaction: CompanionReaction | null;
};

type Action =
  | { type: "CONNECTED" }
  | { type: "DISCONNECTED" }
  | { type: "THINKING" }
  | { type: "RESPONSE"; payload: CompanionReaction }
  | { type: "SPEAKING_DONE" }
  | { type: "HIDE_BUBBLE" }
  | { type: "TOGGLE_BUBBLE" }
  | { type: "STATUS"; text: string }
  | { type: "ERROR"; text: string };

function overlayReducer(state: OverlayState, action: Action): OverlayState {
  switch (action.type) {
    case "CONNECTED":
      return { ...state, connected: true };
    case "DISCONNECTED":
      return { ...state, connected: false, isThinking: false };
    case "THINKING":
      return { ...state, isThinking: true, showBubble: true };
    case "RESPONSE":
      return {
        ...state,
        reaction: action.payload,
        isThinking: false,
        showBubble: true,
        isSpeaking: true,
        detailedMood: action.payload.mood || "chill",
      };
    case "SPEAKING_DONE":
      return { ...state, isSpeaking: false };
    case "HIDE_BUBBLE":
      return { ...state, showBubble: false };
    case "TOGGLE_BUBBLE":
      return { ...state, showBubble: !state.showBubble };
    case "STATUS":
    case "ERROR":
      return { ...state, isThinking: false, showBubble: true };
    default:
      return state;
  }
}

export default function OverlayScreen({ config }: Props) {
  const [state, dispatch] = useReducer(overlayReducer, {
    connected: false,
    isThinking: false,
    showBubble: true,
    isSpeaking: false,
    detailedMood: "chill",
    reaction: null,
  });

  // DOM ref for typewriter (bypasses React render cycle)
  const speechRef = useRef<HTMLDivElement>(null);
  const typewriterRef = useRef<number | null>(null);
  const bubbleTimer = useRef<number | null>(null);
  const [statusText, setStatusText] = useState("백엔드 연결 중...");

  // Drag support
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest(".ctrl-btn")) return;
    isDragging.current = true;
    dragStart.current = { x: e.screenX, y: e.screenY };
  }, []);

  useEffect(() => {
    const handleMouseMove = async (e: MouseEvent) => {
      if (!isDragging.current || !tauriWindow || !tauriDpi) return;
      const dx = e.screenX - dragStart.current.x;
      const dy = e.screenY - dragStart.current.y;
      dragStart.current = { x: e.screenX, y: e.screenY };
      try {
        const win = tauriWindow.getCurrentWindow();
        const pos = await win.outerPosition();
        await win.setPosition(new tauriDpi.PhysicalPosition(pos.x + dx, pos.y + dy));
      } catch { /* ignore */ }
    };
    const handleMouseUp = () => { isDragging.current = false; };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  // Typewriter using DOM ref (no React re-renders per character)
  function typewriteText(text: string, onDone?: () => void) {
    if (typewriterRef.current) clearInterval(typewriterRef.current);
    let i = 0;
    if (speechRef.current) speechRef.current.textContent = "";
    typewriterRef.current = window.setInterval(() => {
      if (i < text.length) {
        i++;
        if (speechRef.current) speechRef.current.textContent = text.substring(0, i);
      } else {
        if (typewriterRef.current) clearInterval(typewriterRef.current);
        if (onDone) onDone();
      }
    }, 22);
  }

  // Click-through toggle: hold Alt to interact with overlay
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Alt" && tauriWindow) {
        tauriWindow.getCurrentWindow().setIgnoreCursorEvents(false);
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Alt" && tauriWindow) {
        tauriWindow.getCurrentWindow().setIgnoreCursorEvents(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, []);

  // SSE connection with auto-reconnect
  useEffect(() => {
    const evtSourceRef = { current: null as EventSource | null };
    let reconnectTimer: number | null = null;

    function connect() {
      const es = new EventSource("http://localhost:8080/stream");
      evtSourceRef.current = es;

      es.onopen = () => {
        dispatch({ type: "CONNECTED" });
        setStatusText("연결됨! 화면 분석 시작...");
        if (speechRef.current) speechRef.current.textContent = "연결됨! 화면 분석 시작...";
      };

      es.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "thinking") {
          dispatch({ type: "THINKING" });
        } else if (data.type === "status") {
          // Internal status — don't show to user

        // --- Streaming: text appears as Claude generates it ---
        } else if (data.type === "stream_start") {
          // Clear previous text, show bubble, mark speaking
          if (typewriterRef.current) clearInterval(typewriterRef.current);
          if (speechRef.current) speechRef.current.textContent = "";
          dispatch({ type: "THINKING" }); // show thinking briefly
          dispatch({
            type: "RESPONSE",
            payload: {
              text: "", face: "", mood: "chill",
              cycle: data.cycle, elapsedMs: 0, costEstimate: "...",
            },
          });
        } else if (data.type === "stream_chunk") {
          // Append chunk directly to DOM (no re-render)
          if (speechRef.current) {
            speechRef.current.textContent += data.text;
          }
        } else if (data.type === "stream_end") {
          // Final response with metadata
          const r: CompanionReaction = {
            text: data.text,
            face: data.face,
            mood: data.mood || "chill",
            cycle: data.cycle,
            elapsedMs: data.elapsed_ms,
            costEstimate: data.cost_estimate || "?",
          };
          dispatch({ type: "RESPONSE", payload: r });
          dispatch({ type: "SPEAKING_DONE" });
          if (speechRef.current) speechRef.current.textContent = data.text;

          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => {
            dispatch({ type: "HIDE_BUBBLE" });
          }, 8000);

        // Legacy non-streaming support
        } else if (data.type === "response") {
          const r: CompanionReaction = {
            text: data.text,
            face: data.face,
            mood: data.mood || "chill",
            cycle: data.cycle,
            elapsedMs: data.elapsed_ms,
            costEstimate: data.cost_estimate || "?",
          };
          dispatch({ type: "RESPONSE", payload: r });
          typewriteText(r.text, () => dispatch({ type: "SPEAKING_DONE" }));

          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => {
            dispatch({ type: "HIDE_BUBBLE" });
          }, 8000);
        } else if (data.type === "error") {
          dispatch({ type: "ERROR", text: data.text });
          setStatusText(data.text);
          if (speechRef.current) speechRef.current.textContent = data.text;
        }
      };

      es.onerror = () => {
        dispatch({ type: "DISCONNECTED" });
        es.close();
        reconnectTimer = window.setTimeout(connect, 2000);
      };
    }

    reconnectTimer = window.setTimeout(connect, 1500);

    return () => {
      evtSourceRef.current?.close();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
      if (typewriterRef.current) clearInterval(typewriterRef.current);
    };
  }, []);

  const handleStop = useCallback(async () => {
    try {
      await tauriCore?.invoke("stop_companion");
    } catch {
      window.close();
    }
  }, []);

  const handleQuit = useCallback(async () => {
    try {
      await tauriCore?.invoke("quit_app");
    } catch {
      window.close();
    }
  }, []);

  return (
    <div className={`overlay-root overlay-${config.position}`}>
      <div
        className={`companion-widget ${state.showBubble ? "expanded" : ""} ${state.isThinking ? "thinking" : ""}`}
        onMouseDown={handleMouseDown}
        style={{ cursor: "grab" }}
      >
        <div className="overlay-controls">
          <button type="button" className="ctrl-btn" onClick={handleStop} title="설정으로 돌아가기">
            ⚙
          </button>
          <button type="button" className="ctrl-btn ctrl-quit" onClick={handleQuit} title="종료">
            ✕
          </button>
        </div>

        <div className="avatar-container" onClick={() => dispatch({ type: "TOGGLE_BUBBLE" })}>
          <CharacterAvatar
            character={config.character}
            mood={state.isThinking ? "thinking" : state.detailedMood as any}
            isSpeaking={state.isSpeaking}
          />
        </div>

        {state.showBubble && (
          <div className="speech-bubble">
            {state.isThinking ? (
              <div className="thinking-text">생각 중...</div>
            ) : (
              <div className="speech-text" ref={speechRef}>
                {statusText}
              </div>
            )}
            {state.reaction && !state.isThinking && (
              <div className="bubble-meta">
                #{state.reaction.cycle} | {state.reaction.elapsedMs}ms |{" "}
                <span className="cost">${state.reaction.costEstimate}</span>
              </div>
            )}
          </div>
        )}
        <div className={`connection-dot ${state.connected ? "connected" : ""}`} />
      </div>
    </div>
  );
}
