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

// Mood → talk variant for mouth-flap animation
const MOOD_TO_TALK: Record<string, string> = {
  "excited": "normaltalk",
  "curious": "normaltalk",
  "worried": "sadtalk1",
  "chill": "normaltalk",
  "amused": "normaltalk",
  "thinking": "normaltalk",
  "angry": "angrytalk",
  "sad": "sadtalk2",
  "disgusted": "normaltalk",
  "blush": "normaltalk",
  "pout": "normaltalk",
};

// Characters that have sprite assets in /characters/<name>/
const SPRITE_CHARACTERS = ["nozomi"];
const DEFAULT_OUTFIT = "casual";

// Fallback characters — uses Lottie animations
const LOTTIE_CHARACTERS = ["robot", "cat", "ghost", "fox", "slime"];

// --- Spring physics for reactive animations ---
function createSpring(stiffness = 180, damping = 12) {
  let position = 0;
  let velocity = 0;
  const target = 0;

  return {
    impulse(force: number) {
      velocity += force;
    },
    update(dt: number): number {
      const springForce = -stiffness * (position - target);
      const dampingForce = -damping * velocity;
      velocity += (springForce + dampingForce) * dt;
      position += velocity * dt;
      return position;
    },
    get value() { return position; },
    get isSettled() { return Math.abs(position) < 0.1 && Math.abs(velocity) < 0.1; },
  };
}

// Mood → spring impulse config
const MOOD_IMPULSES: Record<string, { y: number; scale: number; rotate: number }> = {
  excited:   { y: -40, scale: 8, rotate: 0 },
  angry:     { y: 0, scale: -5, rotate: 15 },
  worried:   { y: 5, scale: -3, rotate: -5 },
  sad:       { y: 8, scale: -4, rotate: 0 },
  amused:    { y: -20, scale: 5, rotate: 3 },
  blush:     { y: -10, scale: 3, rotate: -3 },
  curious:   { y: -15, scale: 2, rotate: 5 },
  disgusted: { y: 0, scale: -3, rotate: -8 },
  pout:      { y: 0, scale: -2, rotate: -3 },
};


function CharacterAvatar({ character, mood, isSpeaking = false }: Props) {
  // Crossfade state
  const [frontImg, setFrontImg] = useState("");
  const [backImg, setBackImg] = useState("");
  const [showFront, setShowFront] = useState(true);

  // Mouth-flap state for speaking
  const [mouthOpen, setMouthOpen] = useState(false);
  const mouthTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Spring physics refs
  const springY = useRef(createSpring(180, 12));
  const springScale = useRef(createSpring(120, 10));
  const springRotate = useRef(createSpring(100, 8));
  const animFrameRef = useRef<number>(0);
  const spriteRef = useRef<HTMLDivElement | null>(null);

  // Micro-animation refs
  const microRef = useRef({ swayX: 0, swayY: 0, breathPhase: 0 });

  // Blink animation
  const blinkTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasSprites = SPRITE_CHARACTERS.includes(character);
  const isLottie = !hasSprites && LOTTIE_CHARACTERS.includes(character);

  // Resolve expression image for current mood
  const resolveImage = useCallback(
    (m: string, speaking: boolean, mouth: boolean): string => {
      // During speaking: alternate between expression and talk variant
      if (speaking && mouth) {
        const talkExpr = MOOD_TO_TALK[m] || "normaltalk";
        return `${character}_${DEFAULT_OUTFIT}_${talkExpr}.webp`;
      }
      const key = speaking ? `${m}_speaking` : m;
      const expression = MOOD_TO_EXPRESSION[key] || MOOD_TO_EXPRESSION[m] || "normal";
      return `${character}_${DEFAULT_OUTFIT}_${expression}.webp`;
    },
    [character],
  );

  // --- Layer 3: Mouth-flap animation during speech ---
  useEffect(() => {
    if (isSpeaking && hasSprites) {
      // Toggle mouth open/closed every 150-250ms
      mouthTimerRef.current = setInterval(() => {
        setMouthOpen(prev => !prev);
      }, 180 + Math.random() * 70);
    } else {
      setMouthOpen(false);
      if (mouthTimerRef.current) clearInterval(mouthTimerRef.current);
    }
    return () => {
      if (mouthTimerRef.current) clearInterval(mouthTimerRef.current);
    };
  }, [isSpeaking, hasSprites]);

  // --- Crossfade when expression changes ---
  useEffect(() => {
    if (!hasSprites) return;

    const nextImg = resolveImage(mood, isSpeaking, mouthOpen);
    const currentVisible = showFront ? frontImg : backImg;

    if (nextImg === currentVisible) return;

    if (showFront) {
      setBackImg(nextImg);
      requestAnimationFrame(() => setShowFront(false));
    } else {
      setFrontImg(nextImg);
      requestAnimationFrame(() => setShowFront(true));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mood, isSpeaking, mouthOpen, hasSprites, resolveImage]);

  // Initialize first image
  useEffect(() => {
    if (!hasSprites) return;
    const img = resolveImage(mood, isSpeaking, false);
    setFrontImg(img);
    setBackImg(img);
    setShowFront(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSprites, character]);

  // --- Layer 4: Spring physics — fire impulse on mood change ---
  const prevMoodRef = useRef(mood);
  useEffect(() => {
    if (mood === prevMoodRef.current) return;
    prevMoodRef.current = mood;

    const impulse = MOOD_IMPULSES[mood];
    if (impulse) {
      springY.current.impulse(impulse.y);
      springScale.current.impulse(impulse.scale);
      springRotate.current.impulse(impulse.rotate);
    }
  }, [mood]);

  // --- Layer 2 + 4: Combined animation loop (micro-sway + spring physics) ---
  useEffect(() => {
    if (!hasSprites) return;

    let lastTime = performance.now();
    const micro = microRef.current;

    function tick(now: number) {
      const dt = Math.min((now - lastTime) / 1000, 0.05); // cap at 50ms
      lastTime = now;

      // Layer 2: Micro-sway (random gentle drift)
      micro.breathPhase += dt * 1.8; // ~0.55Hz breathing
      micro.swayX += (Math.random() - 0.5) * 0.3;
      micro.swayY += (Math.random() - 0.5) * 0.2;
      micro.swayX *= 0.95; // dampen
      micro.swayY *= 0.95;

      const breathY = Math.sin(micro.breathPhase) * 2.5;
      const driftX = micro.swayX;
      const driftY = micro.swayY;

      // Layer 4: Spring physics
      const sY = springY.current.update(dt);
      const sScale = springScale.current.update(dt);
      const sRotate = springRotate.current.update(dt);

      // Combine all transforms
      const el = spriteRef.current;
      if (el) {
        const totalY = breathY + driftY + sY;
        const totalX = driftX;
        const scale = 1 + sScale * 0.01;
        const rotate = sRotate * 0.1;
        el.style.transform = `translate(${totalX.toFixed(2)}px, ${totalY.toFixed(2)}px) scale(${scale.toFixed(4)}) rotate(${rotate.toFixed(2)}deg)`;
      }

      animFrameRef.current = requestAnimationFrame(tick);
    }

    animFrameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [hasSprites]);

  // --- Blink cycle ---
  const scheduleBlink = useCallback(() => {
    const delay = 3000 + Math.random() * 3000;
    blinkTimerRef.current = setTimeout(() => {
      const el = spriteRef.current;
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

  // --- Render: Sprite characters ---
  if (hasSprites) {
    const defaultSrc = `/characters/${character}/${character}_${DEFAULT_OUTFIT}_normal.webp`;
    return (
      <div
        ref={spriteRef}
        className={`avatar-sprite ${isSpeaking ? "speaking" : ""}`}
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

  // --- Render: Lottie characters ---
  if (isLottie) {
    return (
      <div className={`avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`}>
        <LottieAvatar character={character} mood={mood} />
      </div>
    );
  }

  // --- Render: Fallback ---
  return (
    <div className={`avatar-sprite mood-${mood}`}>
      <div className="avatar-fallback">{character.charAt(0).toUpperCase()}</div>
    </div>
  );
}

// Lottie avatar for non-sprite characters
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
