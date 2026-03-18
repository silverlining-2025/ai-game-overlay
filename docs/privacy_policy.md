# 개인정보 처리방침 / Privacy Policy

**최종 수정일 / Last Updated**: 2026-03-19

---

## 한국어

### 1. 수집하는 정보

AI Gaming Companion은 다음 정보를 수집합니다:

| 항목 | 설명 | 저장 위치 |
|------|------|-----------|
| 화면 캡처 이미지 | 게임 화면을 DXGI Desktop Duplication API로 캡처합니다. | 메모리 (임시) |
| API 키 | Anthropic API 키를 사용자가 직접 입력합니다. | 로컬 저장소 (localStorage) |
| 사용 통계 | 세션 길이, 사용 빈도 등 기본 사용 통계를 기록합니다. | 로컬 저장소 |
| 사용자 설정 | 캐릭터 선택, 위치 설정, 언어 설정 등을 저장합니다. | 로컬 저장소 |

### 2. 정보 이용 목적

수집된 정보는 다음 목적으로만 사용됩니다:

- **AI 게임 반응 생성**: 화면 캡처 이미지를 AI 모델에 전달하여 게임 상황에 맞는 코멘트, 조언, 반응을 생성합니다.
- **서비스 개선**: 사용 통계를 바탕으로 기능 개선 및 성능 최적화를 수행합니다.
- **사용자 경험 유지**: 설정값을 저장하여 재실행 시 동일한 환경을 제공합니다.

### 3. 제3자 제공

| 제공받는 자 | 제공 항목 | 제공 목적 | 보유 기간 |
|-------------|-----------|-----------|-----------|
| Anthropic, Inc. (미국) | 화면 캡처 이미지 | AI 이미지 분석 및 응답 생성 | 요청 처리 후 즉시 삭제 (Anthropic API 정책에 따름) |

- 이미지는 HTTPS를 통해 암호화 전송됩니다.
- Anthropic은 API 요청 데이터를 모델 학습에 사용하지 않습니다 (API Terms of Service 기준).
- 로컬 VLM (Moondream2) 사용 시 데이터가 외부로 전송되지 않습니다.

### 4. 보유 기간

- **화면 캡처 이미지**: 세션 종료 시 메모리에서 즉시 삭제됩니다. 디스크에 저장하지 않습니다.
- **API 키**: 사용자가 삭제하거나 브라우저 데이터를 초기화할 때까지 로컬 저장소에 보관됩니다.
- **사용 통계**: 로컬에만 보관되며, 앱 데이터 삭제 시 함께 삭제됩니다.
- **학습 데이터 옵트인**: 사용자가 학습 데이터 제공에 동의한 경우, 스크린샷과 AI 응답이 로컬 디스크에 보관됩니다. 동의 철회 시 즉시 삭제됩니다.

### 5. 이용자 권리

이용자는 다음 권리를 행사할 수 있습니다:

- **데이터 삭제 요청**: 앱 설정에서 모든 로컬 데이터를 삭제할 수 있습니다.
- **동의 철회**: 개인정보 수집 동의를 언제든지 철회할 수 있으며, 철회 시 앱 사용이 중단됩니다.
- **학습 데이터 옵트아웃**: 학습 데이터 제공 동의를 별도로 철회할 수 있습니다.
- **API 키 삭제**: 저장된 API 키를 언제든지 삭제하거나 변경할 수 있습니다.

### 6. 안전성 확보 조치

- **HTTPS 전송**: 모든 외부 API 통신은 TLS 암호화를 사용합니다.
- **로컬 저장**: 민감한 데이터는 사용자의 로컬 기기에만 저장됩니다.
- **게임 메모리 미접근**: 게임 프로세스 메모리를 읽거나 수정하지 않습니다. DLL 인젝션이나 DirectX/Vulkan 후킹을 수행하지 않습니다.
- **OS 수준 화면 캡처**: DXGI Desktop Duplication API만 사용하며, 이는 운영체제에서 제공하는 표준 화면 캡처 방식입니다.
- **독립 프로세스**: 오버레이는 게임과 완전히 분리된 별도 창으로 동작합니다.

### 7. 문의

본 개인정보 처리방침에 대한 문의사항은 프로젝트 GitHub 저장소의 Issues를 통해 접수해 주세요.

---

## English

### 1. Information We Collect

AI Gaming Companion collects the following information:

| Data | Description | Storage |
|------|-------------|---------|
| Screen capture images | Game screen captured via DXGI Desktop Duplication API. | Memory (temporary) |
| API key | Anthropic API key entered by the user. | Local storage (localStorage) |
| Usage statistics | Basic usage statistics such as session length and usage frequency. | Local storage |
| User preferences | Character selection, position settings, language settings, etc. | Local storage |

### 2. Purpose of Use

Collected information is used solely for the following purposes:

- **AI game response generation**: Screen capture images are sent to AI models to generate contextual comments, advice, and reactions for gameplay.
- **Service improvement**: Usage statistics inform feature improvements and performance optimization.
- **User experience continuity**: Settings are persisted to provide the same environment upon relaunch.

### 3. Third-Party Sharing

| Recipient | Data Shared | Purpose | Retention |
|-----------|-------------|---------|-----------|
| Anthropic, Inc. (United States) | Screen capture images | AI image analysis and response generation | Deleted immediately after request processing (per Anthropic API policy) |

- Images are transmitted via HTTPS with TLS encryption.
- Anthropic does not use API request data for model training (per API Terms of Service).
- When using a local VLM (Moondream2), no data is transmitted externally.

### 4. Data Retention

- **Screen capture images**: Immediately deleted from memory upon session end. Never written to disk.
- **API key**: Retained in local storage until the user deletes it or clears browser data.
- **Usage statistics**: Stored locally only; deleted when app data is cleared.
- **Training data opt-in**: If the user consents to providing training data, screenshots and AI responses are stored on local disk. Deleted immediately upon consent withdrawal.

### 5. Your Rights

You may exercise the following rights at any time:

- **Data deletion**: Delete all local data from the app settings.
- **Withdraw consent**: Withdraw your consent to data collection at any time. The app will cease to function upon withdrawal.
- **Training data opt-out**: Separately withdraw consent for training data collection.
- **API key removal**: Delete or change your stored API key at any time.

Under the GDPR (if applicable), you additionally have the right to:

- **Access**: Request a copy of the personal data we hold about you.
- **Rectification**: Request correction of inaccurate personal data.
- **Portability**: Receive your data in a structured, commonly used format.
- **Restriction of processing**: Request limitation of how your data is processed.
- **Object to processing**: Object to the processing of your personal data.

As all persistent data is stored locally on your device, you have full and immediate control over your data at all times. No account or server-side data exists.

### 6. Security Measures

- **HTTPS transmission**: All external API communication uses TLS encryption.
- **Local storage**: Sensitive data is stored only on the user's local device.
- **No game memory access**: The application does not read or modify game process memory. No DLL injection or DirectX/Vulkan hooking is performed.
- **OS-level screen capture**: Only DXGI Desktop Duplication API is used, which is a standard operating system screen capture method.
- **Independent process**: The overlay operates as a completely separate window, isolated from the game process.

### 7. Legal Basis for Processing (GDPR)

Where GDPR applies, we process personal data on the following legal bases:

- **Consent** (Article 6(1)(a)): Explicit consent is obtained before any data collection begins.
- **Legitimate interest** (Article 6(1)(f)): Usage statistics for service improvement, balanced against minimal privacy impact due to local-only storage.

### 8. International Data Transfers

When using the Anthropic API, screen capture images may be transferred to servers in the United States. This transfer is necessary for the performance of the service you have consented to use. Anthropic maintains appropriate safeguards for data protection.

### 9. Contact

For inquiries regarding this privacy policy, please submit an issue on the project's GitHub repository.
