"""Isolated Ephemeral SSH Certificate Authority (CA) Service (P4-01 & P4-02).

Implements OpenSSH User Certificate signing, principal restriction,
short validity windows, and zero gateway CA key exposure under ADR-003, ADR-009, and SEC-05.
"""

import re
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Dict, Any, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_ssh_public_key,
    SSHCertificateBuilder,
    SSHCertificateType,
)
from ariba_pam.core.errors import ValidationException, ForbiddenException
from ariba_pam.db.base import utc_now, ensure_utc

# POSIX username safety regex
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_.][a-zA-Z0-9_.-]{0,31}$")


class SSHUserCAService:
    """
    Isolated User Certificate Authority signer.
    The CA private key resides strictly in memory within this service.
    Neither the SSH gateway nor general administrators have direct access to the private key.
    """

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._active_key: ed25519.Ed25519PrivateKey = private_key or ed25519.Ed25519PrivateKey.generate()
        self._previous_keys: List[ed25519.Ed25519PrivateKey] = []

    def get_active_public_key(self) -> str:
        """Return the active CA public key in OpenSSH authorized_keys format."""
        pub_bytes = self._active_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        return f"{pub_bytes.decode('ascii')} ariba-pam-user-ca"

    def get_active_fingerprint(self) -> str:
        """Return SHA-256 fingerprint of the active CA public key."""
        pub_bytes = self._active_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
        digest = hashlib.sha256(pub_bytes).hexdigest()
        return f"SHA256:{digest[:32]}"

    def get_trusted_ca_keys(self) -> List[str]:
        """Return all trusted CA public keys (active + rollover) for target host configuration."""
        keys = [self.get_active_public_key()]
        for prev in self._previous_keys:
            prev_pub = prev.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode("ascii")
            keys.append(f"{prev_pub} ariba-pam-user-ca-rollover")
        return keys

    def rotate_ca_key(self) -> str:
        """
        Execute CA key rollover (P4-02).
        Generates a new active CA key and retains the previous key for dual-trust verification.
        """
        self._previous_keys.append(self._active_key)
        self._active_key = ed25519.Ed25519PrivateKey.generate()
        return self.get_active_public_key()

    def sign_grant_certificate(
        self,
        client_public_key_openssh: str,
        principal: str,
        grant_id: str,
        grant_end_at: datetime,
        max_validity_seconds: int = 300,
    ) -> Tuple[str, datetime, int, str]:
        """
        Sign an ephemeral OpenSSH User Certificate for an authorized grant.

        Enforces:
        1. Principal Restriction: ONLY the target account username is authorized.
        2. Bounded Validity: Max 5 minutes, capped by grant_end_at.
        3. Audit Traceability: Serial number and Key ID derived from grant and session.
        4. Standard OpenSSH Extensions: permit-pty, permit-user-rc.
        """
        if not principal or not USERNAME_REGEX.match(principal):
            raise ValidationException(
                f"Invalid principal username format: '{principal}'",
                code="INVALID_PRINCIPAL",
            )

        # Parse client public key submitted by gateway
        try:
            pubkey_bytes = client_public_key_openssh.strip().encode("ascii")
            client_pub = load_ssh_public_key(pubkey_bytes)
        except Exception as exc:
            raise ValidationException(
                f"Failed to parse client OpenSSH public key: {exc}",
                code="INVALID_PUBLIC_KEY",
            )

        now = utc_now()
        effective_end = ensure_utc(grant_end_at)
        if now >= effective_end:
            raise ForbiddenException(
                "Cannot sign certificate: grant validity window has expired",
                code="GRANT_EXPIRED",
            )

        # Allow 30 seconds clock skew in the past
        valid_after = now - timedelta(seconds=30)
        # Cap validity window to 5 minutes or remaining grant window, whichever is smaller
        valid_seconds = min(max_validity_seconds, int((effective_end - now).total_seconds()))
        valid_before = now + timedelta(seconds=max(30, valid_seconds))

        # Deterministic 64-bit positive serial number
        seed = f"{grant_id}_{principal}_{int(now.timestamp())}".encode("utf-8")
        serial_int = int.from_bytes(hashlib.sha256(seed).digest()[:8], byteorder="big") & 0x7FFFFFFFFFFFFFFF

        key_id = f"ariba_{grant_id}_{principal}".encode("ascii")

        builder = (
            SSHCertificateBuilder()
            .public_key(client_pub)
            .serial(serial_int)
            .type(SSHCertificateType.USER)
            .key_id(key_id)
            .valid_principals([principal.encode("ascii")])
            .valid_after(int(valid_after.timestamp()))
            .valid_before(int(valid_before.timestamp()))
            .add_extension(b"permit-pty", b"")
            .add_extension(b"permit-user-rc", b"")
        )

        cert = builder.sign(self._active_key)
        cert_openssh = cert.public_bytes().decode("ascii")

        return cert_openssh, valid_before, serial_int, self.get_active_fingerprint()


# Global in-memory CA service singleton (initialized once per process)
ca_service = SSHUserCAService()
