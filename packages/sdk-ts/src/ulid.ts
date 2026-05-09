/**
 * Tiny ULID generator (Crockford base32). Avoids a runtime dependency
 * for the SDK skeleton; swap for a robust impl later if needed.
 */
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

function randomBigInt(bits: number): bigint {
  // 80 random bits = 10 bytes
  const bytes = new Uint8Array(Math.ceil(bits / 8));
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  let out = 0n;
  for (const b of bytes) out = (out << 8n) | BigInt(b);
  return out;
}

export function newUlid(): string {
  const tsMs = BigInt(Date.now());
  const rnd = randomBigInt(80);
  let value = (tsMs << 80n) | rnd;
  const chars: string[] = [];
  for (let i = 0; i < 26; i += 1) {
    const idx = Number(value & 0x1fn);
    chars.push(ALPHABET[idx] ?? '0');
    value >>= 5n;
  }
  return chars.reverse().join('');
}
