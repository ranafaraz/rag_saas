import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", 6333))
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    MONGO_HOST: str = os.getenv("MONGO_HOST", "localhost")
    MONGO_PORT: int = int(os.getenv("MONGO_PORT", 27017))
    MONGO_USER: str = os.getenv("MONGO_USER", "admin")
    MONGO_PASSWORD: str = os.getenv("MONGO_PASSWORD", "admin123")
    MONGO_DB: str = os.getenv("MONGO_DB", "rag_audit_log")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", 512))
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
    VLLM_MODEL: str = os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B")
    VLLM_API_KEY: str = os.getenv("VLLM_API_KEY", "local-vllm")
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "ollama")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "768"))

    EMBEDDING_CACHE_TTL_SECONDS: int = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", 1800))
    RESPONSE_CACHE_TTL_SECONDS: int = int(os.getenv("RESPONSE_CACHE_TTL_SECONDS", 900))

    CORE_API_URL: str = os.getenv("CORE_API_URL", "http://localhost:8000")

    class Config:
        case_sensitive = True

settings = Settings()
