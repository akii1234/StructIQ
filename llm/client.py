"""Unified LLM client supporting OpenAI, Anthropic, Groq, and Ollama."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


_PROVIDER_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "openai":    ("gpt-4.1-mini",              None),
    "anthropic": ("claude-haiku-4-5-20251001",  None),
    "groq":      ("llama-3.1-8b-instant",       "https://api.groq.com/openai/v1"),
    "ollama":    ("llama3.2",                   "http://localhost:11434/v1"),
}


class LLMClient:
    """Unified LLM client. All providers expose the same generate_json interface."""

    def __init__(
        self,
        provider: str = "openai",
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider.lower().strip()
        if self.provider not in _PROVIDER_DEFAULTS:
            raise ValueError(
                f"Unsupported provider '{self.provider}'. "
                f"Choose from: {', '.join(_PROVIDER_DEFAULTS)}"
            )
        default_model, base_url = _PROVIDER_DEFAULTS[self.provider]
        self.model = model or default_model

        if self.provider == "anthropic":
            import anthropic as _anthropic
            resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not resolved_key:
                raise ValueError("API key required for Anthropic — set ANTHROPIC_API_KEY or pass api_key.")
            self._anthropic_client = _anthropic.Anthropic(api_key=resolved_key)
            self._openai_client = None
        else:
            from openai import OpenAI
            if self.provider == "ollama":
                resolved_key = api_key or "ollama"
            elif self.provider == "groq":
                resolved_key = api_key or os.getenv("GROQ_API_KEY")
                if not resolved_key:
                    raise ValueError("API key required for Groq — set GROQ_API_KEY or pass api_key.")
            else:
                resolved_key = api_key or os.getenv("OPENAI_API_KEY")
                if not resolved_key:
                    raise ValueError("OPENAI_API_KEY is not set.")
            kwargs: dict[str, Any] = {"api_key": resolved_key, "timeout": 60}
            if base_url:
                kwargs["base_url"] = base_url
            self._openai_client = OpenAI(**kwargs)
            self._anthropic_client = None

    def generate_json(self, prompt: str, content: str) -> Dict[str, Any]:
        """Generate structured JSON output. All errors are raised as ValueError."""
        try:
            if self.provider == "anthropic":
                return self._call_anthropic(prompt, content)
            return self._call_openai_compat(prompt, content)
        except (ValueError, json.JSONDecodeError):
            raise
        except Exception as exc:
            raise ValueError(f"LLM error ({self.provider}/{self.model}): {exc}") from exc

    def _call_openai_compat(self, prompt: str, content: str) -> Dict[str, Any]:
        assert self._openai_client is not None
        response = self._openai_client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise code analysis assistant. Always return valid JSON.",
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nCode:\n{content}",
                },
            ],
            temperature=0,
        )
        payload = response.choices[0].message.content or "{}"
        return json.loads(payload)

    def _call_anthropic(self, prompt: str, content: str) -> Dict[str, Any]:
        assert self._anthropic_client is not None
        response = self._anthropic_client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=(
                "You are a precise code analysis assistant. "
                "Return only valid JSON with no markdown, no code fences, no other text."
            ),
            messages=[
                {"role": "user", "content": f"{prompt}\n\nCode:\n{content}"},
            ],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )
        return json.loads(text)


# Backwards compatibility — existing code that imports OpenAIClient continues to work
OpenAIClient = LLMClient
