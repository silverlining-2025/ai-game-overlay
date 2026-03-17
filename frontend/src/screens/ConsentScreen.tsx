import { useState } from "react";
import "./ConsentScreen.css";

interface Props {
  onConsent: () => void;
}

export default function ConsentScreen({ onConsent }: Props) {
  const [agreed, setAgreed] = useState(false);

  const handleConsent = () => {
    localStorage.setItem("privacy_consent", "true");
    onConsent();
  };

  return (
    <div className="consent-root">
      <div className="consent-card">
        <h1 className="consent-title">개인정보 처리 안내</h1>
        <p className="consent-subtitle">
          AI Gaming Companion을 사용하기 전에 아래 내용을 확인해주세요.
        </p>

        <div className="consent-section">
          <div className="consent-section-title">수집 및 처리 항목</div>
          <div className="consent-items">
            <div className="consent-item">
              <span className="consent-item-icon">🖥️</span>
              <div className="consent-item-text">
                <div className="consent-item-label">화면 캡처</div>
                <div className="consent-item-desc">
                  게임 화면을 캡처하여 AI에게 전송합니다
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">🌐</span>
              <div className="consent-item-text">
                <div className="consent-item-label">데이터 전송</div>
                <div className="consent-item-desc">
                  캡처된 이미지는 Anthropic API(미국)로 전송되어 분석됩니다
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">🗑️</span>
              <div className="consent-item-text">
                <div className="consent-item-label">데이터 저장</div>
                <div className="consent-item-desc">
                  이미지는 서버에 저장되지 않습니다 (분석 후 즉시 삭제)
                </div>
              </div>
            </div>

            <div className="consent-item">
              <span className="consent-item-icon">💾</span>
              <div className="consent-item-text">
                <div className="consent-item-label">학습 데이터</div>
                <div className="consent-item-desc">
                  --save-training 옵션 사용 시 로컬에 저장될 수 있습니다
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="consent-safe">
          <span className="consent-safe-icon">🛡️</span>
          <span>
            안티치트 안전: 게임 메모리를 읽거나 수정하지 않습니다.
            OS 수준의 화면 캡처만 사용합니다.
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
            위 내용을 확인했으며, 데이터 처리에 동의합니다
          </span>
        </label>

        <button
          type="button"
          className="btn-consent"
          disabled={!agreed}
          onClick={handleConsent}
        >
          동의하고 시작
        </button>
      </div>
    </div>
  );
}
