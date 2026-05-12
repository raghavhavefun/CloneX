import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _master_secret() -> bytes:
    secret = os.getenv("AUTOMATION_CRED_MASTER_KEY", "").strip()
    if not secret:
        raise RuntimeError("AUTOMATION_CRED_MASTER_KEY is missing")
    return secret.encode("utf-8")


def _derive_fernet_key(salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    key = kdf.derive(_master_secret())
    return base64.urlsafe_b64encode(key)


def encrypt_text(plain_text: str) -> tuple[str, str]:
    salt = os.urandom(16)
    key = _derive_fernet_key(salt)
    token = Fernet(key).encrypt((plain_text or "").encode("utf-8"))
    return token.decode("utf-8"), base64.b64encode(salt).decode("utf-8")


def decrypt_text(cipher_text: str, salt_b64: str) -> str:
    salt = base64.b64decode(salt_b64.encode("utf-8"))
    key = _derive_fernet_key(salt)
    plain = Fernet(key).decrypt((cipher_text or "").encode("utf-8"))
    return plain.decode("utf-8")
