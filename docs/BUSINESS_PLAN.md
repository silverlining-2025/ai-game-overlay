# AI Gaming Companion — Business Plan

## 혼겜의 새로운 동반자 (Your New Companion for Solo Gaming)

A native desktop overlay AI companion that watches your game and reacts like a friend, not a coach.

---

## Executive Summary

- **Market**: $14.6B Korean gaming market, 52% of gamers pay ($450/yr per capita)
- **Product**: Native Tauri overlay with anime character companions reacting to gameplay
- **Differentiator**: Companion not coach, Korean-first, native overlay (not webpage), deep personality
- **Model**: Freemium + subscription + character marketplace
- **Target**: Break-even at 2,000 paying users (~25.8M KRW/mo)

## Pricing

| Tier | Price | Features | API Cost/User |
|------|-------|----------|---------------|
| Free | 0 | 1 character, 15 reactions/day, 1 game | ~$0.45/mo |
| Standard | 9,900 KRW/mo | 3 characters, 150 reactions/day, all games, memory | ~$2/mo |
| Premium | 19,900 KRW/mo | All characters, unlimited, custom personality, voice | ~$4/mo |
| Character packs | 3,900 KRW each | Individual characters, seasonal skins | 0 |

## Go-to-Market

| Phase | Timeline | Goal | Key Metric |
|-------|----------|------|------------|
| Closed Beta | Month 1-3 | 200-500 users, Palworld only | Day-7 retention > 25% |
| Public Launch | Month 4-6 | 5,000 users, billing live | Free→paid conversion > 5% |
| Growth | Month 7-12 | 20,000 users, 5+ games | MRR > 20M KRW |
| Scale | Month 13-18 | 50,000 users, English/JP | LTV:CAC > 3:1 |

## Target Customer

**혼겜러 (Solo Gamer), Age 20-30**
- Plays Palworld/Genshin/survival games solo
- Watches VTubers or anime content
- Active on DC Inside, Inven, Discord
- Spends 10K-50K KRW/month on gaming
- Wants company while gaming, not voice chat with strangers

## Marketing Messages

- Primary: **"게임할 때 옆에서 떠드는 AI 친구"**
- Safety: **"화면만 보고 반응 — 게임 데이터 접근 없음"**
- Personality: **"츤데레부터 고양이까지, 취향대로 골라"**

## Legal Requirements (Pre-Launch)

1. 사업자등록 (business registration)
2. Korean privacy policy (개인정보 처리방침) — screen capture + Anthropic cross-border
3. Explicit user consent flow before first screen capture
4. AI output labeling (AI Basic Act, effective Jan 2026)
5. EV code signing certificate (~$300-600/yr)

## Payment Stack

**PortOne + Toss Payments** → Kakao Pay, Naver Pay, Toss, cards, bank transfer

## Technical Architecture (Production)

```
[Screen Capture] → [Local CV] → [API Proxy (your server)]
                                        ↓
                   [User Auth] → [Session Manager] → [Claude API]
                                        ↓
                   [Analytics] → [Usage Tracking] → [Billing]
                                        ↓
                                [Local Overlay via SSE]
```

## Competitive Moat

1. Korean-first (no competitor)
2. Native overlay (Questie is webpage)
3. Character IP (fan community, merch potential)
4. Companion memory (switching costs)
5. User feedback flywheel (thumbs up/down → better model)

## Funding Options

- KOCCA game production fund (23.6B KRW, "AI games" category)
- TIPS program (up to 800M KRW R&D grants)
- SparkLabs accelerator (up to $100K for 6%)
- Google for Startups AI First Korea
- Bootstrappable to profitability at 2,000 paying users

## Unit Economics (at 10,000 paying users)

- Revenue: ~129M KRW/mo (~$97K)
- API costs: ~$26K/mo
- Gross margin: ~73%
- Infrastructure: ~$500/mo
- Net: Profitable with 1 engineer + 1 artist
