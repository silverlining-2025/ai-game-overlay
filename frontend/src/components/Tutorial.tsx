import { useState } from "react";
import { useTranslation } from "../i18n/useTranslation";
import "./Tutorial.css";

interface Props {
  onComplete: () => void;
}

interface Slide {
  icon: string;
  titleKey: string;
  descKey: string;
  featureKeys?: Array<{ icon: string; key: string }>;
  safeBadge?: boolean;
}

const SLIDES: Slide[] = [
  {
    icon: "\uD83C\uDFAE", // game controller
    titleKey: "tutorial.slide1_title",
    descKey: "tutorial.slide1_desc",
  },
  {
    icon: "\uD83D\uDCF7", // camera
    titleKey: "tutorial.slide2_title",
    descKey: "tutorial.slide2_desc",
    featureKeys: [
      { icon: "\uD83D\uDDA5\uFE0F", key: "tutorial.slide2_feature1" },
      { icon: "\uD83E\uDDE0", key: "tutorial.slide2_feature2" },
      { icon: "\uD83D\uDCAC", key: "tutorial.slide2_feature3" },
    ],
  },
  {
    icon: "\u2328\uFE0F", // keyboard
    titleKey: "tutorial.slide3_title",
    descKey: "tutorial.slide3_desc",
    featureKeys: [
      { icon: "\uD83D\uDDE8\uFE0F", key: "tutorial.slide3_key1" },
      { icon: "\uD83D\uDC1B", key: "tutorial.slide3_key2" },
      { icon: "\uD83D\uDCCA", key: "tutorial.slide3_key3" },
      { icon: "\uD83D\uDCDD", key: "tutorial.slide3_key4" },
    ],
  },
  {
    icon: "\uD83D\uDEE1\uFE0F", // shield
    titleKey: "tutorial.slide4_title",
    descKey: "tutorial.slide4_desc",
    featureKeys: [
      { icon: "\u2705", key: "tutorial.slide4_feature1" },
      { icon: "\u2705", key: "tutorial.slide4_feature2" },
      { icon: "\u2705", key: "tutorial.slide4_feature3" },
    ],
    safeBadge: true,
  },
];

export default function Tutorial({ onComplete }: Props) {
  const { t } = useTranslation();
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
          {t("tutorial.skip")}
        </button>

        <div className="tutorial-slide-content" key={slideIndex}>
          <div className="tutorial-illustration">
            <span className="tutorial-illustration-icon">{slide.icon}</span>
          </div>

          <h2 className="tutorial-slide-title">{t(slide.titleKey as any)}</h2>
          <p className="tutorial-slide-desc">{t(slide.descKey as any)}</p>

          {slide.featureKeys && (
            <div className="tutorial-features">
              {slide.featureKeys.map((f, i) => (
                <div className="tutorial-feature-item" key={i}>
                  <span className="tutorial-feature-icon">{f.icon}</span>
                  <span>{t(f.key as any)}</span>
                </div>
              ))}
            </div>
          )}

          {slide.safeBadge && (
            <div className="tutorial-safe-badge">
              <span>{"\uD83D\uDEE1\uFE0F"}</span>
              <span>{t("tutorial.slide4_desc")}</span>
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
            {t("tutorial.prev")}
          </button>
          <button
            type="button"
            className="tutorial-btn-next"
            onClick={handleNext}
          >
            {isLast ? t("tutorial.done") : t("tutorial.next")}
          </button>
        </div>

        <div className="tutorial-dont-show">
          <input
            type="checkbox"
            id="tutorial-dont-show"
            checked={dontShowAgain}
            onChange={(e) => setDontShowAgain(e.target.checked)}
          />
          <label htmlFor="tutorial-dont-show">{t("tutorial.dont_show")}</label>
        </div>
      </div>
    </div>
  );
}
