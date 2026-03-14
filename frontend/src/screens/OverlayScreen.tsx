import { useEffect, useRef, useState } from "react";
import type { AppConfig, CompanionReaction } from "../types";
import CharacterAvatar from "../components/CharacterAvatar";
import "./OverlayScreen.css";

interface Props {
  config: AppConfig;
}

export default function OverlayScreen({ config }: Props) {
  const [reaction, setReaction] = useState<CompanionReaction | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [displayText, setDisplayText] = useState("");
  const [showBubble, setShowBubble] = useState(false);
  const [, setHistory] = useState<CompanionReaction[]>([]);
  const bubbleTimer = useRef<number | null>(null);
  const typewriterRef = useRef<number | null>(null);

  // Connect to Python backend SSE stream
  useEffect(() => {
    const baseUrl = "http://localhost:8080";
    const evtSource = new EventSource(`${baseUrl}/stream`);

    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "thinking") {
        setIsThinking(true);
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

        // Add to history
        setHistory((prev) => [r, ...prev].slice(0, 5));

        // Typewriter effect
        typewriteText(r.text);

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
      setIsThinking(false);
    };

    return () => {
      evtSource.close();
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current);
      if (typewriterRef.current) clearInterval(typewriterRef.current);
    };
  }, []);

  function typewriteText(text: string) {
    if (typewriterRef.current) clearInterval(typewriterRef.current);
    let i = 0;
    setDisplayText("");
    typewriterRef.current = window.setInterval(() => {
      if (i < text.length) {
        i++;
        setDisplayText(text.substring(0, i));
      } else {
        if (typewriterRef.current) clearInterval(typewriterRef.current);
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

  return (
    <div className={`overlay-root ${positionClass}`}>
      <div className={`companion-widget ${showBubble ? "expanded" : ""} ${isThinking ? "thinking" : ""}`}>
        <div className="avatar-container" onClick={() => setShowBubble(!showBubble)}>
          <CharacterAvatar
            character={config.character}
            mood={isThinking ? "thinking" : (reaction?.mood || "chill")}
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
      </div>
    </div>
  );
}
