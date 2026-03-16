import { useEffect, useRef, useState, memo } from "react";
import type { AppConfig } from "../types";
import "./CharacterAvatar.css";

interface Props {
  character: AppConfig["character"];
  mood: string;
  isSpeaking?: boolean;
}

// Expression mappings per character — mood + speaking state → image file
const NOZOMI_EXPRESSIONS: Record<string, string> = {
  "excited_speaking": "nozomi_casual_happy.webp",
  "curious_speaking": "nozomi_casual_normaltalk.webp",
  "worried_speaking": "nozomi_casual_sadtalk1.webp",
  "chill_speaking": "nozomi_casual_normaltalk.webp",
  "amused_speaking": "nozomi_casual_evilsmirk.webp",
  "thinking_speaking": "nozomi_casual_normaltalk.webp",
  "angry_speaking": "nozomi_casual_angrytalk.webp",
  "sad_speaking": "nozomi_casual_sadtalk2.webp",
  "excited": "nozomi_casual_happy.webp",
  "curious": "nozomi_casual_huh.webp",
  "worried": "nozomi_casual_sad1.webp",
  "chill": "nozomi_casual_normal.webp",
  "amused": "nozomi_casual_evilsmirk.webp",
  "thinking": "nozomi_casual_frown.webp",
  "angry": "nozomi_casual_angry.webp",
  "disgusted": "nozomi_casual_disgusted.webp",
  "blush": "nozomi_casual_blush.webp",
  "pout": "nozomi_casual_pout.webp",
  "sad": "nozomi_casual_sad2.webp",
};

// Fallback for non-Nozomi characters — uses Lottie animations
const LOTTIE_CHARACTERS = ["robot", "cat", "ghost", "fox", "slime"];

const CHARACTER_DEFAULTS: Record<string, string> = {
  nozomi: "nozomi_casual_normal.webp",
};

function CharacterAvatar({ character, mood, isSpeaking = false }: Props) {
  const [currentImg, setCurrentImg] = useState("");

  const isNozomi = character === "nozomi";
  const isLottie = LOTTIE_CHARACTERS.includes(character);

  useEffect(() => {
    if (!isNozomi) return;

    const key = isSpeaking ? `${mood}_speaking` : mood;
    const img = NOZOMI_EXPRESSIONS[key] || NOZOMI_EXPRESSIONS[mood] || CHARACTER_DEFAULTS.nozomi;
    setCurrentImg(img);
  }, [mood, isSpeaking, isNozomi]);

  if (isNozomi) {
    return (
      <div className={`avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`}>
        <img
          src={`/characters/nozomi/${currentImg || CHARACTER_DEFAULTS.nozomi}`}
          alt={mood}
          className="sprite-img"
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
      <div className="avatar-fallback">{character[0].toUpperCase()}</div>
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
