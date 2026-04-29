"""Kalshi RSA-PSS SHA-256 request signing.

Per Kalshi v3 API spec (https://docs.kalshi.com/getting_started/api_keys):
  - Signing algorithm: RSA-PSS with SHA-256, MGF1(SHA-256), salt_length=32.
  - Message to sign: timestamp_ms (ASCII decimal) + HTTP_METHOD + path (no query params).
  - Signature: base64-encoded.
  - Headers: KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from feeds.kalshi.errors import KalshiAuthError


class KalshiAuth:
    """Manages API key + private key and produces signed headers for each request."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        private_key_path: str | Path | None = None,
        private_key_pem: bytes | None = None,
    ) -> None:
        """Initialise auth credentials.

        Args:
            api_key: Kalshi API key UUID. Falls back to env ``KALSHI_API_KEY``.
            private_key_path: Path to RSA private key PEM file.
                Falls back to env ``KALSHI_PRIVATE_KEY_PATH``.
            private_key_pem: Raw PEM bytes. Takes precedence over ``private_key_path``
                if both are provided.
        """
        self._api_key = api_key or os.environ.get("KALSHI_API_KEY", "")
        if not self._api_key:
            raise KalshiAuthError("Kalshi API key not provided and KALSHI_API_KEY env var is empty")

        if private_key_pem is not None:
            self._private_key = self._load_key_from_pem(private_key_pem)
        else:
            key_path = private_key_path or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
            if not key_path:
                raise KalshiAuthError(
                    "Kalshi private key not provided: set private_key_path, "
                    "private_key_pem, or KALSHI_PRIVATE_KEY_PATH env var"
                )
            self._private_key = self._load_key_from_file(Path(key_path))

    @staticmethod
    def _load_key_from_file(path: Path) -> rsa.RSAPrivateKey:
        """Load an RSA private key from a PEM file."""
        if not path.exists():
            raise KalshiAuthError(f"Private key file not found: {path}")
        pem_data = path.read_bytes()
        return KalshiAuth._load_key_from_pem(pem_data)

    @staticmethod
    def _load_key_from_pem(pem_data: bytes) -> rsa.RSAPrivateKey:
        """Parse an RSA private key from PEM bytes."""
        try:
            key = serialization.load_pem_private_key(pem_data, password=None)
        except Exception as exc:
            raise KalshiAuthError(f"Failed to load RSA private key: {exc}") from exc
        if not isinstance(key, rsa.RSAPrivateKey):
            raise KalshiAuthError(f"Expected RSA private key, got {type(key).__name__}")
        return key

    @property
    def api_key(self) -> str:
        return self._api_key

    def sign(self, timestamp_ms: int, method: str, path: str) -> str:
        """Produce a base64-encoded RSA-PSS signature for a request.

        Args:
            timestamp_ms: Milliseconds since Unix epoch.
            method: HTTP method, uppercase (e.g. ``GET``, ``POST``).
            path: Request path without query parameters (e.g. ``/trade-api/v2/markets``).

        Returns:
            Base64-encoded signature string.
        """
        message = f"{timestamp_ms}{method}{path}".encode("ascii")
        raw_sig = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(raw_sig).decode("ascii")

    def build_headers(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        """Build the three Kalshi auth headers for a request.

        Args:
            method: HTTP method, uppercase.
            path: Request path without query parameters.
            timestamp_ms: Optional override; defaults to current time.

        Returns:
            Dict with KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        signature = self.sign(timestamp_ms, method, path)
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": str(timestamp_ms),
            "KALSHI-ACCESS-SIGNATURE": signature,
        }


def generate_test_key_pair() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Generate an RSA key pair for testing. Returns (private_key, pem_bytes)."""
    from cryptography.hazmat.primitives.asymmetric import rsa as rsa_gen

    private_key = rsa_gen.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_key, pem_bytes
