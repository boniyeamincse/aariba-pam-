"""Security utilities, token validation, and assurance enforcement."""

import hmac
import hashlib
import json
import base64
import time
from typing import Dict, Any, Optional
from ariba_pam.config import settings
from ariba_pam.core.errors import UnauthorizedException


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (4 - len(s) % 4) if len(s) % 4 != 0 else ""
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))


def create_session_token(
    user_id: str,
    email: str,
    assurance_level: str = "aal3",
    auth_methods: Optional[list] = None,
    expires_in_seconds: Optional[int] = None,
) -> str:
    """Create a signed session token including assurance claims."""
    if expires_in_seconds is None:
        expires_in_seconds = settings.session_lifetime_minutes * 60

    if auth_methods is None:
        auth_methods = ["pwd", "fido2"]

    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iss": settings.idp_issuer,
        "aud": settings.idp_audience,
        "iat": now,
        "exp": now + expires_in_seconds,
        "assurance_level": assurance_level,
        "amr": auth_methods,
    }

    header = {"alg": "HS256", "typ": "JWT"}
    header_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    unsigned_token = f"{_b64url_encode(header_json)}.{_b64url_encode(payload_json)}"
    signature = hmac.new(
        settings.secret_key.encode("utf-8"),
        unsigned_token.encode("ascii"),
        hashlib.sha256,
    ).digest()

    return f"{unsigned_token}.{_b64url_encode(signature)}"


def verify_session_token(token: str) -> Dict[str, Any]:
    """Verify session token signature, expiration, and assurance requirements."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise UnauthorizedException("Malformed session token", code="INVALID_TOKEN")

        unsigned_token = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(
            settings.secret_key.encode("utf-8"),
            unsigned_token.encode("ascii"),
            hashlib.sha256,
        ).digest()

        actual_sig = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise UnauthorizedException("Invalid token signature", code="INVALID_TOKEN_SIGNATURE")

        payload_bytes = _b64url_decode(parts[1])
        payload = json.loads(payload_bytes.decode("utf-8"))

        now = int(time.time())
        if payload.get("exp", 0) < now:
            raise UnauthorizedException("Session token has expired", code="TOKEN_EXPIRED")

        # Validate pilot MFA policy if required
        if settings.require_phishing_resistant_mfa:
            amr = payload.get("amr", [])
            # Must include phishing-resistant method like fido2 or hardware token
            if not any(method in ("fido2", "webauthn", "hardware_key") for method in amr):
                raise UnauthorizedException(
                    "Phishing-resistant MFA assurance required",
                    code="INSUFFICIENT_ASSURANCE",
                )

        return payload
    except UnauthorizedException:
        raise
    except Exception as e:
        raise UnauthorizedException(f"Token verification failed: {str(e)}", code="INVALID_TOKEN")


def encrypt_vault_payload(plaintext: str, key: Optional[bytes] = None) -> str:
    """Encrypt a secret string using AES-256-GCM. Returns base64 string nonce + ciphertext + tag."""
    import os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if key is None:
        key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_vault_payload(encrypted_b64: str, key: Optional[bytes] = None) -> str:
    """Decrypt base64 nonce + ciphertext + tag using AES-256-GCM."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if key is None:
        key = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    data = base64.b64decode(encrypted_b64.encode("ascii"))
    nonce = data[:12]
    ciphertext = data[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")

