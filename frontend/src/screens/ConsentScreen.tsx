import { useState } from "react";
import { useTranslation } from "../i18n/useTranslation";
import "./ConsentScreen.css";

interface Props {
  onConsent: () => void;
}

export default function ConsentScreen({ onConsent }: Props) {
  const { t } = useTranslation();
  const [agreed, setAgreed] = useState(false);

  const handleConsent = () => {
    localStorage.setItem("privacy_consent", "true");
    onConsent();
  };

  return (
    <div className="consent-root">
      <div className="consent-card">
        <h1 className="consent-title">{t("consent.title")}</h1>
        <p className="consent-subtitle">
          {t("consent.subtitle")}
        </p>

        <div className="consent-section">
          <div className="consent-section-title">{t("consent.section_title")}</div>
          <div className="consent-items">
            <div className="consent-item">
              <span className="consent-item-icon">🖥️</span>
              <div className="consent-item-text">
                <div className="consent-item-label">{t("consent.item_capture_label")}</div>
                <div className="consent-item-desc">
                  {t("consent.item_capture_desc")}
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">🌐</span>
              <div className="consent-item-text">
                <div className="consent-item-label">{t("consent.item_transfer_label")}</div>
                <div className="consent-item-desc">
                  {t("consent.item_transfer_desc")}
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">🗑️</span>
              <div className="consent-item-text">
                <div className="consent-item-label">{t("consent.item_storage_label")}</div>
                <div className="consent-item-desc">
                  {t("consent.item_storage_desc")}
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">💾</span>
              <div className="consent-item-text">
                <div className="consent-item-label">{t("consent.item_training_label")}</div>
                <div className="consent-item-desc">
                  {t("consent.item_training_desc")}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="consent-safe">
          <span className="consent-safe-icon">🛡️</span>
          <span>
            {t("consent.safety")}
          </span>
        </div>

        <label className="consent-checkbox-row">
          <input
            type="checkbox"
            className="consent-checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          <span className="consent-checkbox-label">
            {t("consent.checkbox_label")}
          </span>
        </label>

        <button
          type="button"
          className="btn-consent"
          disabled={!agreed}
          onClick={handleConsent}
        >
          {t("consent.button")}
        </button>
      </div>
    </div>
  );
}
