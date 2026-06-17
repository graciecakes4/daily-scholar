#!/usr/bin/env python3
"""
Generate a VAPID keypair for Web Push.

Run once, then paste the printed lines into your .env file. The same keypair
should be reused across server restarts — regenerating invalidates every
existing push subscription (all browsers would need to re-subscribe).

Usage:
    python scripts/generate_vapid_keys.py
"""

import base64

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(raw: bytes) -> str:
    """Standard VAPID urlsafe base64 without padding."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key = private_key.public_key()

    # private key: DER-encoded SEC1 raw scalar -> urlsafe-b64
    private_numbers = private_key.private_numbers()
    private_bytes = private_numbers.private_value.to_bytes(32, "big")
    private_b64 = _b64url(private_bytes)

    # public key: uncompressed point (65 bytes: 0x04 || X || Y) -> urlsafe-b64
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = _b64url(public_bytes)

    print("# --- VAPID keys for Web Push ---")
    print("# Paste these into your .env. Use the SAME keys forever for this app")
    print("# (regenerating invalidates every existing browser subscription).")
    print()
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_SUBJECT=mailto:you@example.com")
    print()
    print("# VAPID_SUBJECT must be a mailto: or https:// URL identifying the app owner.")


if __name__ == "__main__":
    main()
