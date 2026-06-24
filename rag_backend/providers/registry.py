"""Resolve a generation config (env defaults + per-tenant overrides) into a provider.

Per-tenant override shape (sent by Core's verify endpoints from AIModelConfig):
    {"provider": "groq|openai|anthropic|deepseek|vllm|ollama|custom",
     "model": "...", "endpoint_url": "...", "api_key": "..."}
Any field may be omitted; omitted fields fall back to the provider preset / env.
"""
import os

from .base import LLMProvider
from .openai_compatible import OpenAICompatibleProvider
from .anthropic_provider import AnthropicProvider
from .ollama_provider import OllamaProvider

# Default provider for the free tier. Groq = powerful hosted models, no local GPU.
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
DEFAULT_MAX_TOKENS = int(os.getenv("OLLAMA_NUM_PREDICT", "512"))


def _preset(provider: str) -> dict:
    """Base config for a known provider, filled from env."""
    presets = {
        "groq": {
            "kind": "openai",
            "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "api_key": os.getenv("GROQ_API_KEY", ""),
        },
        "openai": {
            "kind": "openai",
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "api_key": os.getenv("OPENAI_API_KEY", ""),
        },
        "deepseek": {
            "kind": "openai",
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        },
        "anthropic": {
            "kind": "anthropic",
            "base_url": "",
            "model": os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        },
        "vllm": {
            "kind": "openai",
            "base_url": os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1"),
            "model": os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B"),
            "api_key": os.getenv("VLLM_API_KEY", "local-vllm"),
        },
        "ollama": {
            "kind": "ollama",
            "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            "api_key": "",
        },
        "custom": {
            "kind": "openai",
            "base_url": os.getenv("CUSTOM_LLM_BASE_URL", ""),
            "model": os.getenv("CUSTOM_LLM_MODEL", ""),
            "api_key": os.getenv("CUSTOM_LLM_API_KEY", ""),
        },
    }
    return dict(presets.get(provider, presets["ollama"]))


def resolve_config(llm_config: dict | None = None) -> dict:
    """Merge a per-tenant override over the provider preset and env defaults."""
    override = {k: v for k, v in (llm_config or {}).items() if v}
    provider = (override.get("provider") or DEFAULT_PROVIDER).lower()

    cfg = _preset(provider)
    if override.get("endpoint_url"):
        cfg["base_url"] = override["endpoint_url"]
    if override.get("model"):
        cfg["model"] = override["model"]
    if override.get("api_key"):
        cfg["api_key"] = override["api_key"]
    cfg["provider"] = provider
    cfg.setdefault("temperature", DEFAULT_TEMPERATURE)
    cfg.setdefault("max_tokens", DEFAULT_MAX_TOKENS)

    # Graceful degrade: a hosted provider with no key (no tenant BYOK, no env key)
    # falls back to the local Ollama model so dev/self-host works out of the box.
    hosted = {"groq", "openai", "deepseek", "anthropic"}
    if provider in hosted and not cfg["api_key"]:
        fallback = _preset("ollama")
        fallback.update({"provider": "ollama", "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"]})
        return fallback
    return cfg


def get_provider(llm_config: dict | None = None) -> LLMProvider:
    cfg = resolve_config(llm_config)
    kind = cfg.get("kind", "openai")
    common = {"model": cfg["model"], "temperature": cfg["temperature"], "max_tokens": cfg["max_tokens"]}

    if kind == "anthropic":
        return AnthropicProvider(api_key=cfg["api_key"], **common)
    if kind == "ollama":
        return OllamaProvider(base_url=cfg["base_url"], **common)
    return OpenAICompatibleProvider(base_url=cfg["base_url"], api_key=cfg["api_key"], **common)
