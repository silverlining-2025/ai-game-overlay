import { useEffect, useRef } from "react";
import lottie, { type AnimationItem } from "lottie-web";
import type { AppConfig, CompanionReaction } from "../types";
import "./CharacterAvatar.css";

interface Props {
  character: AppConfig["character"];
  mood: CompanionReaction["mood"];
}

const LOTTIE_FILES: Record<AppConfig["character"], string> = {
  robot: "/lottie/robot.json",
  cat: "/lottie/cat.json",
  ghost: "/lottie/ghost.json",
  fox: "/lottie/fox.json",
  slime: "/lottie/slime.json",
};

export default function CharacterAvatar({ character, mood }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const animRef = useRef<AnimationItem | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Clean up previous animation
    if (animRef.current) {
      animRef.current.destroy();
    }

    animRef.current = lottie.loadAnimation({
      container: containerRef.current,
      renderer: "svg",
      loop: true,
      autoplay: true,
      path: LOTTIE_FILES[character],
    });

    return () => {
      if (animRef.current) {
        animRef.current.destroy();
        animRef.current = null;
      }
    };
  }, [character]);

  // Change animation speed based on mood
  useEffect(() => {
    if (!animRef.current) return;
    switch (mood) {
      case "excited":
        animRef.current.setSpeed(2.0);
        break;
      case "thinking":
        animRef.current.setSpeed(0.5);
        break;
      case "worried":
        animRef.current.setSpeed(1.5);
        break;
      default:
        animRef.current.setSpeed(1.0);
    }
  }, [mood]);

  return (
    <div className={`avatar mood-${mood}`}>
      <div ref={containerRef} className="lottie-container" />
    </div>
  );
}
