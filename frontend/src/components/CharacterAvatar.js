import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useRef, useState, memo, useCallback } from "react";
import "./CharacterAvatar.css";
// Expression mappings per character — mood + speaking state → image file
const NOZOMI_EXPRESSIONS = {
    "excited_speaking": "nozomi_casual_happy.webp",
    "curious_speaking": "nozomi_casual_normaltalk.webp",
    "worried_speaking": "nozomi_casual_sadtalk1.webp",
    "chill_speaking": "nozomi_casual_normaltalk.webp",
    "amused_speaking": "nozomi_casual_normaltalk.webp",
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
const CHARACTER_DEFAULTS = {
    nozomi: "nozomi_casual_normal.webp",
};
function CharacterAvatar({ character, mood, isSpeaking = false }) {
    // Crossfade state: track current and previous images
    const [frontImg, setFrontImg] = useState("");
    const [backImg, setBackImg] = useState("");
    const [showFront, setShowFront] = useState(true);
    // Blink animation — randomized interval
    const blinkRef = useRef(null);
    const blinkTimerRef = useRef(null);
    const isNozomi = character === "nozomi";
    const isLottie = LOTTIE_CHARACTERS.includes(character);
    // Resolve expression image for current mood + speaking state
    const resolveImage = useCallback((m, speaking) => {
        const key = speaking ? `${m}_speaking` : m;
        return (NOZOMI_EXPRESSIONS[key] ||
            NOZOMI_EXPRESSIONS[m] ||
            CHARACTER_DEFAULTS.nozomi ||
            "");
    }, []);
    // Crossfade when expression changes
    useEffect(() => {
        if (!isNozomi)
            return;
        const nextImg = resolveImage(mood, isSpeaking);
        const currentVisible = showFront ? frontImg : backImg;
        if (nextImg === currentVisible)
            return; // no change
        if (showFront) {
            // Load next into back layer, then flip
            setBackImg(nextImg);
            // Allow a frame for the img src to set before transitioning
            requestAnimationFrame(() => setShowFront(false));
        }
        else {
            setFrontImg(nextImg);
            requestAnimationFrame(() => setShowFront(true));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mood, isSpeaking, isNozomi, resolveImage]);
    // Initialize first image without transition
    useEffect(() => {
        if (!isNozomi)
            return;
        const img = resolveImage(mood, isSpeaking);
        setFrontImg(img);
        setBackImg(img);
        setShowFront(true);
        // Only run on mount
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isNozomi]);
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
            if (blinkTimerRef.current)
                clearTimeout(blinkTimerRef.current);
        };
    }, [scheduleBlink]);
    if (isNozomi) {
        const defaultSrc = `/characters/nozomi/${CHARACTER_DEFAULTS.nozomi}`;
        return (_jsxs("div", { ref: blinkRef, className: `avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`, children: [_jsx("img", { src: backImg ? `/characters/nozomi/${backImg}` : defaultSrc, alt: mood, className: `sprite-img crossfade-layer ${!showFront ? "crossfade-visible" : "crossfade-hidden"}`, draggable: false }), _jsx("img", { src: frontImg ? `/characters/nozomi/${frontImg}` : defaultSrc, alt: mood, className: `sprite-img crossfade-layer ${showFront ? "crossfade-visible" : "crossfade-hidden"}`, draggable: false })] }));
    }
    if (isLottie) {
        return (_jsx("div", { className: `avatar-sprite mood-${mood} ${isSpeaking ? "speaking" : "idle"}`, children: _jsx(LottieAvatar, { character: character, mood: mood }) }));
    }
    // Fallback
    return (_jsx("div", { className: `avatar-sprite mood-${mood}`, children: _jsx("div", { className: "avatar-fallback", children: character.charAt(0).toUpperCase() }) }));
}
// Lottie avatar for non-Nozomi characters
function LottieAvatar({ character, mood }) {
    const containerRef = useRef(null);
    const [, setLoaded] = useState(false);
    useEffect(() => {
        let anim = null;
        async function loadLottie() {
            try {
                const lottie = await import("lottie-web");
                if (!containerRef.current)
                    return;
                anim = lottie.default.loadAnimation({
                    container: containerRef.current,
                    renderer: "svg",
                    loop: true,
                    autoplay: true,
                    path: `/lottie/${character}.json`,
                });
                setLoaded(true);
                // Adjust speed based on mood
                const speeds = {
                    excited: 2.0, thinking: 0.5, worried: 1.5, amused: 1.3,
                };
                anim.setSpeed(speeds[mood] || 1.0);
            }
            catch { /* lottie not available */ }
        }
        loadLottie();
        return () => { anim?.destroy(); };
    }, [character]);
    useEffect(() => {
        // Speed changes don't need full reload
    }, [mood]);
    return _jsx("div", { ref: (el) => { containerRef.current = el; }, className: "lottie-container" });
}
export default memo(CharacterAvatar);
