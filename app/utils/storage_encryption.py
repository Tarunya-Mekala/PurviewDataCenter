"""Storage encryption utilities for encrypting exported files at rest.

Uses self-contained authenticated encryption (CTR keystream with HMAC-SHA256,
per-file random 16-byte salt, random 16-byte IV, and HMAC-SHA256 integrity tag).
"""
import hashlib
import hmac
import os

MAGIC_HEADER = b"ENC1"
SALT_SIZE = 16
IV_SIZE = 16
TAG_SIZE = 32


def encrypt_file_bytes(data: bytes, secret_key: str) -> bytes:
    """Encrypt byte payload at rest with authenticated encryption."""
    if not data:
        return data

    salt = os.urandom(SALT_SIZE)
    iv = os.urandom(IV_SIZE)

    # Derive per-file encryption key using key + salt
    derived_key = hashlib.sha256(secret_key.encode("utf-8") + salt).digest()

    # Generate keystream blocks
    block_count = (len(data) + 31) // 32
    keystream = b"".join(
        hmac.new(derived_key, iv + i.to_bytes(4, "big"), hashlib.sha256).digest()
        for i in range(block_count)
    )

    # XOR plaintext with keystream
    ciphertext = bytes(a ^ b for a, b in zip(data, keystream[:len(data)]))

    # Authenticated tag over header, salt, iv, and ciphertext (Encrypt-then-MAC)
    auth_tag = hmac.new(
        derived_key,
        MAGIC_HEADER + salt + iv + ciphertext,
        hashlib.sha256,
    ).digest()

    return MAGIC_HEADER + salt + iv + auth_tag + ciphertext


def decrypt_file_bytes(encrypted: bytes, secret_key: str) -> bytes:
    """Decrypt byte payload encrypted at rest. Returns raw bytes if not encrypted."""
    if not encrypted:
        return encrypted

    # Check for encryption magic header
    if not encrypted.startswith(MAGIC_HEADER):
        return encrypted

    header_len = len(MAGIC_HEADER)
    salt_end = header_len + SALT_SIZE
    iv_end = salt_end + IV_SIZE
    tag_end = iv_end + TAG_SIZE

    if len(encrypted) < tag_end:
        return encrypted

    salt = encrypted[header_len:salt_end]
    iv = encrypted[salt_end:iv_end]
    expected_tag = encrypted[iv_end:tag_end]
    ciphertext = encrypted[tag_end:]

    derived_key = hashlib.sha256(secret_key.encode("utf-8") + salt).digest()

    # Verify authenticity and integrity tag
    computed_tag = hmac.new(
        derived_key,
        MAGIC_HEADER + salt + iv + ciphertext,
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(expected_tag, computed_tag):
        raise ValueError("Decryption failed: corrupted data or invalid key")

    # Reconstruct keystream and decrypt
    block_count = (len(ciphertext) + 31) // 32
    keystream = b"".join(
        hmac.new(derived_key, iv + i.to_bytes(4, "big"), hashlib.sha256).digest()
        for i in range(block_count)
    )

    return bytes(a ^ b for a, b in zip(ciphertext, keystream[:len(ciphertext)]))
