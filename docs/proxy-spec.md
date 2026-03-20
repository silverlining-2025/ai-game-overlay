# Managed Mode Proxy Specification

## Overview
Lightweight API proxy for managed-mode (Track 2) users. Validates license keys,
forwards AI vision requests using our pooled API keys, and enforces tier limits.

## Deployment
- Platform: Cloudflare Workers (free tier: 100K requests/day)
- URL: https://api.aigamingcompanion.com/v1/vision
- Auth: License key in X-License-Key header

## Endpoints

### POST /v1/vision
Proxies vision API calls to the cheapest available provider.

Request:
{headers}
X-License-Key: <lemon_squeezy_license_key>
Content-Type: application/json

{body}
{
  "image_b64": "<base64 jpeg>",
  "prompt": "<text prompt>",
  "system_prompt": "<system prompt>",
  "max_tokens": 80,
  "temperature": 0.7,
  "stream": true,
  "quality": "standard|smart|premium"
}

Response (streaming): SSE with text chunks
Response (non-streaming): JSON { "text": "...", "tokens": {...}, "provider": "gemini" }

### GET /v1/usage
Returns daily usage for the license key.

### POST /v1/validate
Validates a license key against Lemon Squeezy API.

## Routing Logic
- quality=standard: Gemini Flash-Lite only
- quality=smart: Gemini for normal, Claude for score>=0.7
- quality=premium: Claude first, Gemini fallback

## Rate Limits (per license key)
- Basic: 50 RPD, 5 RPM
- Pro: unlimited RPD, 15 RPM
- Streamer: unlimited RPD, 30 RPM

## Security
- License key validated against Lemon Squeezy API (cached 1hr)
- API keys stored in Cloudflare Worker secrets (never exposed to client)
- Request size limit: 2MB (covers a 1080p JPEG)
- IP rate limiting: 60 RPM per IP (DDoS protection)

## Cost Model
- Cloudflare Workers free tier: 100K requests/day
- At 50 managed users x 120 calls/hr x 2hr/day = 12,000 requests/day (well within free)
- At 500 users: 120,000/day -> $5/mo Cloudflare paid plan
- API cost: proxied through our Gemini keys -> ~$0.10/user/mo
