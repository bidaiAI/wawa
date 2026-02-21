"""
API Key Manager — Encrypted storage for LLM provider API keys.

Keys are encrypted at rest using Fernet symmetric encryption.
The encryption key is derived from PLATFORM_AUTH_SECRET via HMAC-SHA256.

Fallback: if encrypted storage doesn't exist, reads from environment variables
(migration path from manual .env to managed keys).
"""

import os
import json
import time
import hmac
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mortal.platform.key_manager")

# Supported LLM providers
PROVIDERS = ("gemini", "deepseek", "openrouter")

# Env var names for each provider (fallback source)
PROVIDER_ENV_VARS = {
    "gemini": "PLATFORM_GEMINI_API_KEY",
    "deepseek": "PLATFORM_DEEPSEEK_API_KEY",
    "openrouter": "PLATFORM_OPENROUTER_API_KEY",
}


class KeyManager:
    """Manages LLM API keys with encrypted file storage."""

    def __init__(self, data_dir: Path, auth_secret: str = ""):
        self.data_dir = data_dir
        self.keys_file = data_dir / "platform" / "api_keys.json"
        self._auth_secret = auth_secret or os.getenv(
            "PLATFORM_AUTH_SECRET", "mortal-platform-secret-change-me"
        )
        self._fernet = None
        self._keys: dict[str, dict] = {}  # provider -> {key, rotated_at}
        self._init_encryption()
        self._load()

    def _init_encryption(self):
        """Initialize Fernet encryption from auth secret."""
        try:
            from cryptography.fernet import Fernet
            import base64

            # Derive a 32-byte key from the auth secret
            derived = hmac.new(
                self._auth_secret.encode(),
                b"api-key-encryption",
                hashlib.sha256,
            ).digest()
            fernet_key = base64.urlsafe_b64encode(derived)
            self._fernet = Fernet(fernet_key)
        except ImportError:
            logger.warning(
                "cryptography package not installed — API keys stored in plaintext. "
                "Install with: pip install cryptography"
            )
            self._fernet = None

    def _load(self):
        """Load keys from encrypted file, falling back to env vars."""
        if self.keys_file.exists():
            try:
                raw = json.loads(self.keys_file.read_text(encoding="utf-8"))
                for provider, data in raw.items():
                    encrypted_key = data.get("key", "")
                    if encrypted_key and self._fernet:
                        try:
                            decrypted = self._fernet.decrypt(
                                encrypted_key.encode()
                            ).decode()
                            self._keys[provider] = {
                                "key": decrypted,
                                "rotated_at": data.get("rotated_at", 0),
                            }
                        except Exception:
                            logger.warning(f"Failed to decrypt key for {provider}")
                    elif encrypted_key:
                        # No encryption available, assume plaintext
                        self._keys[provider] = {
                            "key": encrypted_key,
                            "rotated_at": data.get("rotated_at", 0),
                        }
                logger.info(f"Loaded {len(self._keys)} API keys from encrypted storage")
                return
            except Exception as e:
                logger.warning(f"Failed to load keys file: {e}")

        # Fallback: migrate from environment variables
        migrated = 0
        for provider in PROVIDERS:
            env_var = PROVIDER_ENV_VARS[provider]
            key = os.getenv(env_var, "")
            if key:
                self._keys[provider] = {"key": key, "rotated_at": time.time()}
                migrated += 1
        if migrated:
            logger.info(f"Migrated {migrated} API keys from environment variables")
            self._save()

    def _save(self):
        """Save keys to encrypted file."""
        self.keys_file.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for provider, info in self._keys.items():
            if self._fernet:
                encrypted = self._fernet.encrypt(info["key"].encode()).decode()
            else:
                encrypted = info["key"]  # Plaintext fallback
            data[provider] = {
                "key": encrypted,
                "rotated_at": info.get("rotated_at", 0),
            }
        self.keys_file.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        logger.info(f"Saved {len(data)} API keys to encrypted storage")

    def get_key(self, provider: str) -> str:
        """Get decrypted API key for a provider."""
        info = self._keys.get(provider)
        if info:
            return info["key"]
        # Final fallback: env var
        env_var = PROVIDER_ENV_VARS.get(provider, "")
        return os.getenv(env_var, "") if env_var else ""

    def set_key(self, provider: str, key: str):
        """Set or update an API key."""
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        self._keys[provider] = {"key": key, "rotated_at": time.time()}
        self._save()
        # Also update os.environ for current process
        env_var = PROVIDER_ENV_VARS.get(provider, "")
        if env_var:
            os.environ[env_var] = key
        logger.info(f"API key set for {provider}")

    def remove_key(self, provider: str):
        """Remove an API key."""
        if provider in self._keys:
            del self._keys[provider]
            self._save()
        env_var = PROVIDER_ENV_VARS.get(provider, "")
        if env_var and env_var in os.environ:
            os.environ[env_var] = ""
        logger.info(f"API key removed for {provider}")

    def get_masked_keys(self) -> list[dict]:
        """Return masked key info for UI display. NEVER returns full key."""
        result = []
        for provider in PROVIDERS:
            info = self._keys.get(provider)
            if info and info["key"]:
                key = info["key"]
                masked = key[:4] + "..." + key[-3:] if len(key) > 7 else "***"
                result.append({
                    "provider": provider,
                    "key_masked": masked,
                    "key_set": True,
                    "key_length": len(key),
                    "rotated_at": info.get("rotated_at", 0),
                })
            else:
                result.append({
                    "provider": provider,
                    "key_masked": "",
                    "key_set": False,
                    "key_length": 0,
                    "rotated_at": 0,
                })
        return result

    def get_all_keys(self) -> dict[str, str]:
        """Return all keys as {provider: key} — internal use only."""
        return {p: self.get_key(p) for p in PROVIDERS}

    def get_status(self) -> dict:
        """Status for dashboard."""
        return {
            "providers_configured": sum(
                1 for p in PROVIDERS if self.get_key(p)
            ),
            "providers_total": len(PROVIDERS),
            "encryption_enabled": self._fernet is not None,
            "storage_file": str(self.keys_file),
        }
