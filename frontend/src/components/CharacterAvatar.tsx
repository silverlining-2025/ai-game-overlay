import { useEffect, useState } from "react";
import type { AppConfig, CompanionReaction } from "../types";
import "./CharacterAvatar.css";

interface Props {
  character: AppConfig["character"];
  mood: CompanionReaction["mood"];
  isSpeaking?: boolean;
}

// Nozomi expression mapping — mood + speaking state → image file
const NOZOMI_EXPRESSIONS: Record<string, string> = {
  // Speaking variants
  "excited_speaking": "nozomi_casual_happy.webp",
  "curious_speaking": "nozomi_casual_normaltalk.webp",
  "worried_speaking": "nozomi_casual_sadtalk1.webp",
  "chill_speaking": "nozomi_casual_normaltalk.webp",
  "amused_speaking": "nozomi_casual_evilsmirk.webp",
  "thinking_speaking": "nozomi_casual_normaltalk.webp",
  // Non-speaking variants
  "excited": "nozomi_casual_happy.webp",
  "curious": "nozomi_casual_huh.webp",
  "worried": "nozomi_casual_sad1.webp",
  "chill": "nozomi_casual_normal.webp",
  "amused": "nozomi_casual_evilsmirk.webp",
  "thinking": "nozomi_casual_frown.webp",
  // Additional expression triggers (used by extended mood detection)
  "angry": "nozomi_casual_angry.webp",
  "angry_speaking": "nozomi_casual_angrytalk.webp",
  "disgusted": "nozomi_casual_disgusted.webp",
  "blush": "nozomi_casual_blush.webp",
  "pout": "nozomi_casual_pout.webp",
  "sad": "nozomi_casual_sad2.webp",
  "sad_speaking": "nozomi_casual_sadtalk2.webp",
};

const DEFAULT_EXPRESSION = "nozomi_casual_normal.webp";

// Extended mood detection with more granular emotions
export function detectDetailedMood(text: string): string {
  const checks: [string, string[]][] = [
    ["angry", ["짜증", "화나", "뭐야", "미친", "아 진짜", "ㅡㅡ"]],
    ["disgusted", ["역겹", "에반", "더럽", "우웩"]],
    ["blush", ["부끄", "ㅎㅎ", "헤헤", "귀엽"]],
    ["pout", ["에이", "치", "흥", "삐짐"]],
    ["excited", ["대박", "미쳤", "개쩔", "레전", "헐", "ㄷㄷ", "!!", "와아", "쩔"]],
    ["worried", ["조심", "위험", "HP", "피", "죽", "도망", "에러"]],
    ["amused", ["ㅋㅋ", "ㅎㅎ", "웃", "ㄹㅇ", "ㅋ"]],
    ["curious", ["뭐", "왜", "어떻게", "신기", "궁금", "?"]],
    ["sad", ["슬프", "아쉽", "ㅠㅠ", "ㅜㅜ"]],
  ];

  for (const [mood, keywords] of checks) {
    if (keywords.some(k => text.includes(k))) return mood;
  }
  return "chill";
}

export default function CharacterAvatar({ character, mood, isSpeaking = false }: Props) {
  const [currentImg, setCurrentImg] = useState(DEFAULT_EXPRESSION);
  const [isTransitioning, setIsTransitioning] = useState(false);

  useEffect(() => {
    const key = isSpeaking ? `${mood}_speaking` : mood;
    const img = NOZOMI_EXPRESSIONS[key] || NOZOMI_EXPRESSIONS[mood] || DEFAULT_EXPRESSION;

    if (img !== currentImg) {
      setIsTransitioning(true);
      setTimeout(() => {
        setCurrentImg(img);
        setIsTransitioning(false);
      }, 100);
    }
  }, [mood, isSpeaking, currentImg]);

  return (
    <div className={`avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"} ${isTransitioning ? "transitioning" : ""}`}>
      <img
        src={`/characters/nozomi/${currentImg}`}
        alt={mood}
        className="sprite-img"
        draggable={false}
      />
    </div>
  );
}
