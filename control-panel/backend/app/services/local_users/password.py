"""Password hashing — pwdlib with Argon2 → Bcrypt chain.

Also includes RSA-2048 crypto for optional password transport encryption.
"""

import re
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


def validate_password_strength(password: str, username: str) -> list[str]:
    """Validate password against strength rules.

    Returns a list of failure reasons.  Empty list means the password
    meets all requirements.
    """
    errors: list[str] = []

    # Length: 8-64 (NIST SP 800-63B recommends allowing at least 64)
    if len(password) < 8 or len(password) > 64:
        errors.append("密码长度需为 8-64 位")

    # Must not contain username (case-insensitive)
    if username and username.lower() in password.lower():
        errors.append("密码不能包含用户名")

    # At least 2 of 4 character categories
    categories = 0
    if re.search(r"[a-z]", password):
        categories += 1
    if re.search(r"[A-Z]", password):
        categories += 1
    if re.search(r"[0-9]", password):
        categories += 1
    if re.search(r"[^a-zA-Z0-9]", password):
        categories += 1
    if categories < 2:
        errors.append(
            "密码需至少包含大写字母、小写字母、数字、特殊字符中的两类"
        )

    return errors


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
