import { useState } from "react";
import "./Tutorial.css";

interface Props {
  onComplete: () => void;
}

interface Slide {
  icon: string;
  title: string;
  description: string;
  features?: Array<{ icon: string; text: string }>;
  safeBadge?: string;
}

const SLIDES: Slide[] = [
  {
    icon: "\uD83C\uDFAE", // game controller
    title: "AI \uCEF4\uD328\uB2C8\uC5B8\uC744 \uB9CC\uB098\uBCF4\uC138\uC694",
    description:
      "\uB2F9\uC2E0\uC758 \uAC8C\uC784 \uD654\uBA74\uC744 \uBCF4\uACE0 \uC2E4\uC2DC\uAC04\uC73C\uB85C \uBC18\uC751\uD558\uB294 AI \uCE5C\uAD6C\uC785\uB2C8\uB2E4. " +
      "\uAC8C\uC784 \uC0C1\uD669\uC5D0 \uB9DE\uB294 \uCF54\uBA58\uD2B8, \uC870\uC5B8, \uAC10\uC815 \uBC18\uC751\uC744 \uC81C\uACF5\uD569\uB2C8\uB2E4. " +
      "\uCE90\uB9AD\uD130\uB97C \uC120\uD0DD\uD558\uACE0 \uB098\uB9CC\uC758 AI \uCE5C\uAD6C\uB97C \uC124\uC815\uD574\uBCF4\uC138\uC694!",
  },
  {
    icon: "\uD83D\uDCF7", // camera
    title: "\uD654\uBA74\uC744 \uBCF4\uACE0 \uBC18\uC751\uD569\uB2C8\uB2E4",
    description:
      "AI \uCEF4\uD328\uB2C8\uC5B8\uC740 \uD654\uBA74 \uCEA1\uCC98\uB97C \uD1B5\uD574 \uAC8C\uC784 \uC0C1\uD669\uC744 \uC774\uD574\uD569\uB2C8\uB2E4.",
    features: [
      { icon: "\uD83D\uDDA5\uFE0F", text: "DXGI \uD654\uBA74 \uCEA1\uCC98 \u2014 OS \uC218\uC900 API \uC0AC\uC6A9" },
      { icon: "\uD83E\uDDE0", text: "AI \uBD84\uC11D \u2014 \uC774\uBBF8\uC9C0 \uC778\uC2DD\uC73C\uB85C \uC0C1\uD669 \uD30C\uC545" },
      { icon: "\uD83D\uDCAC", text: "\uC2E4\uC2DC\uAC04 \uBC18\uC751 \u2014 \uAC8C\uC784 \uD750\uB984\uC5D0 \uB9DE\uB294 \uCF54\uBA58\uD2B8" },
    ],
  },
  {
    icon: "\u2328\uFE0F", // keyboard
    title: "\uC870\uC791 \uBC29\uBC95",
    description: "\uAC04\uB2E8\uD55C \uB2E8\uCD95\uD0A4\uB85C \uCEF4\uD328\uB2C8\uC5B8\uC744 \uC81C\uC5B4\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    features: [
      { icon: "\uD83D\uDDE8\uFE0F", text: "Alt \u2014 \uCEF4\uD328\uB2C8\uC5B8\uACFC \uC0C1\uD638\uC791\uC6A9" },
      { icon: "\uD83D\uDC1B", text: "Ctrl+Shift+D \u2014 \uB514\uBC84\uADF8 \uBAA8\uB4DC" },
      { icon: "\uD83D\uDCCA", text: "Ctrl+Shift+S \u2014 \uD1B5\uACC4 \uD328\uB110" },
      { icon: "\uD83D\uDCDD", text: "Alt+F \u2014 \uD53C\uB4DC\uBC31 \uBCF4\uB0B4\uAE30" },
    ],
  },
  {
    icon: "\uD83D\uDEE1\uFE0F", // shield
    title: "\uC548\uD2F0\uCE58\uD2B8 \uC548\uC804",
    description:
      "\uAC8C\uC784 \uBA54\uBAA8\uB9AC\uB97C \uC77D\uAC70\uB098 \uC218\uC815\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. " +
      "\uC628\uB77C\uC778 \uAC8C\uC784\uC5D0\uC11C\uB3C4 \uC548\uC804\uD558\uAC8C \uC0AC\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
    features: [
      { icon: "\u2705", text: "\uD654\uBA74 \uCEA1\uCC98\uB9CC \uC0AC\uC6A9 \u2014 \uBA54\uBAA8\uB9AC \uC811\uADFC \uC5C6\uC74C" },
      { icon: "\u2705", text: "DLL \uC778\uC81D\uC158 \uC5C6\uC74C \u2014 DirectX/Vulkan \uD6C4\uD0B9 \uC5C6\uC74C" },
      { icon: "\u2705", text: "\uBCC4\uB3C4 \uCC3D \uB3D9\uC791 \u2014 \uAC8C\uC784 \uD504\uB85C\uC138\uC2A4\uC640 \uC644\uC804 \uBD84\uB9AC" },
    ],
    safeBadge:
      "\uD654\uBA74 \uCEA1\uCC98 \uC804\uC6A9 \u2014 \uAC8C\uC784 \uD504\uB85C\uC138\uC2A4\uC5D0 \uC808\uB300 \uC811\uADFC\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4",
  },
];

export default function Tutorial({ onComplete }: Props) {
  const [slideIndex, setSlideIndex] = useState(0);
  const [dontShowAgain, setDontShowAgain] = useState(true);

  const slide = SLIDES[slideIndex]!;
  const isLast = slideIndex === SLIDES.length - 1;

  const handleComplete = () => {
    if (dontShowAgain) {
      localStorage.setItem("tutorial_completed", "true");
    }
    onComplete();
  };

  const handleSkip = () => {
    handleComplete();
  };

  const handleNext = () => {
    if (isLast) {
      handleComplete();
    } else {
      setSlideIndex((i) => i + 1);
    }
  };

  const handlePrev = () => {
    setSlideIndex((i) => Math.max(0, i - 1));
  };

  return (
    <div className="tutorial-overlay">
      <div className="tutorial-card">
        <button type="button" className="tutorial-skip" onClick={handleSkip}>
          건너뛰기
        </button>

        <div className="tutorial-slide-content" key={slideIndex}>
          <div className="tutorial-illustration">
            <span className="tutorial-illustration-icon">{slide.icon}</span>
          </div>

          <h2 className="tutorial-slide-title">{slide.title}</h2>
          <p className="tutorial-slide-desc">{slide.description}</p>

          {slide.features && (
            <div className="tutorial-features">
              {slide.features.map((f, i) => (
                <div className="tutorial-feature-item" key={i}>
                  <span className="tutorial-feature-icon">{f.icon}</span>
                  <span>{f.text}</span>
                </div>
              ))}
            </div>
          )}

          {slide.safeBadge && (
            <div className="tutorial-safe-badge">
              <span>{"\uD83D\uDEE1\uFE0F"}</span>
              <span>{slide.safeBadge}</span>
            </div>
          )}
        </div>

        <div className="tutorial-dots">
          {SLIDES.map((_, i) => (
            <button
              key={i}
              type="button"
              className={`tutorial-dot ${i === slideIndex ? "active" : ""}`}
              onClick={() => setSlideIndex(i)}
              aria-label={`Slide ${i + 1}`}
            />
          ))}
        </div>

        <div className="tutorial-nav">
          <button
            type="button"
            className="tutorial-btn-prev"
            onClick={handlePrev}
            disabled={slideIndex === 0}
          >
            이전
          </button>
          <button
            type="button"
            className="tutorial-btn-next"
            onClick={handleNext}
          >
            {isLast ? "시작하기" : "다음"}
          </button>
        </div>

        <div className="tutorial-dont-show">
          <input
            type="checkbox"
            id="tutorial-dont-show"
            checked={dontShowAgain}
            onChange={(e) => setDontShowAgain(e.target.checked)}
          />
          <label htmlFor="tutorial-dont-show">다시 보지 않기</label>
        </div>
      </div>
    </div>
  );
}
