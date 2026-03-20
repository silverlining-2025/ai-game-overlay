import { useEffect, useRef, useState, memo, useCallback } from "react";
import type { AppConfig } from "../types";
import "./CharacterAvatar.css";

interface Props {
  character: AppConfig["character"];
  mood: string;
  isSpeaking?: boolean;
}

// Mood → expression file suffix mapping (works for any character with sprites)
// Naming convention: {character}_{outfit}_{expression}.webp
const MOOD_TO_EXPRESSION: Record<string, string> = {
  "excited_speaking": "happy",
  "curious_speaking": "normaltalk",
  "worried_speaking": "sadtalk1",
  "chill_speaking": "normaltalk",
  "amused_speaking": "normaltalk",
  "thinking_speaking": "normaltalk",
  "angry_speaking": "angrytalk",
  "sad_speaking": "sadtalk2",
  "excited": "happy",
  "curious": "huh",
  "worried": "sad1",
  "chill": "normal",
  "amused": "evilsmirk",
  "thinking": "frown",
  "angry": "angry",
  "disgusted": "disgusted",
  "blush": "blush",
  "pout": "pout",
  "sad": "sad2",
};

// Characters that have sprite assets in /characters/<name>/
// Add a character here once their sprites are generated
const SPRITE_CHARACTERS = ["nozomi", "keiko"];
const DEFAULT_OUTFIT = "casual";

// Fallback characters — uses Lottie animations
const LOTTIE_CHARACTERS = ["robot", "cat", "ghost", "fox", "slime"];

function CharacterAvatar({ character, mood, isSpeaking = false }: Props) {
  // Crossfade state: track current and previous images
  const [frontImg, setFrontImg] = useState("");
  const [backImg, setBackImg] = useState("");
  const [showFront, setShowFront] = useState(true);

  // Blink animation — randomized interval
  const blinkRef = useRef<HTMLDivElement | null>(null);
  const blinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasSprites = SPRITE_CHARACTERS.includes(character);
  const isLottie = !hasSprites && LOTTIE_CHARACTERS.includes(character);

  // Resolve expression image for current mood + speaking state
  const resolveImage = useCallback(
    (m: string, speaking: boolean): string => {
      const key = speaking ? `${m}_speaking` : m;
      const expression = MOOD_TO_EXPRESSION[key] || MOOD_TO_EXPRESSION[m] || "normal";
      return `${character}_${DEFAULT_OUTFIT}_${expression}.webp`;
    },
    [character],
  );

  // Crossfade when expression changes
  useEffect(() => {
    if (!hasSprites) return;

    const nextImg = resolveImage(mood, isSpeaking);
    const currentVisible = showFront ? frontImg : backImg;

    if (nextImg === currentVisible) return; // no change

    if (showFront) {
      // Load next into back layer, then flip
      setBackImg(nextImg);
      // Allow a frame for the img src to set before transitioning
      requestAnimationFrame(() => setShowFront(false));
    } else {
      setFrontImg(nextImg);
      requestAnimationFrame(() => setShowFront(true));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mood, isSpeaking, hasSprites, resolveImage]);

  // Initialize first image without transition
  useEffect(() => {
    if (!hasSprites) return;
    const img = resolveImage(mood, isSpeaking);
    setFrontImg(img);
    setBackImg(img);
    setShowFront(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSprites, character]);

  // Eye blink cycle — randomized CSS class toggle
  const scheduleBlink = useCallback(() => {
    const delay = 3000 + Math.random() * 3000; // 3-6s
    blinkTimerRef.current = setTimeout(() => {
      const el = blinkRef.current;
      if (el) {
        el.classList.add("blink");
        setTimeout(() => {
          el.classList.remove("blink");
          scheduleBlink();
        }, 150);
      }
    }, delay);
  }, []);

  useEffect(() => {
    scheduleBlink();
    return () => {
      if (blinkTimerRef.current) clearTimeout(blinkTimerRef.current);
    };
  }, [scheduleBlink]);

  if (hasSprites) {
    const defaultSrc = `/characters/${character}/${character}_${DEFAULT_OUTFIT}_normal.webp`;
    return (
      <div
        ref={blinkRef}
        className={`avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`}
      >
        {/* Back layer */}
        <img
          src={backImg ? `/characters/${character}/${backImg}` : defaultSrc}
          alt={mood}
          className={`sprite-img crossfade-layer ${!showFront ? "crossfade-visible" : "crossfade-hidden"}`}
          draggable={false}
        />
        {/* Front layer */}
        <img
          src={frontImg ? `/characters/${character}/${frontImg}` : defaultSrc}
          alt={mood}
          className={`sprite-img crossfade-layer ${showFront ? "crossfade-visible" : "crossfade-hidden"}`}
          draggable={false}
        />
      </div>
    );
  }

  if (isLottie) {
    return (
      <div className={`avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`}>
        <LottieAvatar character={character} mood={mood} />
      </div>
    );
  }

  // Fallback
  return (
    <div className={`avatar-sprite mood-${mood}`}>
      <div className="avatar-fallback">{character.charAt(0).toUpperCase()}</div>
    </div>
  );
}

// Lottie avatar for non-Nozomi characters
function LottieAvatar({ character, mood }: { character: string; mood: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [, setLoaded] = useState(false);

  useEffect(() => {
    let anim: any = null;
    async function loadLottie() {
      try {
        const lottie = await import("lottie-web");
        if (!containerRef.current) return;
        anim = lottie.default.loadAnimation({
          container: containerRef.current,
          renderer: "svg",
          loop: true,
          autoplay: true,
          path: `/lottie/${character}.json`,
        });
        setLoaded(true);

        // Adjust speed based on mood
        const speeds: Record<string, number> = {
          excited: 2.0, thinking: 0.5, worried: 1.5, amused: 1.3,
        };
        anim.setSpeed(speeds[mood] || 1.0);
      } catch { /* lottie not available */ }
    }
    loadLottie();
    return () => { anim?.destroy(); };
  }, [character]);

  useEffect(() => {
    // Speed changes don't need full reload
  }, [mood]);

  return <div ref={(el) => { containerRef.current = el; }} className="lottie-container" />;
}

export default memo(CharacterAvatar);
