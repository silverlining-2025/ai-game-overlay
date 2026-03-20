"""Multi-API provider abstraction for vision-based AI companion.

Supports multiple AI backends with automatic fallback:
  1. Gemini Flash-Lite (cheapest, 1000 free/day)
  2. GPT-4o-mini (cheap, fast)
  3. Claude Haiku (current, higher quality)
  4. Local VLM fallback (offline, no cost)

Usage:
    provider = create_provider_chain(api_keys, locale="ko")
    response = provider.query(image_b64, prompt, system_prompt, max_tokens=80)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator

log = logging.getLogger(__name__)


@dataclass
class AIResponse:
    """Standardized response from any AI provider."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    provider: str = ""
    model: str = ""
    elapsed_ms: float = 0.0
    error: str | None = None


class AIProvider(ABC):
    """Base class for AI vision providers."""

    name: str = "base"
    model: str = ""

    # Cost per 1M tokens (for cost tracking)
    input_cost_per_1m: float = 0.0
    output_cost_per_1m: float = 0.0

    @abstractmethod
    def query(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 80,
        temperature: float = 0.7,
    ) -> AIResponse:
        """Send an image + prompt and get a response."""

    @abstractmethod
    def stream(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 80,
        temperature: float = 0.7,
    ) -> Generator[str, None, AIResponse]:
        """Stream response chunks, yield text, return final AIResponse."""

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_cost_per_1m + output_tokens * self.output_cost_per_1m) / 1_000_000

    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        return True


class ClaudeProvider(AIProvider):
    """Anthropic Claude Haiku/Sonnet via the anthropic SDK."""

    name = "claude"
    model = "claude-haiku-4-5-20251001"
    input_cost_per_1m = 1.0
    output_cost_per_1m = 5.0

    def __init__(self, api_key: str, model: str | None = None):
        import httpx
        import anthropic
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=httpx.Timeout(30.0, connect=5.0),
            max_retries=2,
        )
        if model:
            self.model = model

    def query(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        t0 = time.perf_counter()
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": prompt},
        ]
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = response.content[0].text.strip()
        inp = response.usage.input_tokens
        out = response.usage.output_tokens
        return AIResponse(
            text=text, input_tokens=inp, output_tokens=out,
            cost_usd=self._calc_cost(inp, out),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def stream(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        t0 = time.perf_counter()
        user_content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": prompt},
        ]
        text = ""
        input_tokens = 0
        output_tokens = 0

        with self._client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            for event in stream:
                if hasattr(event, 'type'):
                    if event.type == 'content_block_delta' and hasattr(event, 'delta'):
                        chunk = getattr(event.delta, 'text', '')
                        if chunk:
                            text += chunk
                            yield chunk
                    elif event.type == 'message_start' and hasattr(event, 'message'):
                        usage = getattr(event.message, 'usage', None)
                        if usage:
                            input_tokens = getattr(usage, 'input_tokens', 0)
                    elif event.type == 'message_delta':
                        usage = getattr(event, 'usage', None)
                        if usage:
                            output_tokens = getattr(usage, 'output_tokens', 0)

        return AIResponse(
            text=text.strip(), input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=self._calc_cost(input_tokens, output_tokens),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def is_available(self):
        return bool(self._client.api_key)


class GeminiProvider(AIProvider):
    """Google Gemini Flash/Flash-Lite via google-genai SDK."""

    name = "gemini"
    model = "gemini-2.5-flash-lite-preview-06-17"
    input_cost_per_1m = 0.10
    output_cost_per_1m = 0.40

    def __init__(self, api_key: str, model: str | None = None):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        if model:
            self.model = model

    def query(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        import base64
        from google.genai import types

        t0 = time.perf_counter()
        image_bytes = base64.b64decode(image_b64)

        response = self._client.models.generate_content(
            model=self.model,
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes)),
                    types.Part(text=prompt),
                ]),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )

        text = response.text.strip() if response.text else ""
        # Gemini usage metadata
        inp = getattr(response.usage_metadata, 'prompt_token_count', 0) if response.usage_metadata else 0
        out = getattr(response.usage_metadata, 'candidates_token_count', 0) if response.usage_metadata else 0

        return AIResponse(
            text=text, input_tokens=inp, output_tokens=out,
            cost_usd=self._calc_cost(inp, out),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def stream(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        import base64
        from google.genai import types

        t0 = time.perf_counter()
        image_bytes = base64.b64decode(image_b64)
        text = ""
        input_tokens = 0
        output_tokens = 0

        for chunk in self._client.models.generate_content_stream(
            model=self.model,
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=image_bytes)),
                    types.Part(text=prompt),
                ]),
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        ):
            if chunk.text:
                text += chunk.text
                yield chunk.text
            if chunk.usage_metadata:
                input_tokens = getattr(chunk.usage_metadata, 'prompt_token_count', input_tokens)
                output_tokens = getattr(chunk.usage_metadata, 'candidates_token_count', output_tokens)

        return AIResponse(
            text=text.strip(), input_tokens=input_tokens, output_tokens=output_tokens,
            cost_usd=self._calc_cost(input_tokens, output_tokens),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )


class OpenAICompatProvider(AIProvider):
    """OpenAI-compatible API (GPT-4o-mini, Groq, Together, OpenRouter)."""

    name = "openai"
    model = "gpt-4o-mini"
    input_cost_per_1m = 0.15
    output_cost_per_1m = 0.60

    def __init__(self, api_key: str, model: str | None = None,
                 base_url: str | None = None, name: str | None = None):
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        if model:
            self.model = model
        if name:
            self.name = name

    def query(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        t0 = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ]},
            ],
        )
        text = response.choices[0].message.content.strip() if response.choices else ""
        inp = response.usage.prompt_tokens if response.usage else 0
        out = response.usage.completion_tokens if response.usage else 0
        return AIResponse(
            text=text, input_tokens=inp, output_tokens=out,
            cost_usd=self._calc_cost(inp, out),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    def stream(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        t0 = time.perf_counter()
        text = ""

        response_stream = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ]},
            ],
        )

        for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                text += delta
                yield delta

        # Estimate tokens (OpenAI streaming doesn't always return usage)
        est_input = 3000  # ~image + prompt
        est_output = len(text) // 3
        return AIResponse(
            text=text.strip(), input_tokens=est_input, output_tokens=est_output,
            cost_usd=self._calc_cost(est_input, est_output),
            provider=self.name, model=self.model,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )


class ProviderChain:
    """Tries providers in order, falls back on failure."""

    def __init__(self, providers: list[AIProvider]):
        self.providers = providers
        self._current_idx = 0
        self._fail_counts: dict[str, int] = {}
        self._last_fail_time: dict[str, float] = {}
        # Back off failed providers for 60s
        self._backoff_sec = 60.0

    @property
    def current(self) -> AIProvider:
        return self.providers[self._current_idx]

    def _is_backed_off(self, provider: AIProvider) -> bool:
        name = provider.name
        if name in self._last_fail_time:
            elapsed = time.time() - self._last_fail_time[name]
            if elapsed < self._backoff_sec:
                return True
            # Backoff expired, reset
            self._fail_counts.pop(name, None)
            self._last_fail_time.pop(name, None)
        return False

    def _mark_failed(self, provider: AIProvider, error: str):
        name = provider.name
        self._fail_counts[name] = self._fail_counts.get(name, 0) + 1
        self._last_fail_time[name] = time.time()
        log.warning("Provider %s failed (%d): %s", name, self._fail_counts[name], error)

    def _mark_success(self, provider: AIProvider):
        self._fail_counts.pop(provider.name, None)
        self._last_fail_time.pop(provider.name, None)

    def query(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7) -> AIResponse:
        last_error = None
        for provider in self.providers:
            if self._is_backed_off(provider):
                continue
            try:
                result = provider.query(image_b64, prompt, system_prompt, max_tokens, temperature)
                self._mark_success(provider)
                return result
            except Exception as e:
                self._mark_failed(provider, str(e))
                last_error = e

        return AIResponse(text="", error=f"All providers failed: {last_error}", provider="none")

    def stream(self, image_b64, prompt, system_prompt, max_tokens=80, temperature=0.7):
        """Try providers in order. Returns (generator, provider_name) for the first that works."""
        for provider in self.providers:
            if self._is_backed_off(provider):
                continue
            try:
                gen = provider.stream(image_b64, prompt, system_prompt, max_tokens, temperature)
                return gen, provider
            except Exception as e:
                self._mark_failed(provider, str(e))

        # All failed — return empty generator
        def empty():
            yield ""
            return AIResponse(text="", error="All providers failed", provider="none")
        return empty(), None


def create_provider_chain(
    anthropic_key: str = "",
    gemini_key: str = "",
    openai_key: str = "",
    groq_key: str = "",
) -> ProviderChain:
    """Create a provider chain with available API keys.

    Priority order (cheapest first):
    1. Gemini Flash-Lite (free tier / $0.10/1M)
    2. Groq (free tier, fast)
    3. GPT-4o-mini ($0.15/1M)
    4. Claude Haiku ($1.00/1M)
    """
    providers: list[AIProvider] = []

    if gemini_key:
        try:
            providers.append(GeminiProvider(api_key=gemini_key))
            log.info("Gemini provider added (model: %s)", GeminiProvider.model)
        except Exception as e:
            log.warning("Gemini init failed: %s", e)

    if groq_key:
        try:
            providers.append(OpenAICompatProvider(
                api_key=groq_key,
                model="llama-3.2-11b-vision-preview",
                base_url="https://api.groq.com/openai/v1",
                name="groq",
            ))
            log.info("Groq provider added")
        except Exception as e:
            log.warning("Groq init failed: %s", e)

    if openai_key:
        try:
            providers.append(OpenAICompatProvider(api_key=openai_key))
            log.info("OpenAI provider added (model: gpt-4o-mini)")
        except Exception as e:
            log.warning("OpenAI init failed: %s", e)

    if anthropic_key:
        try:
            providers.append(ClaudeProvider(api_key=anthropic_key))
            log.info("Claude provider added (model: %s)", ClaudeProvider.model)
        except Exception as e:
            log.warning("Claude init failed: %s", e)

    if not providers:
        log.error("No AI providers configured! Add at least one API key.")

    return ProviderChain(providers)
