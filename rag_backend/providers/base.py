"""Provider interface. Implementations turn a fully-built prompt into text."""
from abc import ABC, abstractmethod
from typing import Generator


class LLMProvider(ABC):
    """A grounded-generation backend. Receives the complete prompt string
    (system rules + tenant base prompt + context + question already assembled by
    services.llm) and returns the model's answer."""

    #: Short system instruction reinforcing grounded behaviour for chat-style APIs.
    SYSTEM_HINT = "Follow the user prompt exactly and answer only from the provided context."

    def __init__(self, *, model: str, temperature: float = 0.0, max_tokens: int = 512):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Return the full answer for the prompt."""

    @abstractmethod
    def stream(self, prompt: str) -> Generator[str, None, None]:
        """Yield answer tokens as they are produced."""
