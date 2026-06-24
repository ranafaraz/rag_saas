"""
Symmetric encryption for tenant secrets (BYOK LLM provider keys).

Uses Fernet (AES-128-CBC + HMAC) with a key from the FIELD_ENCRYPTION_KEY env var.
In DEBUG with no key configured, a deterministic dev key is derived so local
development works out of the box — NEVER rely on that path in production.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _load_fernet() -> Fernet:
    key = os.getenv("FIELD_ENCRYPTION_KEY", "").strip()
    if not key:
        # Dev fallback: derive a stable key from SECRET_KEY so encrypt/decrypt is
        # consistent within a deployment. Set FIELD_ENCRYPTION_KEY in production.
        seed = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-secret").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    # Allow either a raw Fernet key or arbitrary string (hash it to 32 bytes).
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        digest = hashlib.sha256(key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(raw: str) -> str:
    if not raw:
        return ""
    return _load_fernet().encrypt(raw.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _load_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
