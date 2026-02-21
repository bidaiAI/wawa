"""
Wallet Signature Authentication — Creator Dashboard Access.

Verifies that the caller owns a specific Ethereum wallet by checking
a signed message. Uses EIP-191 personal_sign (simpler than EIP-712,
widely supported by MetaMask and all wallets).

Flow:
  1. Frontend: creator signs message "I am the creator of mortal AI. Timestamp: {ts}"
  2. Backend: recover signer address from signature
  3. Backend: verify signer == creator() on vault contract
  4. Backend: issue JWT (1 hour expiry)

No passwords. No usernames. Your wallet IS your identity.
"""

import time
import hmac
import json
import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger("mortal.platform.auth")

# JWT-like token using HMAC (no external dependency needed)
# For production: use python-jose or PyJWT
_SECRET_KEY = ""  # Set at startup from env


def set_secret_key(key: str):
    """Set the HMAC secret key for token signing."""
    global _SECRET_KEY
    _SECRET_KEY = key


@dataclass
class AuthToken:
    """Authenticated session token."""
    wallet: str         # Verified wallet address
    issued_at: float    # Unix timestamp
    expires_at: float   # Unix timestamp
    valid: bool = True


def verify_signature(message: str, signature: str) -> str | None:
    """
    Recover the signer address from an EIP-191 personal_sign signature.

    Args:
        message: The original message that was signed
        signature: The hex-encoded signature (0x-prefixed)

    Returns:
        The checksummed address of the signer, or None if invalid.
    """
    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account

        msg = encode_defunct(text=message)
        address = Account.recover_message(msg, signature=signature)
        return address
    except Exception as e:
        logger.warning(f"Signature verification failed: {e}")
        return None


def create_auth_message(timestamp: int | None = None) -> str:
    """Generate the message the creator must sign."""
    ts = timestamp or int(time.time())
    return f"I am the creator of mortal AI. Timestamp: {ts}"


def create_token(wallet: str, ttl_seconds: int = 3600) -> str:
    """
    Create an HMAC-signed auth token (JWT-like but simpler).

    Args:
        wallet: Verified wallet address
        ttl_seconds: Token lifetime (default 1 hour)

    Returns:
        Base64-encoded token string
    """
    import base64

    payload = {
        "wallet": wallet.lower(),
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_bytes = json.dumps(payload).encode()
    sig = hmac.new(_SECRET_KEY.encode(), payload_bytes, hashlib.sha256).hexdigest()

    token_data = json.dumps({"payload": payload, "sig": sig})
    return base64.b64encode(token_data.encode()).decode()


def verify_token(token: str) -> AuthToken | None:
    """
    Verify an auth token and return the authenticated session.

    Returns:
        AuthToken if valid, None if expired or tampered.
    """
    import base64

    try:
        token_data = json.loads(base64.b64decode(token))
        payload = token_data["payload"]
        sig = token_data["sig"]

        # Verify HMAC
        expected_sig = hmac.new(
            _SECRET_KEY.encode(),
            json.dumps(payload).encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("Token signature mismatch")
            return None

        # Check expiry
        if time.time() > payload["exp"]:
            logger.info(f"Token expired for {payload['wallet']}")
            return None

        return AuthToken(
            wallet=payload["wallet"],
            issued_at=payload["iat"],
            expires_at=payload["exp"],
        )

    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return None
