"""Tiny ULID generator (Crockford base32, monotonic-ish per process).

Avoids a dependency for the SDK at this stage. Replace with a robust
implementation if/when one is needed downstream.
"""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    ts_ms = int(time.time() * 1000)
    rnd = int.from_bytes(os.urandom(10), "big")
    value = (ts_ms << 80) | rnd
    out = []
    for _ in range(26):
        out.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))
