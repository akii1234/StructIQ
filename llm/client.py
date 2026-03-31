"""OpenAI client wrapper for JSON-based summarization."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from openai import OpenAI


class OpenAIClient:
    """Thin wrapper around the OpenAI Chat Completions API."""

    def __init__(self, model: str = "gpt-4.1-mini", api_key: str | None = None) -> None:
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self.client = OpenAI(api_key=resolved_key, timeout=60)
        self.model = model

    def generate_json(self, prompt: str, content: str) -> Dict[str, Any]:
        """Generate structured JSON output using an LLM."""
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise code analysis assistant. "
                        "Always return valid JSON."
                    ),
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
