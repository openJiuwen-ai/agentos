"""密码哈希与 RSA 加密工具测试。

覆盖 pwdlib 链式哈希（Argon2→Bcrypt）和 RSA-2048 加解密。
测试数据从 test_data.json 加载。
"""
from app.services.local_users.password import (
    hash_password,
    verify_password,
    generate_random_password,
    get_public_key_pem,
)
from tests.conftest import load_test_data

_data = load_test_data()
SAMPLE_PW = _data["passwords"]["sample"]


def test_hash_password_returns_string():
    """hash_password() 返回非空字符串（哈希值）。"""
    h = hash_password(SAMPLE_PW)
    assert isinstance(h, str)
    assert len(h) > 0


def test_verify_password_correct():
    """正确密码验证 → 返回 (True, upgraded_hash_or_None)。"""
    h = hash_password(SAMPLE_PW)
    valid, new_hash = verify_password(SAMPLE_PW, h)
    assert valid is True


def test_verify_password_wrong():
    """错误密码验证 → 返回 (False, None)。"""
    h = hash_password(SAMPLE_PW)
    valid, _ = verify_password("wrongpassword", h)
    assert valid is False


def test_verify_password_returns_upgraded_hash():
    """密码验证支持哈希升级：如果算法变更，返回升级后的新哈希。"""
    h = hash_password(SAMPLE_PW)
    valid, new_hash = verify_password(SAMPLE_PW, h)
    assert valid is True
    # new_hash 为 None 表示无需升级，为 str 表示已升级


def test_generate_random_password_unique():
    """随机密码生成器：每次生成不同且长度 >= 12。"""
    pw1 = generate_random_password()
    pw2 = generate_random_password()
    assert pw1 != pw2
    assert len(pw1) >= 12
    assert len(pw2) >= 12


def test_public_key_pem_format():
    """公钥 PEM 格式正确（BEGIN/END PUBLIC KEY）。"""
    pem = get_public_key_pem()
    assert pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert pem.endswith("-----END PUBLIC KEY-----\n")


def test_rsa_encrypt_decrypt_roundtrip():
    """RSA-2048 加解密往返：加密后解密还原原文。"""
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    plaintext = b"hello world"
    encrypted = private_key.public_key().encrypt(
        plaintext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    decrypted = private_key.decrypt(
        encrypted,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    assert decrypted == plaintext
