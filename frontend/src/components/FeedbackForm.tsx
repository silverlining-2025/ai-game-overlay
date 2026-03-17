import { useEffect, useRef, useState } from "react";
import "./FeedbackForm.css";

interface Props {
  onClose: () => void;
  game: string;
  character: string;
}

export default function FeedbackForm({ onClose, game, character }: Props) {
  const [text, setText] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-focus on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Click outside to close
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  // ESC to close
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
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
    if (!trimmed) return;

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
    } catch (err) {
      console.error("Failed to submit feedback:", err);
    }

    setSubmitted(true);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="feedback-overlay" ref={containerRef}>
      {submitted ? (
        <div className="feedback-confirm">감사합니다!</div>
      ) : (
        <input
          ref={inputRef}
          className="feedback-input"
          type="text"
          placeholder="피드백을 입력하세요..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
        />
      )}
    </div>
  );
}
