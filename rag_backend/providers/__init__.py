"""Pluggable LLM provider registry for the RAG backend.

Default free tier is Groq (powerful hosted models, no local GPU). Tenants may
bring their own key for OpenAI / Anthropic / DeepSeek, or self-host via Ollama /
vLLM. New open-source providers slot in by adding a module + registry entry.
"""
from .registry import get_provider, resolve_config

__all__ = ["get_provider", "resolve_config"]
