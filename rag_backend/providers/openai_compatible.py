"""OpenAI-compatible chat provider.

Covers Groq, OpenAI, DeepSeek, vLLM and any custom OpenAI-compatible endpoint —
they differ only by base_url / model / api_key.
"""
from typing import Generator

from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, base_url: str, api_key: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 512):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self.base_url = base_url
        self.api_key = api_key or "not-needed"

    def _client(self):
        from openai import OpenAI
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _messages(self, prompt: str):
        return [
            {"role": "system", "content": self.SYSTEM_HINT},
            {"role": "user", "content": prompt},
        ]

    def generate(self, prompt: str) -> str:
        resp = self._client().chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=self._messages(prompt),
        )
        return (resp.choices[0].message.content or "").strip()

    def stream(self, prompt: str) -> Generator[str, None, None]:
        stream = self._client().chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
            messages=self._messages(prompt),
        )
        for event in stream:
            token = event.choices[0].delta.content or ""
            if token:
                yield token
