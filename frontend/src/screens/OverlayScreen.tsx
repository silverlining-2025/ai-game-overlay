import { useEffect, useRef, useState, useCallback, useReducer } from "react";
import type { AppConfig, CompanionReaction } from "../types";
import CharacterAvatar from "../components/CharacterAvatar";
import FeedbackForm from "../components/FeedbackForm";
import StatsPanel from "../components/StatsPanel";
import type { SessionStats } from "../components/StatsPanel";
import { useTranslation } from "../i18n/useTranslation";
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
  const { t } = useTranslation();
  const [state, dispatch] = useReducer(overlayReducer, {
    connected: false,
    isThinking: false,
    showBubble: false,  // Hidden until first real reaction
    isSpeaking: false,
    detailedMood: "chill",
    reaction: null,
  });

  // Micro-expression timer (VTuber-style idle animations)
  const microExprRef = useRef<number | null>(null);
  const [microMood, setMicroMood] = useState<string | null>(null);

  // DOM ref for typewriter (bypasses React render cycle)
  const speechRef = useRef<HTMLDivElement>(null);
  const typewriterRef = useRef<number | null>(null);
  const bubbleTimer = useRef<number | null>(null);
  const isStreamingRef = useRef(false);
  const [statusText] = useState("");
  const [debugInfo, setDebugInfo] = useState("");
  const [showDebug, setShowDebug] = useState(false);

  // Text feedback form (Alt+F)
  const [showTextFeedback, setShowTextFeedback] = useState(false);

  // Session stats panel (Ctrl+Shift+S)
  const [showStats, setShowStats] = useState(false);
  const statsRef = useRef<SessionStats>({
    sessionStart: Date.now(),
    reactionCount: { burst: 0, react: 0, chat: 0 },
    apiCalls: 0,
    totalCost: 0,
    feedbackUp: 0,
    feedbackDown: 0,
    events: {},
  });
  const [stats, setStats] = useState<SessionStats>(statsRef.current);

  const updateStats = useCallback((updater: (s: SessionStats) => void) => {
    updater(statsRef.current);
    setStats({ ...statsRef.current });
  }, []);

  // Feedback buttons state
  const [showFeedback, setShowFeedback] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState<"up" | "down" | null>(null);
  const feedbackTimer = useRef<number | null>(null);
  const lastCycleRef = useRef<number>(0);
  const lastTextRef = useRef<string>("");

  const sendFeedback = useCallback(async (rating: "up" | "down") => {
    setFeedbackGiven(rating);
    updateStats(s => {
      if (rating === "up") s.feedbackUp++;
      else s.feedbackDown++;
    });
    try {
      await fetch("http://localhost:8080/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cycle: lastCycleRef.current,
          text: lastTextRef.current,
          rating,
          game: config.game,
          character: config.character,
        }),
      });
    } catch { /* ignore */ }
    // Hide after brief confirmation
    setTimeout(() => {
      setShowFeedback(false);
      setFeedbackGiven(null);
    }, 800);
  }, [config.game, config.character, updateStats]);

  const showFeedbackButtons = useCallback((cycle: number, text: string) => {
    lastCycleRef.current = cycle;
    lastTextRef.current = text;
    setFeedbackGiven(null);
    setShowFeedback(true);
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = window.setTimeout(() => {
      setShowFeedback(false);
      setFeedbackGiven(null);
    }, 6000);
  }, []);

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

  // Click-through toggle + debug toggle
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Alt" && tauriWindow) {
        tauriWindow.getCurrentWindow().setIgnoreCursorEvents(false);
      }
      // Ctrl+Shift+D toggles debug bar
      if (e.key === "D" && e.ctrlKey && e.shiftKey) {
        setShowDebug(prev => !prev);
      }
      // Ctrl+Shift+S toggles session stats panel
      if (e.key === "S" && e.ctrlKey && e.shiftKey) {
        e.preventDefault();
        setShowStats(prev => !prev);
      }
      // Alt+F toggles text feedback form
      if (e.key === "f" && e.altKey) {
        e.preventDefault();
        setShowTextFeedback(prev => !prev);
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
        // Greeting — character is alive from the start (locale-aware)
        const greeting = t("companion.greeting_ko");
        if (speechRef.current) speechRef.current.textContent = greeting;
        dispatch({
          type: "RESPONSE",
          payload: { text: greeting, face: "", mood: "chill", cycle: 0, elapsedMs: 0, costEstimate: "" },
        });
        if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
        bubbleTimer.current = window.setTimeout(() => dispatch({ type: "HIDE_BUBBLE" }), 5000);
      };

      es.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === "thinking") {
          dispatch({ type: "THINKING" });
        } else if (data.type === "status") {
          // Internal status — don't show to user

        // --- Streaming: text appears as Claude generates it ---
        } else if (data.type === "stream_start") {
          if (typewriterRef.current) clearInterval(typewriterRef.current);
          if (speechRef.current) speechRef.current.textContent = "";
          isStreamingRef.current = true;
          dispatch({ type: "THINKING" });
        } else if (data.type === "stream_chunk") {
          // First chunk transitions from thinking to showing text
          if (isStreamingRef.current) {
            isStreamingRef.current = false;
            dispatch({
              type: "RESPONSE",
              payload: {
                text: "", face: "", mood: "chill",
                cycle: 0, elapsedMs: 0, costEstimate: "",
              },
            });
          }
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

          // Track stats from stream_end
          updateStats(s => {
            s.apiCalls++;
            const mode = data.debug?.mode || "react";
            if (mode === "burst") s.reactionCount.burst++;
            else if (mode === "chat") s.reactionCount.chat++;
            else s.reactionCount.react++;
            // Backend sends cumulative total cost — SET, don't add
            const costStr = data.debug?.cost || data.cost_estimate || "0";
            const costNum = parseFloat(String(costStr).replace(/[^0-9.]/g, ""));
            if (!isNaN(costNum)) s.totalCost = costNum;
            // Track event type
            if (data.debug?.event) {
              const evt = data.debug.event as string;
              s.events[evt] = (s.events[evt] || 0) + 1;
            }
          });

          if (data.debug) {
            const d = data.debug;
            setDebugInfo(`#${d.cycle} | ${d.ms}ms | $${d.cost} | ${d.event}(${d.score}) | ${d.mode}`);
          }

          // Show feedback buttons after stream completes
          if (data.cycle > 0) {
            showFeedbackButtons(data.cycle, data.text);
          }

          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          const hideMs = Math.min(15000, Math.max(4000, data.text.length * 80));
          bubbleTimer.current = window.setTimeout(() => {
            dispatch({ type: "HIDE_BUBBLE" });
          }, hideMs);

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

          // Track stats from legacy response
          updateStats(s => {
            s.apiCalls++;
            s.reactionCount.react++;
            const costNum = parseFloat(String(r.costEstimate).replace(/[^0-9.]/g, ""));
            if (!isNaN(costNum)) s.totalCost += costNum;
          });

          if (r.cycle > 0) {
            showFeedbackButtons(r.cycle, r.text);
          }

          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          const hideMs2 = Math.min(15000, Math.max(4000, r.text.length * 80));
          bubbleTimer.current = window.setTimeout(() => {
            dispatch({ type: "HIDE_BUBBLE" });
          }, hideMs2);
        } else if (data.type === "limit_reached") {
          // Show limit message in speech bubble
          if (speechRef.current) speechRef.current.textContent = data.text;
          dispatch({
            type: "RESPONSE",
            payload: { text: data.text, face: "(._. )", mood: "worried", cycle: 0, elapsedMs: 0, costEstimate: "" },
          });
        } else if (data.type === "error") {
          const errorText = data.text || t("companion.error_api");
          if (speechRef.current) speechRef.current.textContent = errorText;
          dispatch({
            type: "RESPONSE",
            payload: { text: errorText, face: "(×_×)", mood: "worried", cycle: 0, elapsedMs: 0, costEstimate: "" },
          });
          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => dispatch({ type: "HIDE_BUBBLE" }), 5000);
        } else if (data.type === "cost_warning") {
          const warningText = data.text || t("companion.cost_warning");
          if (speechRef.current) speechRef.current.textContent = warningText;
          dispatch({
            type: "RESPONSE",
            payload: { text: warningText, face: "(;´Д`)", mood: "worried", cycle: 0, elapsedMs: 0, costEstimate: "" },
          });
          if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
          bubbleTimer.current = window.setTimeout(() => dispatch({ type: "HIDE_BUBBLE" }), 8000);
        } else if (data.type === "cost_limit") {
          const limitText = data.text || t("companion.cost_warning");
          if (speechRef.current) speechRef.current.textContent = limitText;
          dispatch({
            type: "RESPONSE",
            payload: { text: limitText, face: "(×_×)", mood: "worried", cycle: 0, elapsedMs: 0, costEstimate: "" },
          });
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

  // Micro-expression cycle: subtle idle mood shifts every 15-30s
  useEffect(() => {
    function scheduleMicro() {
      const delay = 15000 + Math.random() * 15000; // 15-30s
      microExprRef.current = window.setTimeout(() => {
        if (!state.isThinking && !state.isSpeaking) {
          const moods = ["curious", "amused", "chill", "blush"];
          setMicroMood(moods[Math.floor(Math.random() * moods.length)] ?? null);
          setTimeout(() => setMicroMood(null), 2500);
        }
        scheduleMicro();
      }, delay);
    }
    scheduleMicro();
    return () => { if (microExprRef.current) clearTimeout(microExprRef.current); };
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
          <button type="button" className="ctrl-btn" onClick={handleStop} title={t("companion.back_to_settings")}>
            ⚙
          </button>
          <button type="button" className="ctrl-btn ctrl-quit" onClick={handleQuit} title={t("companion.quit")}>
            ✕
          </button>
        </div>

        <div className="avatar-container" onClick={() => dispatch({ type: "TOGGLE_BUBBLE" })}>
          <CharacterAvatar
            character={config.character}
            mood={state.isThinking ? "thinking" : (microMood || state.detailedMood) as any}
            isSpeaking={state.isSpeaking}
          />
          <div className="character-name">{config.character}</div>
        </div>

        {state.showBubble && (
          <div className="speech-bubble">
            {state.isThinking ? (
              <div className="thinking-text">{t("companion.thinking")}</div>
            ) : (
              <div className="speech-text" ref={speechRef}>
                {statusText}
              </div>
            )}
            {showFeedback && !state.isThinking && (
              <div className="feedback-buttons">
                <button
                  type="button"
                  className={`feedback-btn ${feedbackGiven === "up" ? "feedback-selected-up" : ""} ${feedbackGiven === "down" ? "feedback-other" : ""}`}
                  onClick={() => sendFeedback("up")}
                  disabled={feedbackGiven !== null}
                  title="좋아요"
                >▲</button>
                <button
                  type="button"
                  className={`feedback-btn ${feedbackGiven === "down" ? "feedback-selected-down" : ""} ${feedbackGiven === "up" ? "feedback-other" : ""}`}
                  onClick={() => sendFeedback("down")}
                  disabled={feedbackGiven !== null}
                  title="별로에요"
                >▼</button>
              </div>
            )}
          </div>
        )}
        <div className={`connection-dot ${state.connected ? "connected" : ""}`} />
        {showDebug && debugInfo && <div className="debug-bar">{debugInfo}</div>}
      </div>

      {showTextFeedback && (
        <FeedbackForm
          onClose={() => setShowTextFeedback(false)}
          game={config.game}
          character={config.character}
        />
      )}

      <StatsPanel visible={showStats} stats={stats} />
    </div>
  );
}
