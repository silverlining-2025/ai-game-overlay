# API 키 설정 가이드 (API Key Setup Guide)

## Gemini API 키 (무료, 추천) — Gemini API Key (Free, Recommended)

Google Gemini API는 **무료**로 하루 1,000회까지 사용할 수 있습니다.
(Google Gemini API is **free** for up to 1,000 calls per day.)

### 1단계: Google AI Studio 접속 (Step 1: Visit Google AI Studio)

1. 브라우저에서 [aistudio.google.com/apikey](https://aistudio.google.com/apikey) 접속
   (Open [aistudio.google.com/apikey](https://aistudio.google.com/apikey) in your browser)

2. Google 계정으로 로그인 (Sign in with your Google account)
   - Gmail 계정이 있으면 그대로 사용 가능 (Use your existing Gmail account)
   - 없으면 무료로 생성 (Create one for free if needed)

### 2단계: API 키 생성 (Step 2: Create API Key)

1. "Create API Key" 또는 "API 키 만들기" 버튼 클릭
   (Click "Create API Key" button)

2. "Create API key in new project" 선택
   (Select "Create API key in new project")

3. 생성된 키가 화면에 표시됨 — `AIza...` 형식
   (The generated key appears on screen — starts with `AIza...`)

4. 키를 복사 (Copy the key)

### 3단계: 앱에 입력 (Step 3: Enter in App)

1. AI Gaming Companion 설정 화면에서 "직접 설정" 모드 선택
   (In the config screen, select "Self Setup" mode)

2. "Google Gemini API 키" 필드에 복사한 키 붙여넣기
   (Paste the copied key into the "Google Gemini API Key" field)

3. "시작하기" 클릭! (Click "Start"!)

### 무료 한도 (Free Tier Limits)

| 항목 (Item) | 한도 (Limit) |
|---|---|
| 일일 요청 (Daily requests) | 1,000회 (~8시간 게임 가능) |
| 분당 요청 (Requests per minute) | 15 |
| 비용 (Cost) | **무료 ($0)** |
| 신용카드 필요? (Credit card needed?) | **아니요 (No)** |

### 문제 해결 (Troubleshooting)

**Q: "API key not valid" 오류가 나요**
(Q: Getting "API key not valid" error)
- 키를 복사할 때 앞뒤 공백이 없는지 확인 (Check for extra spaces when copying)
- 키가 `AIza`로 시작하는지 확인 (Make sure key starts with `AIza`)
- 새 키를 다시 생성해보세요 (Try creating a new key)

**Q: "Quota exceeded" 오류가 나요**
(Q: Getting "Quota exceeded" error)
- 하루 1,000회 한도에 도달 — 내일 자동 리셋됨
  (Hit daily 1,000 call limit — resets automatically tomorrow)
- 프리미엄 구독으로 무제한 사용 가능
  (Upgrade to Premium for unlimited use)

**Q: 어떤 데이터가 Google에 전송되나요?**
(Q: What data is sent to Google?)
- 게임 화면 캡처 이미지 + 텍스트 프롬프트만 전송
  (Only game screenshot images + text prompts are sent)
- Google은 무료 API 사용 시 데이터를 모델 학습에 사용할 수 있음
  (Google may use free API data for model training)
- 개인정보(이름, 계정 등)는 전송되지 않음
  (No personal information like names or accounts is sent)

---

## Anthropic API 키 (선택사항) — Anthropic API Key (Optional)

Claude AI는 더 높은 품질의 분석을 제공하지만 **유료**입니다.
(Claude AI provides higher quality analysis but is **paid**.)

### 설정 방법 (Setup)

1. [console.anthropic.com](https://console.anthropic.com) 접속 후 가입
   (Visit [console.anthropic.com](https://console.anthropic.com) and sign up)

2. 결제 정보 등록 필요 (Payment info required — credit card)

3. Settings → API Keys → "Create Key" 클릭
   (Settings → API Keys → Click "Create Key")

4. 생성된 키 복사 (`sk-ant-...` 형식)
   (Copy the generated key — starts with `sk-ant-...`)

5. 앱의 "Anthropic API 키" 필드에 붙여넣기
   (Paste into the "Anthropic API Key" field in the app)

### 요금 (Pricing)

| 항목 | 비용 |
|---|---|
| 시간당 예상 비용 | ~$0.05 |
| 월간 예상 (주 15시간) | ~$3-4 |
| 최소 충전 | $5 |

> Gemini 키와 함께 사용하면 Gemini가 먼저 사용되어 비용이 크게 절감됩니다.
> (When used with Gemini, Gemini handles most calls — significantly reducing cost.)

---

## OpenAI API 키 (선택사항) — OpenAI API Key (Optional)

GPT-4o-mini는 Gemini와 비슷한 가격대의 대안입니다.
(GPT-4o-mini is an alternative at a similar price point to Gemini.)

### 설정 방법 (Setup)

1. [platform.openai.com/api-keys](https://platform.openai.com/api-keys) 접속
2. 가입 + 결제 정보 등록
3. "Create new secret key" 클릭
4. 키 복사 (`sk-...` 형식)
5. 앱의 "OpenAI API 키" 필드에 붙여넣기

---

## API 우선순위 (API Priority Order)

앱은 자동으로 가장 저렴한 API를 먼저 사용합니다:
(The app automatically uses the cheapest API first:)

```
1. Gemini Flash-Lite (무료/free) → 가장 먼저 사용
2. Groq (무료/free) → Gemini 한도 초과 시
3. GPT-4o-mini ($0.15/1M tokens) → 백업
4. Claude Haiku ($1.00/1M tokens) → 프리미엄 품질
```

Gemini 키만 있어도 충분합니다!
(A Gemini key alone is enough!)

---

## 보안 안내 (Security Notice)

- API 키는 **로컬 컴퓨터에만** 저장됩니다 (Keys are stored **locally only**)
- 우리 서버로 전송되지 않습니다 (Never sent to our servers)
- API 호출은 사용자의 컴퓨터에서 직접 발생합니다 (API calls go directly from your machine)
- 언제든지 키를 삭제/재생성할 수 있습니다 (You can delete/regenerate keys anytime)
