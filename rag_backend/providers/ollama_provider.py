"""Self-hosted Ollama provider (CPU-friendly fallback, fully private)."""
from typing import Generator

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, *, base_url: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 512):
        super().__init__(model=model, temperature=temperature, max_tokens=max_tokens)
        self.base_url = base_url

    def _llm(self):
        from langchain_community.llms import Ollama
        return Ollama(
            base_url=self.base_url,
            model=self.model,
            temperature=self.temperature,
            num_predict=self.max_tokens,
        )

    def generate(self, prompt: str) -> str:
        return self._llm().invoke(prompt).strip()

    def stream(self, prompt: str) -> Generator[str, None, None]:
        for chunk in self._llm().stream(prompt):
            if chunk:
                yield chunk
