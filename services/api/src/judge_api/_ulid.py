"""Tiny ULID generator. Crockford base32, 26 chars, no extra deps."""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out: list[str] = []
    for _ in range(26):
        out.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))
