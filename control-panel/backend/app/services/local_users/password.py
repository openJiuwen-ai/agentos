"""Password hashing — pwdlib with Argon2 → Bcrypt chain.

Also includes RSA-2048 crypto for optional password transport encryption.
"""

import secrets

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

# ── Password hashing ────────────────────────────────────────────────

_password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """Return ``(is_valid, upgraded_hash_or_None)``."""
    return _password_hash.verify_and_update(plain, hashed)


def generate_random_password() -> str:
    return secrets.token_urlsafe(12)


# ── RSA keypair (optional transport encryption) ─────────────────────

_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend(),
)


def get_public_key_pem() -> str:
    return (
        _private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )


def decrypt_password(encrypted_hex: str) -> str:
    encrypted_bytes = bytes.fromhex(encrypted_hex)
    decrypted = _private_key.decrypt(
        encrypted_bytes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return decrypted.decode("utf-8")
