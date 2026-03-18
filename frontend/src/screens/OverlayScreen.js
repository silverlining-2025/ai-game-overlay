import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState, useCallback, useReducer } from "react";
import CharacterAvatar from "../components/CharacterAvatar";
import FeedbackForm from "../components/FeedbackForm";
import StatsPanel from "../components/StatsPanel";
import "./OverlayScreen.css";
// Module-level Tauri imports (avoid dynamic import in hot paths)
let tauriWindow = null;
let tauriDpi = null;
let tauriCore = null;
// Load Tauri APIs once at module level
(async () => {
    try {
        tauriWindow = await import("@tauri-apps/api/window");
        tauriDpi = await import("@tauri-apps/api/dpi");
        tauriCore = await import("@tauri-apps/api/core");
    }
    catch {
        // Not in Tauri environment
    }
})();
function overlayReducer(state, action) {
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
export default function OverlayScreen({ config }) {
    const [state, dispatch] = useReducer(overlayReducer, {
        connected: false,
        isThinking: false,
        showBubble: false, // Hidden until first real reaction
        isSpeaking: false,
        detailedMood: "chill",
        reaction: null,
    });
    // DOM ref for typewriter (bypasses React render cycle)
    const speechRef = useRef(null);
    const typewriterRef = useRef(null);
    const bubbleTimer = useRef(null);
    const isStreamingRef = useRef(false);
    const [statusText] = useState("");
    const [debugInfo, setDebugInfo] = useState("");
    const [showDebug, setShowDebug] = useState(false);
    // Text feedback form (Alt+F)
    const [showTextFeedback, setShowTextFeedback] = useState(false);
    // Session stats panel (Ctrl+Shift+S)
    const [showStats, setShowStats] = useState(false);
    const statsRef = useRef({
        sessionStart: Date.now(),
        reactionCount: { burst: 0, react: 0, chat: 0 },
        apiCalls: 0,
        totalCost: 0,
        feedbackUp: 0,
        feedbackDown: 0,
        events: {},
    });
    const [stats, setStats] = useState(statsRef.current);
    const updateStats = useCallback((updater) => {
        updater(statsRef.current);
        setStats({ ...statsRef.current });
    }, []);
    // Feedback buttons state
    const [showFeedback, setShowFeedback] = useState(false);
    const [feedbackGiven, setFeedbackGiven] = useState(null);
    const feedbackTimer = useRef(null);
    const lastCycleRef = useRef(0);
    const lastTextRef = useRef("");
    const sendFeedback = useCallback(async (rating) => {
        setFeedbackGiven(rating);
        updateStats(s => {
            if (rating === "up")
                s.feedbackUp++;
            else
                s.feedbackDown++;
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
        }
        catch { /* ignore */ }
        // Hide after brief confirmation
        setTimeout(() => {
            setShowFeedback(false);
            setFeedbackGiven(null);
        }, 800);
    }, [config.game, config.character, updateStats]);
    const showFeedbackButtons = useCallback((cycle, text) => {
        lastCycleRef.current = cycle;
        lastTextRef.current = text;
        setFeedbackGiven(null);
        setShowFeedback(true);
        if (feedbackTimer.current)
            clearTimeout(feedbackTimer.current);
        feedbackTimer.current = window.setTimeout(() => {
            setShowFeedback(false);
            setFeedbackGiven(null);
        }, 6000);
    }, []);
    // Drag support
    const isDragging = useRef(false);
    const dragStart = useRef({ x: 0, y: 0 });
    const handleMouseDown = useCallback((e) => {
        if (e.target.closest(".ctrl-btn"))
            return;
        isDragging.current = true;
        dragStart.current = { x: e.screenX, y: e.screenY };
    }, []);
    useEffect(() => {
        const handleMouseMove = async (e) => {
            if (!isDragging.current || !tauriWindow || !tauriDpi)
                return;
            const dx = e.screenX - dragStart.current.x;
            const dy = e.screenY - dragStart.current.y;
            dragStart.current = { x: e.screenX, y: e.screenY };
            try {
                const win = tauriWindow.getCurrentWindow();
                const pos = await win.outerPosition();
                await win.setPosition(new tauriDpi.PhysicalPosition(pos.x + dx, pos.y + dy));
            }
            catch { /* ignore */ }
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
    function typewriteText(text, onDone) {
        if (typewriterRef.current)
            clearInterval(typewriterRef.current);
        let i = 0;
        if (speechRef.current)
            speechRef.current.textContent = "";
        typewriterRef.current = window.setInterval(() => {
            if (i < text.length) {
                i++;
                if (speechRef.current)
                    speechRef.current.textContent = text.substring(0, i);
            }
            else {
                if (typewriterRef.current)
                    clearInterval(typewriterRef.current);
                if (onDone)
                    onDone();
            }
        }, 22);
    }
    // Click-through toggle + debug toggle
    useEffect(() => {
        const handleKeyDown = (e) => {
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
        const handleKeyUp = (e) => {
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
        const evtSourceRef = { current: null };
        let reconnectTimer = null;
        function connect() {
            const es = new EventSource("http://localhost:8080/stream");
            evtSourceRef.current = es;
            es.onopen = () => {
                dispatch({ type: "CONNECTED" });
                // Greeting — character is alive from the start
                if (speechRef.current)
                    speechRef.current.textContent = "음~ 게임 시작하는 거야?";
                dispatch({
                    type: "RESPONSE",
                    payload: { text: "음~ 게임 시작하는 거야?", face: "", mood: "chill", cycle: 0, elapsedMs: 0, costEstimate: "" },
                });
                if (bubbleTimer.current)
                    clearTimeout(bubbleTimer.current);
                bubbleTimer.current = window.setTimeout(() => dispatch({ type: "HIDE_BUBBLE" }), 5000);
            };
            es.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === "thinking") {
                    dispatch({ type: "THINKING" });
                }
                else if (data.type === "status") {
                    // Internal status — don't show to user
                    // --- Streaming: text appears as Claude generates it ---
                }
                else if (data.type === "stream_start") {
                    if (typewriterRef.current)
                        clearInterval(typewriterRef.current);
                    if (speechRef.current)
                        speechRef.current.textContent = "";
                    isStreamingRef.current = true;
                    dispatch({ type: "THINKING" });
                }
                else if (data.type === "stream_chunk") {
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
                }
                else if (data.type === "stream_end") {
                    // Final response with metadata
                    const r = {
                        text: data.text,
                        face: data.face,
                        mood: data.mood || "chill",
                        cycle: data.cycle,
                        elapsedMs: data.elapsed_ms,
                        costEstimate: data.cost_estimate || "?",
                    };
                    dispatch({ type: "RESPONSE", payload: r });
                    dispatch({ type: "SPEAKING_DONE" });
                    if (speechRef.current)
                        speechRef.current.textContent = data.text;
                    // Track stats from stream_end
                    updateStats(s => {
                        s.apiCalls++;
                        const mode = data.debug?.mode || "react";
                        if (mode === "burst")
                            s.reactionCount.burst++;
                        else if (mode === "chat")
                            s.reactionCount.chat++;
                        else
                            s.reactionCount.react++;
                        // Parse cost from debug or cost_estimate
                        const costStr = data.debug?.cost || data.cost_estimate || "0";
                        const costNum = parseFloat(String(costStr).replace(/[^0-9.]/g, ""));
                        if (!isNaN(costNum))
                            s.totalCost += costNum;
                        // Track event type
                        if (data.debug?.event) {
                            const evt = data.debug.event;
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
                    if (bubbleTimer.current)
                        clearTimeout(bubbleTimer.current);
                    const hideMs = Math.min(15000, Math.max(4000, data.text.length * 80));
                    bubbleTimer.current = window.setTimeout(() => {
                        dispatch({ type: "HIDE_BUBBLE" });
                    }, hideMs);
                    // Legacy non-streaming support
                }
                else if (data.type === "response") {
                    const r = {
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
                        if (!isNaN(costNum))
                            s.totalCost += costNum;
                    });
                    if (r.cycle > 0) {
                        showFeedbackButtons(r.cycle, r.text);
                    }
                    if (bubbleTimer.current)
                        clearTimeout(bubbleTimer.current);
                    const hideMs2 = Math.min(15000, Math.max(4000, r.text.length * 80));
                    bubbleTimer.current = window.setTimeout(() => {
                        dispatch({ type: "HIDE_BUBBLE" });
                    }, hideMs2);
                }
                else if (data.type === "error") {
                    // Don't show raw errors to user — just hide the bubble
                    dispatch({ type: "HIDE_BUBBLE" });
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
            if (reconnectTimer)
                clearTimeout(reconnectTimer);
            if (bubbleTimer.current)
                clearTimeout(bubbleTimer.current);
            if (typewriterRef.current)
                clearInterval(typewriterRef.current);
        };
    }, []);
    const handleStop = useCallback(async () => {
        try {
            await tauriCore?.invoke("stop_companion");
        }
        catch {
            window.close();
        }
    }, []);
    const handleQuit = useCallback(async () => {
        try {
            await tauriCore?.invoke("quit_app");
        }
        catch {
            window.close();
        }
    }, []);
    return (_jsxs("div", { className: `overlay-root overlay-${config.position}`, children: [_jsxs("div", { className: `companion-widget ${state.showBubble ? "expanded" : ""} ${state.isThinking ? "thinking" : ""}`, onMouseDown: handleMouseDown, style: { cursor: "grab" }, children: [_jsxs("div", { className: "overlay-controls", children: [_jsx("button", { type: "button", className: "ctrl-btn", onClick: handleStop, title: "\uC124\uC815\uC73C\uB85C \uB3CC\uC544\uAC00\uAE30", children: "\u2699" }), _jsx("button", { type: "button", className: "ctrl-btn ctrl-quit", onClick: handleQuit, title: "\uC885\uB8CC", children: "\u2715" })] }), _jsx("div", { className: "avatar-container", onClick: () => dispatch({ type: "TOGGLE_BUBBLE" }), children: _jsx(CharacterAvatar, { character: config.character, mood: state.isThinking ? "thinking" : state.detailedMood, isSpeaking: state.isSpeaking }) }), state.showBubble && (_jsxs("div", { className: "speech-bubble", children: [state.isThinking ? (_jsx("div", { className: "thinking-text", children: "\uC0DD\uAC01 \uC911..." })) : (_jsx("div", { className: "speech-text", ref: speechRef, children: statusText })), showFeedback && !state.isThinking && (_jsxs("div", { className: "feedback-buttons", children: [_jsx("button", { type: "button", className: `feedback-btn ${feedbackGiven === "up" ? "feedback-selected-up" : ""} ${feedbackGiven === "down" ? "feedback-other" : ""}`, onClick: () => sendFeedback("up"), disabled: feedbackGiven !== null, title: "\uC88B\uC544\uC694", children: "\u25B2" }), _jsx("button", { type: "button", className: `feedback-btn ${feedbackGiven === "down" ? "feedback-selected-down" : ""} ${feedbackGiven === "up" ? "feedback-other" : ""}`, onClick: () => sendFeedback("down"), disabled: feedbackGiven !== null, title: "\uBCC4\uB85C\uC5D0\uC694", children: "\u25BC" })] }))] })), _jsx("div", { className: `connection-dot ${state.connected ? "connected" : ""}` }), showDebug && debugInfo && _jsx("div", { className: "debug-bar", children: debugInfo })] }), showTextFeedback && (_jsx(FeedbackForm, { onClose: () => setShowTextFeedback(false), game: config.game, character: config.character })), _jsx(StatsPanel, { visible: showStats, stats: stats })] }));
}
