"""Mint a VAPID key pair for web push (DECISIONS D55).

Push is off whenever `VAPID_PRIVATE_KEY` is unset, which is how development and CI get
away with no keys at all. Turning it on needs a pair in the exact encoding the Web Push
protocol wants — the public key as an uncompressed P-256 point, base64url without
padding, because that is what the browser passes to `pushManager.subscribe` — and
hand-rolling that encoding is the one step people get wrong.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand
from py_vapid import b64urlencode


class Command(BaseCommand):
    help = "Print a fresh VAPID key pair as environment variables."

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        private = key.private_numbers().private_value.to_bytes(32, "big")

        self.stdout.write(f"VAPID_PUBLIC_KEY={b64urlencode(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64urlencode(private)}")
        self.stdout.write(
            self.style.WARNING(
                "\nThe pair is printed, never stored. Put both in the backend's .env; the "
                "public key alone is served to the browser. Changing it later invalidates "
                "every existing subscription."
            )
        )
