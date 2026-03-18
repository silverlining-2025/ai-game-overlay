import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useRef, useState } from "react";
import "./FeedbackForm.css";
export default function FeedbackForm({ onClose, game, character }) {
    const [text, setText] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const inputRef = useRef(null);
    const containerRef = useRef(null);
    // Auto-focus on mount
    useEffect(() => {
        inputRef.current?.focus();
    }, []);
    // Click outside to close
    useEffect(() => {
        function handleClickOutside(e) {
            if (containerRef.current && !containerRef.current.contains(e.target)) {
                onClose();
            }
        }
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, [onClose]);
    // ESC to close
    useEffect(() => {
        function handleKey(e) {
            if (e.key === "Escape") {
                onClose();
            }
        }
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, [onClose]);
    // Auto-close after submission
    useEffect(() => {
        if (submitted) {
            const timer = setTimeout(onClose, 2000);
            return () => clearTimeout(timer);
        }
    }, [submitted, onClose]);
    async function handleSubmit() {
        const trimmed = text.trim();
        if (!trimmed)
            return;
        try {
            await fetch("http://localhost:8080/text-feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    timestamp: new Date().toISOString(),
                    type: "text",
                    text: trimmed,
                    game,
                    character,
                }),
            });
        }
        catch (err) {
            console.error("Failed to submit feedback:", err);
        }
        setSubmitted(true);
    }
    function handleKeyDown(e) {
        if (e.key === "Enter") {
            e.preventDefault();
            handleSubmit();
        }
    }
    return (_jsx("div", { className: "feedback-overlay", ref: containerRef, children: submitted ? (_jsx("div", { className: "feedback-confirm", children: "\uAC10\uC0AC\uD569\uB2C8\uB2E4!" })) : (_jsx("input", { ref: inputRef, className: "feedback-input", type: "text", placeholder: "\uD53C\uB4DC\uBC31\uC744 \uC785\uB825\uD558\uC138\uC694...", value: text, onChange: (e) => setText(e.target.value), onKeyDown: handleKeyDown })) }));
}
