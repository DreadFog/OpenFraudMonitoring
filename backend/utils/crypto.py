"""
FPScanner decryption — XOR cipher + Base64.

Decrypts fingerprint payloads sent by FPScanner with encryption enabled.
The key must match the one used at FPScanner build time.
"""

import base64
import json


def decrypt_fingerprint(ciphertext_b64: str, key: str) -> dict:
    """
    Decrypt and parse an FPScanner encrypted fingerprint payload.

    Args:
        ciphertext_b64: Base64-encoded XOR-encrypted JSON
        key: Encryption key (must match FPScanner build key)

    Returns:
        Parsed fingerprint dict
    """
    encrypted = base64.b64decode(ciphertext_b64)
    key_bytes = key.encode("utf-8")

    decrypted = bytearray(len(encrypted))
    for i in range(len(encrypted)):
        decrypted[i] = encrypted[i] ^ key_bytes[i % len(key_bytes)]

    parsed = json.loads(decrypted.decode("utf-8"))
    # Handle double-JSON-encoding (string containing JSON)
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return parsed
