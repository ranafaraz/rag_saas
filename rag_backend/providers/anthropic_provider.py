"""Anthropic Claude provider (BYOK)."""
from typing import Generator

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 512):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self.api_key = api_key

    def _client(self):
        from anthropic import Anthropic
        return Anthropic(api_key=self.api_key)

    def generate(self, prompt: str) -> str:
        resp = self._client().messages.create(
            model=self.model,
            system=self.SYSTEM_HINT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return ("".join(parts)).strip()

    def stream(self, prompt: str) -> Generator[str, None, None]:
        with self._client().messages.stream(
            model=self.model,
            system=self.SYSTEM_HINT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
